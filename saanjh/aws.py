"""Lambda entry points.

detect_handler  live: SQS messages carrying NOAA's NewGK2AObject notifications, one per new file.
                replay: {"day": "2024-11-18", "step_min": 60} detects a whole day.
                Writes detections/<yyyymmdd>/<HHMM>.csv to the data bucket.
model_handler   {"day": ..., "replay": true} or a scheduled event (live, today in IST).
                Builds fire events, runs the smoke model, writes site/tonight.json (live) or
                results/<yyyymmdd>.json (replay), and publishes smoke alerts (live only).
"""
import base64
import io
import json
import os
import re
import shutil
from datetime import datetime, timedelta, timezone

import boto3
import numpy as np
import pandas as pd

ASSETS = os.path.join(os.path.dirname(__file__), "assets")
os.environ.setdefault("SAANJH_DATA", "/tmp/data")
if os.path.isdir(ASSETS) and not os.path.exists("/tmp/data/pop"):
    shutil.copytree(ASSETS, "/tmp/data", dirs_exist_ok=True)

from saanjh import gk2a, pipeline, smoke  # noqa: E402  (after SAANJH_DATA is set)

s3 = boto3.client("s3")
BUCKET = os.environ.get("DATA_BUCKET", "")
SITE = os.environ.get("SITE_BUCKET", "")
ALERT_TOPIC = os.environ.get("ALERT_TOPIC_ARN", "")
ALERT_UGM3 = float(os.environ.get("ALERT_UGM3", "25"))
KEY_RE = re.compile(r"gk2a_ami_le1b_(sw038|ir112)_fd020ge_(\d{12})\.nc")


def read_scan(band, t):
    """Crop of one scan straight from NOAA's bucket (same region, so ~1 s); None if missing."""
    try:
        return gk2a.read_bt(gk2a.url(band, t), band)
    except FileNotFoundError:
        return None


def _put(key, body, bucket=None, ctype="application/json"):
    s3.put_object(Bucket=bucket or BUCKET, Key=key, Body=body, ContentType=ctype)


def _base(day):
    key = f"baseline/{day:%Y%m%d}.npz"
    try:
        z = np.load(io.BytesIO(s3.get_object(Bucket=BUCKET, Key=key)["Body"].read()))
        return z["bias"], z["noise"]
    except s3.exceptions.NoSuchKey:
        bias, noise = pipeline.morning_base(day, read_scan)
        buf = io.BytesIO()
        np.savez_compressed(buf, bias=bias, noise=noise)
        _put(key, buf.getvalue(), ctype="application/octet-stream")
        return bias, noise


def _detect(t):
    if not 12 <= (t + pipeline.IST).hour <= 23:
        return None
    day = t.replace(hour=0, minute=0)
    d = pipeline.detect_scan(t, _base(day), read_scan)
    if d is not None:
        _put(f"detections/{t:%Y%m%d}/{t:%H%M}.csv", d.to_csv(index=False), ctype="text/csv")
    return d


def detect_handler(event, _ctx=None):
    if "day" in event:  # replay a whole day
        day = datetime.fromisoformat(event["day"])
        times = pipeline.scan_times(day, int(event.get("step_min", 60)))[1]
        found = [d for d in map(_detect, times) if d is not None]
        return {"day": event["day"], "scans": len(found), "detections": int(sum(len(d) for d in found))}
    done = 0
    for rec in event.get("Records", []):  # SQS <- SNS <- S3 event
        body = json.loads(rec["body"])
        msg = json.loads(body["Message"]) if "Message" in body else body
        for r in msg.get("Records", []):
            m = KEY_RE.search(r["s3"]["object"]["key"])
            if m:  # either band may land first; the second one's message does the work
                done += _detect(datetime.strptime(m.group(2), "%Y%m%d%H%M")) is not None
    return {"processed": done}


def _detections(day):
    keys = [o["Key"] for p in s3.get_paginator("list_objects_v2").paginate(
        Bucket=BUCKET, Prefix=f"detections/{day:%Y%m%d}/") for o in p.get("Contents", [])]
    frames = [pd.read_csv(io.BytesIO(s3.get_object(Bucket=BUCKET, Key=k)["Body"].read()), parse_dates=["t"])
              for k in keys]
    frames = [f for f in frames if len(f)]
    return pd.concat(frames) if frames else pd.DataFrame(), len(keys)


def _viirs(day):
    try:
        v = pd.read_csv(io.BytesIO(s3.get_object(Bucket=BUCKET, Key="viirs/punjab_both.csv")["Body"].read()))
        return v[v.acq_date == f"{day:%Y-%m-%d}"]
    except s3.exceptions.NoSuchKey:
        return None


def _frames(conc, factor=2):
    """Hourly ground-smoke grids, block-averaged to 0.1 deg and log-scaled to uint8, base64."""
    k, ny, nx = conc.shape
    c = conc[:, :ny // factor * factor, :nx // factor * factor].reshape(k, ny // factor, factor, nx // factor, factor)
    q = np.clip(np.log10(np.maximum(c.mean((2, 4)), 1e-3)) * 50 + 150, 0, 255).astype("u1")  # 1e-3..1e2 ug/m3
    return [base64.b64encode(f.tobytes()).decode() for f in q]


def model_handler(event, _ctx=None):
    replay = bool(event.get("replay"))
    now_ist = datetime.now(timezone.utc).replace(tzinfo=None) + pipeline.IST
    day = datetime.fromisoformat(event["day"]) if "day" in event else now_ist.replace(hour=0, minute=0, second=0, microsecond=0)
    det, n_scans = _detections(day)
    if det.empty:
        return {"day": f"{day:%Y-%m-%d}", "events": 0}
    step = int(np.median(np.diff(np.sort(det.t.unique()))) / np.timedelta64(1, "m")) if det.t.nunique() > 1 else 60
    ev = pipeline.fire_events(day, step_min=step, viirs=_viirs(day), detections=det)
    met = smoke.Met.era5(day - timedelta(days=1), day + timedelta(days=2), forecast=not replay)
    ev, towns, conc, t0 = pipeline.tonight(day, met, ev)
    out = dict(
        day=f"{day:%Y-%m-%d}", generated=f"{datetime.now(timezone.utc):%Y-%m-%dT%H:%MZ}", scans=n_scans,
        stats=dict(events=len(ev), counted=int(ev.counted.sum()),
                   uncounted_energy_share=round(float(ev.fre_mj[~ev.counted].sum() / ev.fre_mj.sum()), 3),
                   fre_mj=round(float(ev.fre_mj.sum())), pm25_t=round(float(ev.pm25_kg.sum()) / 1000, 1)),
        fires=json.loads(ev.head(50)[["lat", "lon", "first_ist", "scans", "frp_peak", "pm25_kg", "counted", "harm"]]
                         .round(3).to_json(orient="records")),
        towns=json.loads(towns.round(1).to_json(orient="records")),
        grid=dict(lat0=smoke.LAT0, lon0=smoke.LON0, d=smoke.D * 2, ny=smoke.NY // 2, nx=smoke.NX // 2,
                  t0=f"{t0:%Y-%m-%dT%H:%MZ}", scale="ug/m3 = 10**((v-150)/50)"),
        frames=_frames(conc))
    body = json.dumps(out, separators=(",", ":"))
    if replay:
        _put(f"results/{day:%Y%m%d}.json", body)
    else:
        _put("tonight.json", body, bucket=SITE)
        _alert(day, towns)
    return {"day": out["day"], **out["stats"]}


def _alert(day, towns):
    """One SNS message per night listing towns whose predicted farm-smoke peak crosses the threshold."""
    hit = towns[towns.peak_ugm3 >= ALERT_UGM3]
    marker = f"alerts/{day:%Y%m%d}.txt"
    if not ALERT_TOPIC or hit.empty:
        return
    try:
        s3.head_object(Bucket=BUCKET, Key=marker)
        return  # already sent tonight
    except s3.exceptions.ClientError:
        pass
    lines = [f"{r.town}: farm smoke from about {r.arrives_ist}, worst around {r.peak_ist} "
             f"(+{r.peak_ugm3:.0f} ug/m3 PM2.5)" for r in hit.itertuples()]
    boto3.client("sns").publish(TopicArn=ALERT_TOPIC, Subject="Saanjh: farm smoke expected tonight",
                                Message="\n".join(lines) + "\n\nSchools: keep tomorrow's morning assembly indoors.")
    _put(marker, "\n".join(lines), ctype="text/plain")
