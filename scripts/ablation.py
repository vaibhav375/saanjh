"""N4, the ablation: does adding the fires the polar satellites miss explain more of the PM2.5 measured
downwind?

Two emission inventories, same smoke model, same ERA5 weather, 15 Oct - 30 Nov:
  A "overpass":  VIIRS fires at ~13:30, spread over the day with the midday-peaked diurnal profile that
                 operational inventories assume (Gaussian, peak 13:30 IST, sigma 2 h).
  B "saanjh":    GK-2A fire events at the times they were actually seen (10-minute replay on AWS).
  C "hybrid":    A plus only the GK-2A fires the overpass missed, i.e. Saanjh added to today's inventory.
Modelled farm smoke is sampled hourly at CPCB stations. Each station's mean diurnal cycle is removed
from observations and model (so night-time inversions of local pollution do not count as skill),
skill is the correlation of daily station-mean anomalies, by region and month, with a bootstrap over days.

usage: ablation.py YEAR [--eval]   (needs data/detections/<YYYYMMDD>/ from the cloud replay, data/pm25_<YEAR>.csv;
                                   --eval re-scores the saved model run without re-simulating)
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
series = {k: np.zeros((hours, len(st))) for k in ("A", "B", "U")}


def add(name, conc, t0):
    k0 = int(round((t0 - start) / timedelta(hours=1)))
    for k in range(conc.shape[0]):
        if 0 <= k0 + k < hours:
            series[name][k0 + k] += conc[k][iy, ix]


def overpass_inventory(v, day):
    """Inventory A: the same overpass inventory the live system uses (pipeline.overpass_sources)."""
    src, rel = pipeline.overpass_sources(day, v)
    t = np.array([smoke.hours_since(met, pd.Timestamp(x).to_pydatetime()) for x in rel.t])
    return src.lat.to_numpy()[rel.row], src.lon.to_numpy()[rel.row], t, rel.kg.to_numpy()


if "--eval" not in sys.argv:
    d = start
    while d <= end:
        v = viirs[viirs.acq_date == f"{d:%Y-%m-%d}"]
        files = sorted(glob.glob(f"data/detections/{d:%Y%m%d}/*.csv"))
        det = pd.concat([pd.read_csv(f, parse_dates=["t"]) for f in files]) if files else pd.DataFrame()
        if len(det):
            ev = pipeline.fire_events(d, step_min=10, viirs=v, detections=det)
            _, _, conc, t0 = pipeline.tonight(d, met, ev)
            add("B", conc, t0)
            missed = ev[~ev.counted]
            if len(missed):
                _, _, conc, t0 = pipeline.tonight(d, met, missed)
                add("U", conc, t0)
        if len(v):
            lat, lon, t, m = overpass_inventory(v, d)
            conc, _ = smoke.run(met, lat, lon, t, m, hours=30, n_per=10)
            add("A", conc, met.t0 + timedelta(hours=float(t.min())))
        print(f"{d:%Y-%m-%d} events={len(det) and len(ev)} viirs={len(v)}", flush=True)
        d += timedelta(days=1)

idx = pd.date_range(start, periods=hours, freq="h", tz="UTC")
if "--eval" in sys.argv:
    model = pd.read_pickle(f"results/ablation_model_{year}.pkl")
else:
    model = pd.concat({k: pd.DataFrame(a, index=idx, columns=st.id) for k, a in series.items()}, axis=1)
    model.to_pickle(f"results/ablation_model_{year}.pkl")

obs = pd.read_csv(f"data/pm25_{year}.csv", parse_dates=["datetime"])
# OpenAQ stamps each hourly mean with its start (xx:30 UTC in India); use the hour's midpoint.
obs["datetime"] = (obs.datetime + pd.Timedelta(minutes=30)).dt.floor("h")
obs = obs[(obs.value > 0) & (obs.value < 1500)].pivot_table(index="datetime", columns="location_id", values="value")
obs = obs.reindex(index=idx, columns=st.id)  # stations with no data become empty columns


def anomalies(df):
    """Remove each station's mean diurnal cycle (by IST hour), then its mean."""
    hod = (df.index + pd.Timedelta(hours=5, minutes=30)).hour
    return df - df.groupby(hod).transform("mean")


# Daily means per station, station mean removed: does the day-to-day smoke the inventory predicts
# track the day-to-day PM2.5 measured? Scale-free (Pearson r), with a bootstrap over days for B - A.
st["region"] = np.where(st.lat.between(28.3, 28.95) & st.lon.between(76.8, 77.55), "Delhi-NCR", "Punjab/Haryana/W-UP")
daily = {k: (v.resample("D").mean() - v.resample("D").mean().mean()) for k, v in
         {"obs": obs, "A": model["A"], "B": model["B"], "C": model["A"] + model["U"]}.items()}
rng = np.random.default_rng(0)
rows = []
for region in ("Punjab/Haryana/W-UP", "Delhi-NCR", "all"):
    cols = st.id[st.region == region] if region != "all" else st.id
    for month, sel in (("Oct", daily["obs"].index.month == 10), ("Nov", daily["obs"].index.month == 11), ("season", slice(None))):
        frame = pd.concat({k: daily[k].loc[sel, cols].stack() for k in ("obs", "A", "B", "C")}, axis=1).dropna()
        days = frame.index.get_level_values(0).unique()
        r = {k: frame.obs.corr(frame[k]) for k in ("A", "B", "C")}
        boot = {"B": [], "C": []}
        for _ in range(500):
            pick = frame.loc[rng.choice(days, len(days))]
            for k in boot:
                boot[k].append(pick.obs.corr(pick[k]) - pick.obs.corr(pick.A))
        ci = {k: "[%+.2f, %+.2f]" % tuple(np.percentile(v, [2.5, 97.5])) for k, v in boot.items()}
        rows.append(dict(region=region, period=month, stations=frame.index.get_level_values(1).nunique(),
                         r_overpass=r["A"], r_saanjh=r["B"], r_hybrid=r["C"],
                         gain_saanjh=r["B"] - r["A"], ci_saanjh=ci["B"], gain_hybrid=r["C"] - r["A"], ci_hybrid=ci["C"]))
res = pd.DataFrame(rows)
res.to_csv(f"results/ablation_{year}.csv", index=False)
print(res.round(3).to_string(index=False))
