"""Write the page's JSON for one replayed day from the local cache: export_day.py 2024-11-18 site/tonight.json"""
import json
import sys
from datetime import datetime, timedelta

import pandas as pd

from saanjh import pipeline, smoke

day = datetime.fromisoformat(sys.argv[1])
v = pd.read_csv("data/firms/viirs_snpp_2024_punjab_both_octnov.csv")
v = v[v.acq_date == sys.argv[1]]
ev = pipeline.fire_events(day, viirs=v)
met = smoke.Met.era5(day - timedelta(days=1), day + timedelta(days=2))
ranked, towns, conc, t0 = pipeline.tonight(day, met, ev, viirs=v)
out = pipeline.summary(day, ranked, towns, conc, t0, n_scans=15, replay=True, events=ev)
json.dump(out, open(sys.argv[2], "w"), separators=(",", ":"))
print(out["stats"])
