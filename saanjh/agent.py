"""Ask Saanjh: a Strands agent on Amazon Bedrock that explains tonight's ranking from the data.

The model is an open-weight one served by Bedrock's OpenAI-compatible Mantle endpoint (Qwen3 235B by default):
on the AWS Free plan those are the models with inference quota, and Bedrock bills them to the account's credits.

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
from strands.models.openai import OpenAIModel

MODEL_ID = os.environ.get("AGENT_MODEL_ID", "qwen.qwen3-235b-a22b-2507")
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
- A second satellite confirms the evening fires: evening fires GK-2A saw for 30 min or more show up in the ~01:30
  VIIRS night pass 3.0x as often as the same places on other nights (95% CI 1.8-4.7). Fires seen in a single
  10-minute image are NOT confirmed; without them the 2025 share is 89.5% (2024: 83.0%).
- A night-before smoke warning does not beat 'tomorrow will be like today' for predicting bad mornings.
- Noon team plan (2025 held out): 20 field teams placed by expected smoke harm cover 75% of that evening's smoke
  harm, vs 31% when teams chase the previous day's officially counted fires. Fire-risk model ROC AUC 0.90.
- Each town's farm smoke is split by state and source area (exact within the linear smoke model); e.g. on
  18 Nov 2024 Delhi's farm smoke came 84% from Punjab and 16% from Haryana.
- Town values are the median over 9 weather scenarios (perturbed wind direction/speed, mixing height, plume
  height); p_alert is the share of scenarios above 25 ug/m3.
Rankings are by modelled population exposure (people x hours x ug/m3) over the next ~30 hours."""

SYSTEM = """You are Saanjh's assistant for district officers and school staff in Punjab and Haryana.
Answer only from your tools. Be brief (at most 5 sentences), concrete and plain; give numbers with units.
The ranking is by share of modelled population exposure (people x hours x smoke), not by size or emissions.
When asked why a fire ranks where it does, call get_fire and explain from its timing, size, location and share
of exposure, and mention that evening smoke is trapped in a shallow night-time layer if relevant.
Never compare a fire with others ("highest", "largest") unless you have called get_fire for those others too.
Never identify or speculate about individual farmers or plots; the grid is 2-4 km. If the data cannot answer,
say so. Model smoke values are estimates of the farm-fire share only, not total pollution.
If the night summary's `confirmed` is under 5, say there are too few confirmed fires (seen for 30 minutes or more)
to give a reliable missed share yet; do not headline the percentage.
Times carry a weekday (e.g. "Tue 06:00"); when it is not the night's own date, keep it and say it is the next
morning or day. Fires only VIIRS saw are modelled as burning around midday: never call their smoke evening smoke."""


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
        """Tonight's totals and the date. events: fires GK-2A saw; counted: of those, burning and seen by VIIRS at
        the ~13:30 pass; uncounted_energy_share: share of GK-2A fire energy from fires the count missed;
        confirmed: fires seen for 30 min or more (if under 5, say the share is not yet reliable);
        pm25_gk_t: tonnes of PM2.5 from the fires GK-2A saw; viirs_only: small fires VIIRS counted that GK-2A
        could not see; pm25_t: PM2.5 from all fires in the smoke model, including those VIIRS-only fires (assumed
        to burn through the middle of the day); missed_harm_share: share of smoke exposure from uncounted fires."""
        d = _load(day)
        st = {k: v for k, v in d["stats"].items() if k not in ("harm_total", "first_seen")}
        if st.get("confirmed", 99) < 5:  # same rule as the page: no headline share from unconfirmed fires
            st.pop("uncounted_energy_share", None)
            st["note"] = "Too few fires confirmed (seen for 30 min or more) to give a missed share yet."
        return {"day": d["day"], "replay": d.get("replay", False), **st}

    @tool
    def get_town(name: str) -> dict:
        """When farm-fire smoke reaches a town tonight (IST), its modelled peak farm-smoke PM2.5 (ug/m3, median of
        9 weather scenarios), the probability it exceeds 25 / 10 ug/m3, and where that smoke comes from
        (shares by state and by source area)."""
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

    model = OpenAIModel(bedrock_mantle_config={"region": os.environ.get("AWS_REGION", "us-east-1")},
                        model_id=MODEL_ID, params={"max_tokens": 400, "temperature": 0.2})
    return Agent(model=model,
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
