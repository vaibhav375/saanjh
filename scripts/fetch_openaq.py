"""Hourly PM2.5 for the chosen CPCB stations from the OpenAQ v3 API (key: OPENAQ_API_KEY or .env).
OpenAQ's public S3 archive has gaps for these stations, the API does not.

usage: fetch_openaq.py START END OUT.csv   (dates inclusive; stations from data/openaq_stations.csv)
"""
import os
import sys
import time

import certifi
import pandas as pd
import requests


def api_key():
    if os.environ.get("OPENAQ_API_KEY"):
        return os.environ["OPENAQ_API_KEY"]
    for line in open(os.path.join(os.path.dirname(__file__), "..", ".env")):
        if line.startswith("OPENAQ_API_KEY="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("set OPENAQ_API_KEY")


st = pd.read_csv("data/openaq_stations.csv", dtype={"pm25_sensor": str}).dropna(subset=["pm25_sensor"])
a, b = sys.argv[1], sys.argv[2]
http = requests.Session()
http.headers["X-API-Key"] = api_key()
rows = []
pairs = [(loc, int(s)) for loc, ss in zip(st.id, st.pm25_sensor) for s in ss.split(";")]  # stations have old and new sensor ids
for loc, sensor in pairs:
    page = 1
    while True:
        for attempt in range(6):
            r = http.get(f"https://api.openaq.org/v3/sensors/{sensor}/hours", timeout=60, verify=certifi.where(),
                         params=dict(datetime_from=f"{a}T00:00:00Z", datetime_to=f"{b}T23:59:59Z", limit=1000, page=page))
            if r.status_code != 429:
                break
            time.sleep(15 * (attempt + 1))  # free tier: 60 requests/minute
        if not r.ok:
            print("skip", loc, r.status_code)
            break
        res = r.json()["results"]
        rows += [(loc, x["period"]["datetimeFrom"]["utc"], x["value"]) for x in res]
        time.sleep(1.1)
        if len(res) < 1000:
            break
        page += 1
out = pd.DataFrame(rows, columns=["location_id", "datetime", "value"]).drop_duplicates(["location_id", "datetime"])
out.to_csv(sys.argv[3], index=False)
print(len(st), "stations,", out.location_id.nunique(), "with data,", len(out), "hourly values")
