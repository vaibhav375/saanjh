"""District accountability: for each Punjab/Haryana district and season, what the official count saw versus the
fire energy GK-2A saw, and how much of it came from fires that started after the polar overpass.

Writes site/districts.json (stats + simplified district outlines for the map).
Needs: data/geo/IND_ADM2.geojson (geoBoundaries), data/detections/<day>/ (cloud replays), VIIRS files.
"""
import glob
import json
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd

from saanjh import pipeline

SEASON = {y: (date(y, 10, 15), date(y, 11, 30)) for y in (2024, 2025)}
VIIRS = {2024: "data/firms/viirs_snpp_2024_punjab_both_octnov.csv", 2025: "data/firms/viirs_snpp_2025_punjab_both_octnov.csv"}


def rings_of(geom):
    polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
    return [np.array(p[0], float) for p in polys]


def inside(lat, lon, rings):
    lat, lon = np.asarray(lat, float), np.asarray(lon, float)
    hit = np.zeros(lat.shape, bool)
    for r in rings:
        x0, y0 = r[:, 0], r[:, 1]
        x1, y1 = np.roll(x0, -1), np.roll(y0, -1)
        c = ((y0[None] > lat[:, None]) != (y1[None] > lat[:, None])) & (
            lon[:, None] < (x1 - x0)[None] * (lat[:, None] - y0[None]) / np.where(y1 == y0, 1e-12, y1 - y0)[None] + x0[None])
        hit ^= c.sum(1) % 2 == 1
    return hit


# Districts of Punjab and Haryana: the state that contains each district's centroid.
dists = []
for f in json.load(open("data/geo/IND_ADM2.geojson"))["features"]:
    rings = rings_of(f["geometry"])
    allpts = np.concatenate(rings)
    cx, cy = allpts[:, 0].mean(), allpts[:, 1].mean()
    if not (73 < cx < 78.5 and 27.4 < cy < 32.8):
        continue
    st = pipeline.state_of([cy], [cx])[0]
    if st in ("Punjab (India)", "Haryana"):
        dists.append(dict(name=f["properties"]["shapeName"], state=st.replace(" (India)", ""), rings=rings, c=[cx, cy]))
print(len(dists), "districts")


def district_of(lat, lon):
    out = np.full(len(lat), -1)
    for k, d in enumerate(dists):
        m = (out < 0) & inside(lat, lon, d["rings"])
        out[m] = k
    return out


stats = {}
for y, (a, b) in SEASON.items():
    v = pd.read_csv(VIIRS[y])
    ev_all = []
    for n in range((b - a).days + 1):
        d = a + timedelta(n)
        files = glob.glob(f"data/detections/{d:%Y%m%d}/*.csv")
        if not files:
            continue
        det = pd.concat([pd.read_csv(f, parse_dates=["t"]) for f in files])
        if det.empty:
            continue
        ev = pipeline.fire_events(datetime(d.year, d.month, d.day), step_min=10, viirs=v[v.acq_date == f"{d}"], detections=det)
        ev_all.append(ev[["lat", "lon", "fre_mj", "counted"]])
    ev = pd.concat(ev_all)
    ev["k"] = district_of(ev.lat.to_numpy(), ev.lon.to_numpy())
    vd = v[v.acq_date.between(f"{a}", f"{b}")]
    vk = district_of(vd.latitude.to_numpy(), vd.longitude.to_numpy())
    for k, d in enumerate(dists):
        e = ev[ev.k == k]
        fre = float(e.fre_mj.sum())
        stats.setdefault(k, {})[str(y)] = dict(
            official_fires=int((vk == k).sum()), gk2a_events=int(len(e)), fire_energy_tj=round(fre / 1e6, 2),
            missed_energy_tj=round(float(e.fre_mj[~e.counted].sum()) / 1e6, 2),
            missed_share=round(float(e.fre_mj[~e.counted].sum() / fre), 3) if fre > 0 else None)
    print(y, "events assigned to districts:", int((ev.k >= 0).sum()), "of", len(ev))

out = []
for k, d in enumerate(dists):
    s24, s25 = stats[k]["2024"], stats[k]["2025"]
    pct = lambda a, b: round((b - a) / a, 3) if a > 0 else None
    out.append(dict(name=d["name"], state=d["state"], centre=[round(d["c"][0], 3), round(d["c"][1], 3)],
                    y2024=s24, y2025=s25, official_change=pct(s24["official_fires"], s25["official_fires"]),
                    energy_change=pct(s24["fire_energy_tj"], s25["fire_energy_tj"])))
geo = {"type": "FeatureCollection", "features": [
    {"type": "Feature", "properties": {"k": k, "name": d["name"]},
     "geometry": {"type": "MultiPolygon", "coordinates": [[[[round(x, 3), round(y, 3)] for x, y in r[::3]]] for r in d["rings"]]}}
    for k, d in enumerate(dists)]}
json.dump(dict(districts=out, geo=geo), open("site/districts.json", "w"), separators=(",", ":"))
top = sorted(out, key=lambda r: -r["y2025"]["missed_energy_tj"])[:8]
for r in top:
    print(f'{r["name"]:16s} {r["state"]:8s} official 2025 {r["y2025"]["official_fires"]:5d} ({r["official_change"]}) | GK-2A energy {r["y2025"]["fire_energy_tj"]:6.1f} TJ ({r["energy_change"]}) | missed {r["y2025"]["missed_share"]}')
