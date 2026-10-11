"""Independent check of the evening fires: does a second satellite see fire at the same place that night?

VIIRS on S-NPP, NOAA-20 and NOAA-21 also pass at ~01:00-03:00 IST. A real evening fire (or the next field over,
lit by the same farmer) often still shows at that pass; a false alarm has no reason to. We compare the rate at
which GK-2A evening fires have a VIIRS night fire within 5 km against two baselines:
  - same place, other nights of the season (controls for hotspot geography: some villages burn every night);
  - random farmland, same night (controls for how busy that night was).
Writes results/night_check.json and prints a table for NOTES.md.
"""
import glob
import json
import os
import sys
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

sys.path.insert(0, os.path.dirname(__file__))
from fetch_viirs import fetch, map_key  # noqa: E402
from saanjh import pipeline, risk  # noqa: E402

SEASON = {y: (date(y, 10, 15), date(y, 11, 30)) for y in (2024, 2025)}
DAY = {2024: "data/firms/viirs_snpp_2024_punjab_both_octnov.csv", 2025: "data/firms/viirs_snpp_2025_punjab_both_octnov.csv"}
SOURCES = ["VIIRS_SNPP_SP", "VIIRS_NOAA20_SP", "VIIRS_NOAA21_NRT"]
R_KM = 5.0
rng = np.random.default_rng(0)


def night_fires(y):
    """VIIRS night detections, all three satellites; acq_date d at >= 16:00 UTC is the night after day d (IST)."""
    path = f"data/firms/viirs_night_{y}.csv"
    if not os.path.exists(path):
        a, b = SEASON[y]
        v = pd.concat([fetch(s, a, b, map_key()) for s in SOURCES])
        v = v[(v.daynight == "N") & (v.acq_time >= 1600)]
        v.to_csv(path, index=False)
    return pd.read_csv(path)


def km(lat, lon):
    return np.c_[np.asarray(lat) * 111.2, np.asarray(lon) * 111.2 * np.cos(np.radians(30.5))]


def hit(trees, d, lat, lon):
    t = trees.get(d)
    if t is None:
        return np.zeros(len(lat), bool)
    return np.isfinite(t.query(km(lat, lon), distance_upper_bound=R_KM)[0])


mask = np.load("saanjh/assets/farmland_mask.npy")
fr, fc = np.nonzero(mask)
rows = []
for y, (a, b) in SEASON.items():
    nf, vday = night_fires(y), pd.read_csv(DAY[y])
    trees = {d: cKDTree(km(g.latitude, g.longitude)) for d, g in nf.groupby("acq_date")}
    days = [a + timedelta(n) for n in range((b - a).days + 1)]
    for d in days:
        files = glob.glob(f"data/detections/{d:%Y%m%d}/*.csv")
        if not files or f"{d}" not in trees:
            continue
        det = pd.concat([pd.read_csv(f, parse_dates=["t"]) for f in files])
        if det.empty:
            continue
        ev = pipeline.fire_events(datetime(d.year, d.month, d.day), step_min=10, viirs=vday[vday.acq_date == f"{d}"], detections=det)
        if ev.empty:
            continue
        first_ist = ev["first"] + pipeline.IST
        ev["group"] = np.where(ev.counted, "counted", np.where(first_ist.dt.hour >= 14, "evening", "other"))
        ev["night"] = hit(trees, f"{d}", ev.lat, ev.lon)
        others = [f"{o}" for o in days if o != d and f"{o}" in trees]
        ev["other_nights"] = np.mean([hit(trees, o, ev.lat, ev.lon) for o in others], axis=0)
        k = rng.integers(0, len(fr), len(ev))
        rlat = risk.LAT0 + (fr[k] + rng.random(len(ev))) * risk.D
        rlon = risk.LON0 + (fc[k] + rng.random(len(ev))) * risk.D
        ev["random_farm"] = hit(trees, f"{d}", rlat, rlon)
        ev["year"], ev["day"], ev["hour_ist"] = y, f"{d}", first_ist.dt.hour
        rows.append(ev[["year", "day", "group", "hour_ist", "frp_peak", "fre_mj", "scans", "z_max", "lat", "lon", "night", "other_nights", "random_farm"]])

ev = pd.concat(rows)
ev.to_csv("data/night_events.csv", index=False)
days = ev.day.unique()


def rates(sub):
    """Energy-weighted share of fires with a night hit, for the fire and its two baselines."""
    w = sub.fre_mj.to_numpy()
    return np.array([(sub[c].to_numpy() * w).sum() for c in ("night", "other_nights", "random_farm")]) / max(w.sum(), 1e-9)


def boot(sub, n=1000):
    """95% CI of the lifts over both baselines, resampling nights."""
    g = {d: x for d, x in sub.groupby("day")}
    lifts = []
    for _ in range(n):
        s = pd.concat([g[d] for d in rng.choice(days, len(days)) if d in g])
        r = rates(s)
        lifts.append([r[0] / max(r[1], 1e-9), r[0] / max(r[2], 1e-9)])
    return np.round(np.percentile(lifts, [2.5, 97.5], axis=0).T, 2).tolist()


out = {}
ev_ = ev[ev.group == "evening"]
print(f"{'fires (energy-weighted)':30s} {'n':>6s} {'energy':>6s} {'night':>6s} {'same place':>10s} {'random':>6s}  lift vs same place / vs random farm [95% CI]")
for name, sub in [("Evening, first seen >=14 IST", ev_), ("  seen in >=3 scans (30 min)", ev_[ev_.scans >= 3]),
                  ("  seen in >=6 scans (1 h)", ev_[ev_.scans >= 6]), ("  first seen >=18 IST", ev_[ev_.hour_ist >= 18]),
                  ("  single scan", ev_[ev_.scans == 1]), ("Counted by VIIRS at 13:30", ev[ev.group == "counted"])]:
    r, ci = rates(sub), boot(sub)
    out[name.strip()] = dict(n=int(len(sub)), energy_share=round(float(sub.fre_mj.sum() / ev_.fre_mj.sum()), 3),
                             night=round(r[0], 4), same_place=round(r[1], 4), random_farm=round(r[2], 4),
                             lift_same_place=round(r[0] / r[1], 2), ci_same_place=ci[0],
                             lift_random=round(r[0] / r[2], 2), ci_random=ci[1])
    o = out[name.strip()]
    print(f"{name:30s} {o['n']:6d} {o['energy_share']:6.0%} {r[0]:6.1%} {r[1]:10.1%} {r[2]:6.1%}  "
          f"{o['lift_same_place']:.1f} {ci[0]} / {o['lift_random']:.1f} {ci[1]}")
json.dump(dict(radius_km=R_KM, sources=SOURCES, nights=int(len(days)), weighting="fire radiative energy", groups=out),
          open("results/night_check.json", "w"), indent=1)
