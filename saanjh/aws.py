"""Lambda entry points.

detect_handler  live: SQS messages carrying NOAA's NewGK2AObject notifications, one per new file.
                replay: {"day": "2024-11-18", "step_min": 60} detects a whole day.
                Writes detections/<yyyymmdd>/<HHMM>.csv to the data bucket.
model_handler   {"day": ..., "replay": true} or a scheduled event (live, today in IST).
                Builds fire events, runs the smoke model, writes site/tonight.json (live) or
                results/<yyyymmdd>.json (replay), and publishes smoke alerts (live only).
"""
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


def metric(stage="live", **values):
    """Publish custom CloudWatch metrics with the Embedded Metric Format: one structured log line, no API call.
    values: name=(value, unit)."""
    import time as _t
    print(json.dumps({"_aws": {"Timestamp": int(_t.time() * 1000), "CloudWatchMetrics": [{
        "Namespace": "Saanjh", "Dimensions": [["Stage"]],
        "Metrics": [{"Name": k, "Unit": u} for k, (_, u) in values.items()]}]},
        "Stage": stage, **{k: v for k, (v, _) in values.items()}}))


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
                import time as _t
                t = datetime.strptime(m.group(2), "%Y%m%d%H%M")
                t0 = _t.time()
                d = _detect(t)
                if d is not None:
                    done += 1
                    lag = (datetime.now(timezone.utc).replace(tzinfo=None) - t).total_seconds()
                    metric(ScansProcessed=(1, "Count"), Detections=(len(d), "Count"),
                           ScanLatency=(lag, "Seconds"), ProcessSeconds=(_t.time() - t0, "Seconds"))
    return {"processed": done}


def _detections(day):
    keys = [o["Key"] for p in s3.get_paginator("list_objects_v2").paginate(
        Bucket=BUCKET, Prefix=f"detections/{day:%Y%m%d}/") for o in p.get("Contents", [])]
    frames = [pd.read_csv(io.BytesIO(s3.get_object(Bucket=BUCKET, Key=k)["Body"].read()), parse_dates=["t"])
              for k in keys]
    frames = [f for f in frames if len(f)]
    return pd.concat(frames) if frames else pd.DataFrame(), len(keys)


def _viirs(day, replay=True):
    """VIIRS fires for the day: archive copy in S3 for replays, FIRMS near-real-time for live runs."""
    key = os.environ.get("FIRMS_MAP_KEY")
    if not replay and key:
        import requests
        frames = []
        for src in ("VIIRS_SNPP_NRT", "VIIRS_NOAA20_NRT", "VIIRS_NOAA21_NRT"):
            r = requests.get(f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{key}/{src}/71,26,81,34/1/{day:%Y-%m-%d}",
                             timeout=60)
            if r.ok and r.text.startswith("latitude"):
                frames.append(pd.read_csv(io.StringIO(r.text)))
        v = pd.concat(frames) if frames else pd.DataFrame()
        return v[v.daynight == "D"] if len(v) else None
    try:
        v = pd.read_csv(io.BytesIO(s3.get_object(Bucket=BUCKET, Key="viirs/punjab_both.csv")["Body"].read()))
        return v[v.acq_date == f"{day:%Y-%m-%d}"]
    except s3.exceptions.NoSuchKey:
        return None


def model_handler(event, _ctx=None):
    replay = bool(event.get("replay"))
    now_ist = datetime.now(timezone.utc).replace(tzinfo=None) + pipeline.IST
    day = datetime.fromisoformat(event["day"]) if "day" in event else now_ist.replace(hour=0, minute=0, second=0, microsecond=0)
    det, n_scans = _detections(day)
    if det.empty:
        return {"day": f"{day:%Y-%m-%d}", "events": 0}
    step = int(np.median(np.diff(np.sort(det.t.unique()))) / np.timedelta64(1, "m")) if det.t.nunique() > 1 else 60
    viirs = _viirs(day, replay)
    ev = pipeline.fire_events(day, step_min=step, viirs=viirs, detections=det)
    met = smoke.Met.era5(day - timedelta(days=1), day + timedelta(days=2), forecast=not replay)
    ranked, towns, conc, t0 = pipeline.tonight(day, met, ev, viirs=viirs)
    out = pipeline.summary(day, ranked, towns, conc, t0, n_scans, replay, events=ev)
    body = json.dumps(out, separators=(",", ":"))
    if replay:
        _put(f"results/{day:%Y%m%d}.json", body)
    else:
        _put("tonight.json", body, bucket=SITE)
        _alert(day, towns)
        metric(ModelRuns=(1, "Count"), FireEvents=(len(ev), "Count"),
               AlertTowns=(int((towns.peak_ugm3 >= ALERT_UGM3).sum()), "Count"))
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
    lines = [f"{r.town}: arrives around {r.arrives_ist}, heaviest around {r.peak_ist} "
             f"(farm smoke adds ~{r.peak_ugm3:.0f} ug/m3 PM2.5, model estimate)" for r in hit.itertuples()]
    boto3.client("sns").publish(
        TopicArn=ALERT_TOPIC, Subject="Saanjh: farm-fire smoke heading your way tonight",
        Message="Farm-fire smoke is heading to these towns tonight:\n" + "\n".join(lines)
        + "\n\nSchools: before tomorrow's morning assembly, check the local PM2.5 reading "
        "(CPCB Sameer app); if it is above 90, hold assembly indoors.\nMap: " + os.environ.get("SITE_URL", ""))
    _put(marker, "\n".join(lines), ctype="text/plain")


STATIC = os.path.join(os.path.dirname(__file__), "..", "site")
TYPES = {".html": "text/html; charset=utf-8", ".json": "application/json"}


def site_handler(event, _ctx=None):
    """Function URL: the page and borders from the package, tonight.json from the site bucket,
    or a replayed day's results with ?day=YYYY-MM-DD."""
    path = event.get("rawPath", "/").lstrip("/") or "index.html"
    q = event.get("queryStringParameters") or {}
    try:
        if path == "plan.json":
            day = q.get("day", "")
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
                body = s3.get_object(Bucket=BUCKET, Key=f"results/plan_{day.replace('-', '')}.json")["Body"].read()
            else:
                body = s3.get_object(Bucket=SITE, Key="plan.json")["Body"].read()
            return dict(statusCode=200, headers={"Content-Type": TYPES[".json"], "Cache-Control": "max-age=60"},
                        body=body.decode())
        if path == "tonight.json":
            day = q.get("day", "")
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
                body = s3.get_object(Bucket=BUCKET, Key=f"results/{day.replace('-', '')}.json")["Body"].read()
            else:
                body = s3.get_object(Bucket=SITE, Key="tonight.json")["Body"].read()
            return dict(statusCode=200, headers={"Content-Type": TYPES[".json"], "Cache-Control": "max-age=60"},
                        body=body.decode())
        if path == "status.json":
            return dict(statusCode=200, headers={"Content-Type": TYPES[".json"], "Cache-Control": "max-age=60"},
                        body=json.dumps(_status()))
        if path == "days.json":  # replay days available, for the date picker
            keys = [o["Key"] for p in s3.get_paginator("list_objects_v2").paginate(Bucket=BUCKET, Prefix="results/")
                    for o in p.get("Contents", [])]
            fmt = lambda k: f"{k[:4]}-{k[4:6]}-{k[6:8]}"
            days = sorted(fmt(k[8:16]) for k in keys if re.fullmatch(r"results/\d{8}\.json", k))
            plans = sorted(fmt(k[13:21]) for k in keys if re.fullmatch(r"results/plan_\d{8}\.json", k))
            return dict(statusCode=200, headers={"Content-Type": TYPES[".json"], "Cache-Control": "max-age=600"},
                        body=json.dumps({"replays": days, "plans": plans}))
        if path == "config.json":
            return dict(statusCode=200, headers={"Content-Type": TYPES[".json"]},
                        body=json.dumps({"agent_url": os.environ.get("AGENT_URL", "")}))
        if path in ("index.html", "borders.json", "evidence.json", "districts.json"):
            with open(os.path.join(STATIC, path), encoding="utf-8") as f:
                return dict(statusCode=200, headers={"Content-Type": TYPES[os.path.splitext(path)[1]],
                                                     "Cache-Control": "max-age=300"}, body=f.read())
    except s3.exceptions.NoSuchKey:
        pass
    return dict(statusCode=404, headers={"Content-Type": "text/plain"}, body="Not found")


def _rain_cells(day):
    """Rain (mm) on day-1 and day per risk cell, from the Open-Meteo forecast (which serves recent past days)."""
    import requests
    from saanjh import risk
    lats, lons = np.arange(28.0, 33.01, 0.5), np.arange(73.5, 78.01, 0.5)
    pts = np.array(np.meshgrid(lats, lons, indexing="ij")).reshape(2, -1).T
    vals = []
    for i in range(0, len(pts), 50):
        q = pts[i:i + 50]
        js = requests.get("https://api.open-meteo.com/v1/forecast", timeout=60, params=dict(
            latitude=",".join(f"{x:.2f}" for x in q[:, 0]), longitude=",".join(f"{x:.2f}" for x in q[:, 1]),
            daily="precipitation_sum", timezone="Asia/Kolkata", past_days=1, forecast_days=1)).json()
        vals += [c["daily"]["precipitation_sum"][:2] for c in (js if isinstance(js, list) else [js])]
    p = np.nan_to_num(np.array(vals, float)).reshape(len(lats), len(lons), 2)
    clat, clon = risk.centres()
    iy = np.clip(np.round((clat - lats[0]) / 0.5).astype(int), 0, len(lats) - 1)
    ix = np.clip(np.round((clon - lons[0]) / 0.5).astype(int), 0, len(lons) - 1)
    return p[iy, ix, 0], p[iy, ix, 1]


def plan_handler(event, _ctx=None):
    """Noon plan for tonight: where tonight's fires are likely and where K teams cover the most expected harm.
    Uses only what is known at noon: GK-2A fires of the last 7 days, yesterday's VIIRS count, rain, last season."""
    from saanjh import risk
    day = (datetime.fromisoformat(event["day"]) if "day" in event else
           (datetime.now(timezone.utc).replace(tzinfo=None) + pipeline.IST)).replace(hour=0, minute=0, second=0, microsecond=0)
    lat, lon = gk2a.crop_grid()
    hist = []
    for k in range(1, 8):
        det, _ = _detections(day - timedelta(days=k))
        hist.append(risk.grid_sum(lat[det.i, det.j], lon[det.i, det.j], det.frp * 600) if len(det)
                    else np.zeros((risk.NY, risk.NX)))
    v = _viirs(day - timedelta(days=1), replay=False)
    vg = risk.grid_sum(v.latitude, v.longitude) if v is not None and len(v) else np.zeros((risk.NY, risk.NX))
    asset = lambda f: os.path.join(ASSETS, f)
    mask, clim = np.load(asset("farmland_mask.npy")), np.load(asset("clim_2025.npy"))
    models = (dict(np.load(asset("risk_model.npz"))), dict(np.load(asset("energy_model.npz"))))
    X = risk.features(np.stack(hist), vg, clim, _rain_cells(day), (day - timedelta(days=1) - day.replace(month=10, day=15)).days,
                      day.weekday())
    met = smoke.Met.era5(day - timedelta(days=1), day + timedelta(days=2), forecast=True)
    clat, clon = risk.centres()
    t = smoke.hours_since(met, day + timedelta(hours=17 - 5.5))
    _, expo = smoke.run(met, clat[mask], clon[mask], np.full(int(mask.sum()), t), np.ones(int(mask.sum())), hours=30, n_per=8)
    pr, eh = np.zeros(mask.shape), np.zeros(mask.shape)
    pr[mask] = risk.predict_proba(models[0], X[mask])
    eh[mask] = risk.expected_harm(models, X[mask], expo)
    body = risk.payload(day.date(), eh, pr)
    body["generated"] = f"{datetime.now(timezone.utc):%Y-%m-%dT%H:%MZ}"
    _put("plan.json", json.dumps(body, separators=(",", ":")), bucket=SITE)
    metric(PlanRuns=(1, "Count"))
    return {"day": body["day"], "teams": len(body["teams"]), "top_share": body["teams"][0]["share"] if body["teams"] else 0}


_STATUS = {"at": 0, "body": None}


def _status():
    """Live pipeline health for the page: last image processed, throughput, latency, errors, alarms, cost."""
    import time as _t
    if _t.time() - _STATUS["at"] < 60 and _STATUS["body"]:
        return _STATUS["body"]
    cw = boto3.client("cloudwatch")
    now = datetime.now(timezone.utc)
    q = lambda i, ns, name, stat, dims, period=86400, start=timedelta(days=1): dict(
        Id=i, MetricStat=dict(Metric=dict(Namespace=ns, MetricName=name, Dimensions=[dict(Name=k, Value=v) for k, v in dims.items()]),
                              Period=period, Stat=stat), ReturnData=True)
    fns = {k: os.environ.get(k, "") for k in ("DETECT_FN", "MODEL_FN", "PLAN_FN", "AGENT_FN")}
    queries = [q("scans", "Saanjh", "ScansProcessed", "Sum", {"Stage": "live"}),
               q("dets", "Saanjh", "Detections", "Sum", {"Stage": "live"}),
               q("lat", "Saanjh", "ScanLatency", "p50", {"Stage": "live"}, 3 * 3600),
               q("proc", "Saanjh", "ProcessSeconds", "p50", {"Stage": "live"})]
    for k, fn in fns.items():
        if fn:
            queries += [q(f"err_{k.lower()}", "AWS/Lambda", "Errors", "Sum", {"FunctionName": fn}),
                        q(f"dur_{k.lower()}", "AWS/Lambda", "Duration", "Sum", {"FunctionName": fn}),
                        q(f"inv_{k.lower()}", "AWS/Lambda", "Invocations", "Sum", {"FunctionName": fn})]
    res = cw.get_metric_data(MetricDataQueries=queries, StartTime=now - timedelta(days=1), EndTime=now)
    val = {r["Id"]: (r["Values"][0] if r["Values"] else 0.0) for r in res["MetricDataResults"]}
    mem = {"DETECT_FN": 2048, "MODEL_FN": 3008, "PLAN_FN": 3008, "AGENT_FN": 512}
    gbs = sum(val.get(f"dur_{k.lower()}", 0) / 1000 * mem[k] / 1024 for k in fns)
    keys = [o for d in (now - timedelta(days=1), now) for p in s3.get_paginator("list_objects_v2").paginate(
            Bucket=BUCKET, Prefix=f"detections/{d:%Y%m%d}/") for o in p.get("Contents", [])]
    recent = [o for o in keys if o["LastModified"] > now - timedelta(days=1)]
    last = max((o["Key"] for o in keys), default=None)
    alarms = cw.describe_alarms(AlarmNamePrefix="saanjh-")["MetricAlarms"]
    body = dict(
        generated=f"{now:%Y-%m-%dT%H:%MZ}",
        last_image=f"{last[11:15]}-{last[15:17]}-{last[17:19]}T{last[20:22]}:{last[22:24]}:00Z" if last else None,
        images_24h=max(int(val["scans"]), len(recent)), detections_24h=int(val["dets"]),
        latency_p50_min=round(val["lat"] / 60, 1), process_p50_s=round(val["proc"], 1),
        invocations_24h=int(sum(val.get(f"inv_{k.lower()}", 0) for k in fns)),
        errors_24h=int(sum(val.get(f"err_{k.lower()}", 0) for k in fns)),
        lambda_cost_24h_usd=round(gbs * 0.0000133334 + val.get("inv_detect_fn", 0) * 2e-7, 3),
        alarms=[dict(name=a["AlarmName"].replace("saanjh-", ""), state=a["StateValue"]) for a in alarms])
    _STATUS.update(at=_t.time(), body=body)
    return body
