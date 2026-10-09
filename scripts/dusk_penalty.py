"""N3, the dusk penalty: population exposure from the same 1 kg of PM2.5 released at 13:00 vs 17:00 IST
from real fire locations, every day of a window, under that day's ERA5 meteorology.

usage: dusk_penalty.py START END [h_min ...]   (dates YYYY-MM-DD, UTC days)
"""
import sys
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from saanjh import smoke

start, end = (datetime.fromisoformat(a) for a in sys.argv[1:3])
h_mins = [float(x) for x in sys.argv[3:]] or [smoke.H_MIN]
met = smoke.Met.era5(start, end + timedelta(days=2))
v = pd.read_csv("data/firms/viirs_snpp_2024_northindia_octnov.csv")
v = v[v.latitude.between(29.5, 32.5) & v.longitude.between(73.8, 77.5)]
src = v.sample(150, random_state=0)[["latitude", "longitude"]].to_numpy()
rows = []
for h_min in h_mins:
    d = start
    while d <= end:
        e = {}
        for ist in (13, 17):
            t = smoke.hours_since(met, d + timedelta(hours=ist - 5.5))
            _, expo = smoke.run(met, src[:, 0], src[:, 1], np.full(len(src), t), np.ones(len(src)),
                                hours=36, n_per=30, h_min=h_min)
            e[ist] = expo.sum()
        rows.append(dict(day=f"{d:%Y-%m-%d}", h_min=h_min, e13=e[13], e17=e[17], ratio=e[17] / e[13]))
        print(rows[-1], flush=True)
        d += timedelta(days=1)
r = pd.DataFrame(rows)
r.to_csv(f"results/dusk_penalty_{start:%Y%m%d}_{end:%Y%m%d}.csv", index=False)
print(r.groupby("h_min").ratio.describe().round(2))
print("pooled ratio by h_min:", (r.groupby("h_min").e17.sum() / r.groupby("h_min").e13.sum()).round(2).to_dict())
