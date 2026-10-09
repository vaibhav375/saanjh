"""N4, the ablation: does adding the fires the polar satellites miss explain more of the PM2.5 measured
downwind?

Two emission inventories, same smoke model, same ERA5 weather, 15 Oct - 30 Nov:
  A "overpass":  VIIRS fires at ~13:30, spread over the day with the midday-peaked diurnal profile that
                 operational inventories assume (Gaussian, peak 13:30 IST, sigma 2 h).
  B "saanjh":    GK-2A fire events at the times they were actually seen (10-minute replay on AWS).
Modelled farm smoke is sampled hourly at CPCB stations. Each station's mean diurnal cycle is removed
from observations and model (so night-time inversions of local pollution do not count as skill),
the fit is a single pooled slope with station means removed, fitted on October, tested on November.

usage: ablation.py YEAR        (needs data/detections/<YYYYMMDD>/ from the cloud replay, data/pm25_<YEAR>.csv)
"""
import glob
import sys
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from saanjh import pipeline, smoke

year = int(sys.argv[1])
start, end = datetime(year, 10, 15), datetime(year, 11, 30)
met = smoke.Met.era5(start - timedelta(days=2), end + timedelta(days=3))
st = pd.read_csv("data/openaq_stations.csv")
iy = ((st.lat - smoke.LAT0) / smoke.D).astype(int).to_numpy()
ix = ((st.lon - smoke.LON0) / smoke.D).astype(int).to_numpy()
viirs = pd.read_csv("data/firms/viirs_snpp_punjab_both_2024_2025.csv")
hours = int((end - start).days * 24 + 48)
series = {k: np.zeros((hours, len(st))) for k in ("A", "B")}


def add(name, conc, t0):
    k0 = int(round((t0 - start) / timedelta(hours=1)))
    for k in range(conc.shape[0]):
        if 0 <= k0 + k < hours:
            series[name][k0 + k] += conc[k][iy, ix]


def overpass_inventory(v, day):
    """VIIRS fires on the 0.05 deg grid, released 09-19 IST with a midday-peaked profile."""
    g = v.assign(cy=((v.latitude - smoke.LAT0) / smoke.D).astype(int), cx=((v.longitude - smoke.LON0) / smoke.D).astype(int))
    cells = g.groupby(["cy", "cx"]).frp.sum().reset_index()
    lat, lon, t, m = [], [], [], []
    for h in range(9, 20):
        w = np.exp(-((h + 0.5 - 13.5) ** 2) / (2 * 2.0 ** 2))
        lat += list(smoke.LAT0 + (cells.cy + 0.5) * smoke.D)
        lon += list(smoke.LON0 + (cells.cx + 0.5) * smoke.D)
        t += [smoke.hours_since(met, day + timedelta(hours=h - 5.5))] * len(cells)
        m += list(cells.frp * w * 3600 * pipeline.KG_PER_MJ * pipeline.EF_PM25)  # MW*s = MJ
    return np.array(lat), np.array(lon), np.array(t), np.array(m)


d = start
while d <= end:
    v = viirs[viirs.acq_date == f"{d:%Y-%m-%d}"]
    files = sorted(glob.glob(f"data/detections/{d:%Y%m%d}/*.csv"))
    det = pd.concat([pd.read_csv(f, parse_dates=["t"]) for f in files]) if files else pd.DataFrame()
    if len(det):
        ev = pipeline.fire_events(d, step_min=10, viirs=v, detections=det)
        _, _, conc, t0 = pipeline.tonight(d, met, ev)
        add("B", conc, t0)
    if len(v):
        lat, lon, t, m = overpass_inventory(v, d)
        conc, _ = smoke.run(met, lat, lon, t, m, hours=30, n_per=10)
        add("A", conc, met.t0 + timedelta(hours=float(t.min())))
    print(f"{d:%Y-%m-%d} events={len(det) and len(ev)} viirs={len(v)}", flush=True)
    d += timedelta(days=1)

idx = pd.date_range(start, periods=hours, freq="h", tz="UTC")
model = pd.concat({k: pd.DataFrame(a, index=idx, columns=st.id) for k, a in series.items()}, axis=1)
model.to_pickle(f"results/ablation_model_{year}.pkl")

obs = pd.read_csv(f"data/pm25_{year}.csv", parse_dates=["datetime"])
obs = obs[(obs.value > 0) & (obs.value < 1500)].pivot_table(index="datetime", columns="location_id", values="value")
obs = obs.reindex(idx)


def anomalies(df):
    """Remove each station's mean diurnal cycle (by IST hour), then its mean."""
    hod = (df.index + pd.Timedelta(hours=5, minutes=30)).hour
    return df - df.groupby(hod).transform("mean")


rows = []
o = anomalies(obs)
for name in ("A", "B"):
    m = anomalies(model[name])
    for test in (False, True):
        sel = (idx >= pd.Timestamp(year, 11, 1, tz="UTC")) if test else (idx < pd.Timestamp(year, 11, 1, tz="UTC"))
        fit = ~sel
        x, y = m[fit].stack(), o[fit].stack()
        j = x.index.intersection(y.index)
        slope = float((x[j] * y[j]).sum() / (x[j] ** 2).sum())
        xt, yt = m[sel].stack(), o[sel].stack()
        jt = xt.index.intersection(yt.index)
        resid = yt[jt] - slope * xt[jt]
        r2 = 1 - float((resid ** 2).sum() / (yt[jt] ** 2).sum())
        daily = pd.DataFrame({"o": o[sel].mean(axis=1), "m": m[sel].mean(axis=1)}).resample("D").mean().dropna()
        rows.append(dict(model=name, period="Nov (test)" if test else "Oct (fit)", slope=slope, r2=r2,
                         r_daily=float(daily.o.corr(daily.m)), n=len(jt)))
res = pd.DataFrame(rows)
res.to_csv(f"results/ablation_{year}.csv", index=False)
print(res.round(3).to_string(index=False))
