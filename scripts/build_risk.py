"""Train tomorrow's fire-risk model on 2024, test on 2025, and score the team planner.

Outputs: saanjh/assets/risk_model.npz (exported trees), results/risk_<...>.csv, printed summary.
Needs: data/detections/<YYYYMMDD>/ (cloud replays), VIIRS files in data/firms/, ERA5 in data/met/.
"""
import glob
import json
import os
import time
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
import requests
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.metrics import average_precision_score, roc_auc_score

from saanjh import gk2a, risk, smoke

LAT, LON = gk2a.crop_grid()
SEASON = {y: (date(y, 10, 15), date(y, 11, 30)) for y in (2024, 2025)}


def gk_daily(y):
    """GK-2A fire energy (MJ) per cell per day: frp (MW) x 600 s for every 10-minute detection."""
    out = {}
    a, b = SEASON[y]
    for n in range((b - a).days + 1):
        d = a + timedelta(n)
        g = np.zeros((risk.NY, risk.NX))
        for f in glob.glob(f"data/detections/{d:%Y%m%d}/*.csv"):
            x = pd.read_csv(f)
            if len(x):
                g += risk.grid_sum(LAT[x.i, x.j], LON[x.i, x.j], x.frp * 600)
        out[d] = g
    return out


def viirs_daily(v):
    return {datetime.fromisoformat(k).date(): risk.grid_sum(g.latitude, g.longitude) for k, g in v.groupby("acq_date")}


def clim(files, months=(10, 11)):
    v = pd.concat([pd.read_csv(f) for f in files])
    v = v[pd.to_datetime(v.acq_date).dt.month.isin(months) & (v.get("daynight", "D") == "D")]
    return risk.grid_sum(v.latitude, v.longitude)


def rain(y):
    """Daily precipitation (mm) per cell from ERA5 via Open-Meteo, cached."""
    path = f"data/met/rain_{y}.npz"
    if not os.path.exists(path):
        lats, lons = np.arange(28.0, 33.01, 0.5), np.arange(73.5, 78.01, 0.5)
        pts = np.array(np.meshgrid(lats, lons, indexing="ij")).reshape(2, -1).T
        a, b = SEASON[y]
        vals = []
        for i in range(0, len(pts), 50):
            q = pts[i:i + 50]
            for attempt in range(6):
                r = requests.get("https://archive-api.open-meteo.com/v1/era5", timeout=120, params=dict(
                    latitude=",".join(f"{x:.2f}" for x in q[:, 0]), longitude=",".join(f"{x:.2f}" for x in q[:, 1]),
                    start_date=f"{a - timedelta(7)}", end_date=f"{b + timedelta(1)}", daily="precipitation_sum",
                    timezone="Asia/Kolkata"))
                if r.ok:
                    break
                time.sleep(20 * (attempt + 1))
            js = r.json()
            vals += [c["daily"]["precipitation_sum"] for c in (js if isinstance(js, list) else [js])]
            days = (js if isinstance(js, list) else [js])[0]["daily"]["time"]
        np.savez(path, lats=lats, lons=lons, days=np.array(days), p=np.nan_to_num(np.array(vals, float)).reshape(len(lats), len(lons), -1))
    z = np.load(path)
    clat, clon = risk.centres()
    iy = np.clip(np.round((clat - z["lats"][0]) / 0.5).astype(int), 0, len(z["lats"]) - 1)
    ix = np.clip(np.round((clon - z["lons"][0]) / 0.5).astype(int), 0, len(z["lons"]) - 1)
    return {date.fromisoformat(d): z["p"][iy, ix, k] for k, d in enumerate(z["days"])}


def harm_per_kg(y, days):
    """Population exposure per kg PM2.5 released at 17:00 IST from each cell centre, per day (ERA5 weather)."""
    path = f"data/harm_per_kg_{y}.npz"
    if os.path.exists(path):
        z = np.load(path)
        return {date.fromisoformat(k): z[k] for k in z.files}
    a, b = SEASON[y]
    met = smoke.Met.era5(datetime(y, 10, 13), datetime(y, 12, 3))
    clat, clon = risk.centres()
    out = {}
    for d in days:
        t = smoke.hours_since(met, datetime(d.year, d.month, d.day) + timedelta(hours=17 - 5.5))
        _, expo = smoke.run(met, clat.ravel(), clon.ravel(), np.full(clat.size, t), np.ones(clat.size), hours=30, n_per=8)
        out[d] = expo.reshape(risk.NY, risk.NX)
    np.savez(path, **{str(k): v for k, v in out.items()})
    return out


def dataset(y, gk, vi, cl, rn):
    a, b = SEASON[y]
    rows = []
    for n in range(6, (b - a).days):
        d = a + timedelta(n)
        hist = np.stack([gk.get(d - timedelta(k), np.zeros((risk.NY, risk.NX))) for k in range(7)])
        X = risk.features(hist, vi.get(d, np.zeros((risk.NY, risk.NX))), cl,
                          (rn[d], rn[d + timedelta(1)]), (d - a).days, (d + timedelta(1)).weekday())
        rows.append((d, X, gk[d + timedelta(1)]))
    return rows


if __name__ == "__main__":
    v24 = pd.read_csv("data/firms/viirs_snpp_2024_punjab_both_octnov.csv")
    v25 = pd.read_csv("data/firms/viirs_snpp_2025_punjab_both_octnov.csv")
    gk = {y: gk_daily(y) for y in (2024, 2025)}
    vi = {2024: viirs_daily(v24), 2025: viirs_daily(v25)}
    cl = {2024: clim(["data/firms/viirs-snpp_2023_India.csv", "data/firms/viirs-snpp_2023_Pakistan.csv"]),
          2025: clim(["data/firms/viirs-snpp_2024_India.csv", "data/firms/viirs-snpp_2024_Pakistan.csv"])}
    # Farmland cells: any VIIRS fire in the two seasons before the test season (known in advance).
    mask = (cl[2024] + cl[2025]) > 0
    rn = {y: rain(y) for y in (2024, 2025)}
    data = {y: dataset(y, gk[y], vi[y], cl[y], rn[y]) for y in (2024, 2025)}
    print("farmland cells:", int(mask.sum()))

    def stack(y):
        X = np.concatenate([X[mask] for _, X, _ in data[y]])
        e = np.concatenate([e[mask] for _, _, e in data[y]])
        return X, e

    Xtr, etr = stack(2024)
    Xte, ete = stack(2025)
    clf = HistGradientBoostingClassifier(max_iter=200, learning_rate=0.05, max_leaf_nodes=31,
                                         l2_regularization=1.0, random_state=0).fit(Xtr, etr > 0)
    reg = HistGradientBoostingRegressor(max_iter=200, learning_rate=0.05, max_leaf_nodes=31, l2_regularization=1.0,
                                        random_state=0).fit(Xtr[etr > 0], np.log1p(etr[etr > 0]))
    p = clf.predict_proba(Xte)[:, 1]
    m, mr = risk.export_model(clf), risk.export_model(reg)
    os.makedirs("saanjh/assets", exist_ok=True)
    np.savez_compressed("saanjh/assets/risk_model.npz", **m)
    np.savez_compressed("saanjh/assets/energy_model.npz", **mr)
    assert np.allclose(risk.predict_proba(m, Xte), p, atol=1e-9), "numpy tree export disagrees with sklearn"
    assert np.allclose(risk.predict_raw(mr, Xte), reg.predict(Xte), atol=1e-9), "regressor export disagrees"
    print(f"2025 held out: base rate {np.mean(ete > 0):.3f}, ROC AUC {roc_auc_score(ete > 0, p):.3f}, "
          f"average precision {average_precision_score(ete > 0, p):.3f} "
          f"(yesterday's VIIRS count alone: AUC {roc_auc_score(ete > 0, Xte[:, 6]):.3f}, "
          f"AP {average_precision_score(ete > 0, Xte[:, 6]):.3f})")

    # Team placement on the 2025 days: share of next-day fire energy and of next-day smoke harm covered.
    hw = harm_per_kg(2025, [d + timedelta(1) for d, _, _ in data[2025]])
    rows = []
    for d, X, e_next in data[2025]:
        pr, eh = np.zeros((risk.NY, risk.NX)), np.zeros((risk.NY, risk.NX))
        pr[mask] = risk.predict_proba(m, X[mask])
        harm_next = e_next * hw[d + timedelta(1)]  # realised exposure if each MJ released at dusk
        hw_fc = hw[d + timedelta(1)]  # (the live system uses the forecast weather here)
        eh[mask] = risk.expected_harm((m, mr), X[mask], hw_fc[mask])
        methods = {"saanjh: expected harm": eh, "saanjh: risk only": pr * mask,
                   "chase yesterday's VIIRS fires": X[..., 6] * mask, "yesterday's GK-2A fires": X[..., 0] * mask,
                   "last season's hotspots": X[..., 9] * mask}
        for k in (10, 20):
            for name, score in methods.items():
                cov = risk.covered(risk.plan(score, k))
                rows.append(dict(day=str(d), k=k, method=name,
                                 energy=e_next[cov].sum() / max(e_next.sum(), 1e-9),
                                 harm=harm_next[cov].sum() / max(harm_next.sum(), 1e-9), total=e_next.sum()))
    r = pd.DataFrame(rows)
    r = r[r.total > 0]
    r.to_csv("results/risk_planner_2025.csv", index=False)
    # Energy-weighted across days (busy days matter more), with a bootstrap over days.
    rng = np.random.default_rng(0)
    print("\nteams  method                              next-day fire energy covered   next-day smoke harm covered")
    for k in (10, 20):
        for name in r.method.unique():
            s = r[(r.k == k) & (r.method == name)]
            w = s.total / s.total.sum()
            boot = [np.average(s.harm.iloc[i], weights=w.iloc[i]) for i in
                    (rng.integers(0, len(s), len(s)) for _ in range(300))]
            print(f"{k:5d}  {name:34s}  {np.average(s.energy, weights=w):6.1%}                       "
                  f"{np.average(s.harm, weights=w):6.1%} [{np.percentile(boot, 2.5):.0%}-{np.percentile(boot, 97.5):.0%}]")
    json.dump({"features": risk.FEATURES, "mask_cells": int(mask.sum())}, open("results/risk_model_meta.json", "w"))
    # Replay plans for the page: the noon plan for each 2025 evening, with that evening's actual fires.
    os.makedirs("data/plans", exist_ok=True)
    for d, X, e_next in data[2025]:
        tonight = d + timedelta(1)
        pr, eh = np.zeros((risk.NY, risk.NX)), np.zeros((risk.NY, risk.NX))
        pr[mask] = risk.predict_proba(m, X[mask])
        eh[mask] = risk.expected_harm((m, mr), X[mask], hw[tonight][mask])
        json.dump(risk.payload(tonight, eh, pr, actual=e_next), open(f"data/plans/plan_{tonight:%Y%m%d}.json", "w"),
                  separators=(",", ":"))
    np.save("saanjh/assets/clim_2025.npy", risk.grid_sum(v25.latitude, v25.longitude))  # "last season" for 2026
    np.save("saanjh/assets/farmland_mask.npy", mask)
