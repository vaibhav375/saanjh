"""Ask Saanjh: a Strands agent (Claude on Amazon Bedrock) that explains tonight's ranking from the data.

Function URL: GET ?q=<question>[&rank=<n>][&day=YYYY-MM-DD]. The agent can only read: the published
night (tonight.json or a replayed day), a town's smoke timing, the live CPCB PM2.5 reading near a town
(OpenAQ), and the project's measured research findings. It never identifies farmers or plots.
"""
import json
import os
import re

import boto3
import requests
from strands import Agent, tool
from strands.models import BedrockModel

MODEL_ID = os.environ.get("AGENT_MODEL_ID", "us.anthropic.claude-haiku-5-5")
s3 = boto3.client("s3")
_night = {}

FINDINGS = """Measured by Saanjh (Punjab + Haryana, 15 Oct - 30 Nov, every 10-minute GK-2A image):
- 86.8% (2024) and 91.7% (2025, held out) of the fire energy GK-2A detected came from fires that started after the
  ~13:30 IST polar-satellite overpass behind India's official fire count.
- GK-2A sees Punjab at ~66 degrees off vertical (~4 km pixels): it detects ~3% of fires under 5 MW and ~43% of
  40-80 MW fires seen by VIIRS. Small fires are mostly invisible to it.
- The same fire lit at 17:00 instead of 13:00 causes 2.8x the population smoke exposure (200 m plume floor;
  1.9x at 400 m), because the boundary layer collapses from ~1 km to tens of metres after sunset; worse on all 47 days.
- Adding the missed fires to today's overpass inventory raises the day-to-day correlation of modelled smoke with
  measured PM2.5 near the fires from 0.23 to 0.28 (2025, 95% CI +0.02 to +0.10); no change in Delhi.
- A night-before smoke warning does not beat 'tomorrow will be like today' for predicting bad mornings.
Rankings are by modelled population exposure (people x hours x ug/m3) over the next ~30 hours."""

SYSTEM = """You are Saanjh's assistant for district officers and school staff in Punjab and Haryana.
Answer only from your tools. Be brief (at most 5 sentences), concrete and plain; give numbers with units.
When asked why a fire ranks where it does, call get_fire and explain from its timing, size, location and share
of exposure, and mention that evening smoke is trapped in a shallow night-time layer if relevant.
Never identify or speculate about individual farmers or plots; the grid is 2-4 km. If the data cannot answer,
say so. Model smoke values are estimates of the farm-fire share only, not total pollution."""


def _load(day=None):
    key = (day or "tonight")
    if key not in _night:
        if day:
            obj = s3.get_object(Bucket=os.environ["DATA_BUCKET"], Key=f"results/{day.replace('-', '')}.json")
        else:
            obj = s3.get_object(Bucket=os.environ["SITE_BUCKET"], Key="tonight.json")
        d = json.loads(obj["Body"].read())
        d.pop("frames", None)
        d.pop("counted_cells", None)
        _night[key] = d
    return _night[key]


def make_agent(day=None):
    @tool
    def get_fire(rank: int) -> dict:
        """Details of the fire at this rank (1 = most harmful) in tonight's officer list: where it is (nearest
        town and distance), when GK-2A first saw it (IST), how many 10-minute images it was seen in, peak fire
        power (MW), estimated PM2.5 released (kg), whether the official count has it, and its share of all
        modelled farm-smoke exposure."""
        d = _load(day)
        if not 1 <= rank <= len(d["fires"]):
            return {"error": f"rank must be 1..{len(d['fires'])}"}
        f = dict(d["fires"][rank - 1])
        f["share_of_exposure_pct"] = round(100 * f.pop("harm") / d["stats"]["harm_total"], 2)
        f.pop("lat"), f.pop("lon")
        return f

    @tool
    def get_night_summary() -> dict:
        """Tonight's totals: fire events seen, how many were burning when the polar satellites passed, share of
        fire energy the official count missed, PM2.5 released, and the date."""
        d = _load(day)
        return {"day": d["day"], "replay": d.get("replay", False), **{k: v for k, v in d["stats"].items()
                                                                       if k not in ("harm_total", "first_seen")}}

    @tool
    def get_town(name: str) -> dict:
        """When farm-fire smoke reaches a town tonight (IST) and its modelled peak farm-smoke PM2.5 (ug/m3)."""
        for t in _load(day)["towns"]:
            if t["town"].lower() == name.strip().lower():
                return t
        return {"error": "town not in the list", "towns": [t["town"] for t in _load(day)["towns"]]}

    @tool
    def get_station_pm25(town: str) -> dict:
        """The latest measured PM2.5 (ug/m3) at the CPCB monitor nearest the town, from OpenAQ."""
        key = os.environ.get("OPENAQ_API_KEY")
        t = get_town(town)
        if "error" in t or not key:
            return {"error": "no reading available"}
        if "lat" not in t:
            return {"error": "no reading available"}
        la, lo = t["lat"], t["lon"]
        r = requests.get("https://api.openaq.org/v3/locations", timeout=20, headers={"X-API-Key": key},
                         params=dict(coordinates=f"{la},{lo}", radius=25000, parameters_id=2, limit=5))
        for loc in r.json().get("results", []):
            for s in loc.get("sensors", []):
                if s["parameter"]["name"] == "pm25":
                    latest = requests.get(f"https://api.openaq.org/v3/sensors/{s['id']}", timeout=20,
                                          headers={"X-API-Key": key}).json()["results"][0].get("latest") or {}
                    if latest.get("value") is not None:
                        return {"station": loc["name"], "pm25_ugm3": latest["value"], "at": latest["datetime"]["local"]}
        return {"error": "no station within 25 km reported recently"}

    @tool
    def get_research_findings() -> str:
        """What Saanjh has measured about evening fires, detection limits, the dusk penalty and validation."""
        return FINDINGS

    return Agent(model=BedrockModel(model_id=MODEL_ID, region_name=os.environ.get("AWS_REGION", "us-east-1"),
                                    max_tokens=400),
                 system_prompt=SYSTEM, tools=[get_fire, get_night_summary, get_town, get_station_pm25,
                                              get_research_findings], callback_handler=None)


def ask_handler(event, _ctx=None):
    q = (event.get("queryStringParameters") or {})
    question = (q.get("q") or "").strip()[:500]
    day = q.get("day") if re.fullmatch(r"\d{4}-\d{2}-\d{2}", q.get("day", "")) else None
    if q.get("rank", "").isdigit():
        question = question or f"Why is fire #{q['rank']} ranked #{q['rank']}?"
    if not question:
        return dict(statusCode=400, headers={"Content-Type": "text/plain"}, body="Ask a question with ?q=")
    try:
        answer = str(make_agent(day)(question)).strip()
    except Exception as e:  # Bedrock unavailable, throttled, etc.: say so plainly
        return dict(statusCode=503, headers={"Content-Type": "application/json"},
                    body=json.dumps({"error": f"The assistant is unavailable right now ({type(e).__name__})."}))
    return dict(statusCode=200, headers={"Content-Type": "application/json", "Cache-Control": "no-store"},
                body=json.dumps({"question": question, "answer": answer}))
