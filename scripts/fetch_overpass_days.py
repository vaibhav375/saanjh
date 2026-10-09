"""Cache GK-2A scans needed to score the detector against VIIRS: 5 morning baseline scans
(09:00-11:00 IST) and the two scans bracketing each day's median VIIRS overpass."""
import sys
from datetime import datetime, timedelta

import pandas as pd

from saanjh import gk2a

viirs = pd.read_csv(sys.argv[1])
days = int(sys.argv[2]) if len(sys.argv) > 2 else 10
top = viirs.groupby("acq_date").acq_time.agg(["size", "median"]).sort_values("size", ascending=False).head(days)
jobs = []
for d, row in top.iterrows():
    day = datetime.fromisoformat(d)
    hhmm = int(row["median"])
    t = day + timedelta(hours=hhmm // 100, minutes=hhmm % 100 // 10 * 10)
    times = [day + timedelta(hours=3, minutes=30 + 30 * i) for i in range(5)] + [t, t + timedelta(minutes=10)]
    jobs += [(b, x) for x in times for b in ("sw038", "ir112")]
res = gk2a.fetch_many(jobs, workers=16)
print(len(res), "scans,", sum(v is None for v in res.values()), "missing")
