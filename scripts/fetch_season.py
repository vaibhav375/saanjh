"""Cache GK-2A scans for whole days: 5 morning baseline scans (09:00-11:00 IST, every 30 min) and
afternoon/evening scans 12:00-21:00 IST every `step` minutes.

usage: fetch_season.py START END [step_min]
"""
import sys
from datetime import datetime, timedelta

from saanjh import gk2a

start, end = (datetime.fromisoformat(a) for a in sys.argv[1:3])
step = int(sys.argv[3]) if len(sys.argv) > 3 else 60
jobs, d = [], start
while d <= end:
    times = [d + timedelta(hours=3, minutes=30 + 30 * i) for i in range(5)]
    times += [d + timedelta(hours=6, minutes=30) + timedelta(minutes=step * i) for i in range(9 * 60 // step + 1)]
    jobs += [(b, t) for t in times for b in ("sw038", "ir112")]
    d += timedelta(days=1)
res = gk2a.fetch_many(jobs, workers=16)
print(len(res), "scans,", sum(v is None for v in res.values()), "missing")
