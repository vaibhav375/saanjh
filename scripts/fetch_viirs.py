"""VIIRS active fires for the model area from the FIRMS area API (key from FIRMS_MAP_KEY or .env).

usage: fetch_viirs.py SOURCE START END OUT.csv   e.g. VIIRS_SNPP_SP 2025-10-15 2025-11-30 data/firms/x.csv
"""
import io
import os
import sys
import time
from datetime import date, timedelta

import pandas as pd
import requests

BBOX = "71,26,81,34"


def map_key():
    if os.environ.get("FIRMS_MAP_KEY"):
        return os.environ["FIRMS_MAP_KEY"]
    for line in open(os.path.join(os.path.dirname(__file__), "..", ".env")):
        if line.startswith("FIRMS_MAP_KEY="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("set FIRMS_MAP_KEY")


def fetch(source, start: date, end: date, key):
    frames, d = [], start
    while d <= end:
        n = min(5, (end - d).days + 1)
        r = requests.get(f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{key}/{source}/{BBOX}/{n}/{d}", timeout=120)
        r.raise_for_status()
        if r.text.strip() and not r.text.startswith("Invalid"):
            frames.append(pd.read_csv(io.StringIO(r.text)))
        d += timedelta(days=n)
        time.sleep(1)
    return pd.concat(frames) if frames else pd.DataFrame()


if __name__ == "__main__":
    src, a, b, out = sys.argv[1], date.fromisoformat(sys.argv[2]), date.fromisoformat(sys.argv[3]), sys.argv[4]
    v = fetch(src, a, b, map_key())
    v = v[(v.daynight == "D")] if "daynight" in v else v
    if "type" in v:
        v = v[v.type == 0]
    v.to_csv(out, index=False)
    print(len(v), "fires", v.acq_date.min(), v.acq_date.max())
