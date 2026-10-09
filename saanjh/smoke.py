"""Lagrangian smoke model: fire emissions -> ground-level PM2.5 -> population exposure.

Particles move with ERA5 100 m winds (RK2) plus a horizontal random walk. Each particle is mixed
evenly from the ground up to H_p, the deepest boundary layer it has been in since release
(floored at the plume injection depth). That is the residual-layer rule: smoke released into a deep
afternoon layer stays diluted aloft when the layer collapses at dusk, while smoke released into the
shallow evening layer stays trapped near the ground until the next morning's growth mixes it up.
Ground concentration of a particle = mass / (cell area * H_p). The model is linear in emissions,
so any receptor's smoke can be split exactly by source fire.
"""
import json
import os
import time
from datetime import datetime, timedelta

import numpy as np
import requests
from scipy.interpolate import RegularGridInterpolator

# Model grid (degrees): North India + eastern Pakistan, 0.05 deg (~5 km) cells.
LON0, LAT0, D, NX, NY = 71.0, 26.0, 0.05, 200, 160
MET_D = 0.5
H_MIN = 200.0          # m, plume injection floor; sensitivity-tested in the notes
K_H = 1000.0           # m2/s horizontal eddy diffusivity
TAU_H = 72.0           # h, e-folding PM2.5 removal time
DATA = os.path.join(os.path.dirname(__file__), "..", "data")


def cell_area_m2():
    lat = LAT0 + (np.arange(NY) + 0.5) * D
    return (D * 110570.0) * (D * 111320.0 * np.cos(np.radians(lat)))[:, None] * np.ones(NX)


def population():
    """People per model cell (WorldPop 2020 1 km, India; cached)."""
    path = os.path.join(DATA, "pop", "pop_grid.npy")
    if os.path.exists(path):
        return np.load(path)
    import tifffile
    with tifffile.TiffFile(os.path.join(DATA, "pop", "ind_2020_1km.tif")) as tif:
        page = tif.pages[0]
        sx, sy = page.tags["ModelPixelScaleTag"].value[:2]
        x0, y0 = page.tags["ModelTiepointTag"].value[3:5]
        img = page.asarray().astype("f8")
    img[img < 0] = 0
    rows, cols = np.nonzero(img)
    lat, lon = y0 - (rows + 0.5) * sy, x0 + (cols + 0.5) * sx
    iy, ix = ((lat - LAT0) / D).astype(int), ((lon - LON0) / D).astype(int)
    ok = (iy >= 0) & (iy < NY) & (ix >= 0) & (ix < NX)
    pop = np.zeros((NY, NX))
    np.add.at(pop, (iy[ok], ix[ok]), img[rows[ok], cols[ok]])
    np.save(path, pop)
    return pop


class Met:
    """Hourly u, v (m/s, 100 m) and boundary-layer height (m) on a 0.5 deg grid."""

    def __init__(self, t0: datetime, hours, lats, lons, u, v, blh):
        self.t0, self.hours = t0, hours
        axes = (np.arange(hours, dtype=float), lats, lons)
        kw = dict(bounds_error=False, fill_value=None)
        self.u, self.v, self.blh = (RegularGridInterpolator(axes, a, **kw) for a in (u, v, blh))

    def at(self, t_h, lat, lon):
        p = np.c_[np.clip(t_h, 0, self.hours - 1), lat, lon]
        return self.u(p), self.v(p), np.maximum(self.blh(p), 10.0)

    @classmethod
    def era5(cls, start: datetime, end: datetime):
        """ERA5 via Open-Meteo for [start, end] (UTC dates), cached."""
        path = os.path.join(DATA, "met", f"era5_{start:%Y%m%d}_{end:%Y%m%d}.npz")
        if not os.path.exists(path):
            lats = np.arange(LAT0, LAT0 + NY * D + MET_D, MET_D)
            lons = np.arange(LON0, LON0 + NX * D + MET_D, MET_D)
            pts = np.array(np.meshgrid(lats, lons, indexing="ij")).reshape(2, -1).T
            cols = []
            for i in range(0, len(pts), 50):
                q = pts[i:i + 50]
                for attempt in range(6):
                    r = requests.get("https://archive-api.open-meteo.com/v1/era5", timeout=120, params=dict(
                        latitude=",".join(f"{x:.2f}" for x in q[:, 0]),
                        longitude=",".join(f"{x:.2f}" for x in q[:, 1]),
                        start_date=f"{start:%Y-%m-%d}", end_date=f"{end:%Y-%m-%d}", timezone="GMT",
                        hourly="wind_speed_100m,wind_direction_100m,boundary_layer_height",
                        wind_speed_unit="ms"))
                    if r.ok:
                        break
                    time.sleep(20 * (attempt + 1))  # free tier rate limit
                r.raise_for_status()
                js = r.json()
                cols += js if isinstance(js, list) else [js]
                time.sleep(2)
            ws = np.array([c["hourly"]["wind_speed_100m"] for c in cols], float)
            wd = np.radians(np.array([c["hourly"]["wind_direction_100m"] for c in cols], float))
            blh = np.array([c["hourly"]["boundary_layer_height"] for c in cols], float)
            shape = (len(lats), len(lons), -1)
            u, v = (-ws * np.sin(wd)).reshape(shape), (-ws * np.cos(wd)).reshape(shape)  # wind FROM wd
            os.makedirs(os.path.dirname(path), exist_ok=True)
            np.savez_compressed(path, lats=lats, lons=lons, u=u.transpose(2, 0, 1),
                                v=v.transpose(2, 0, 1), blh=blh.reshape(shape).transpose(2, 0, 1),
                                t0=json.dumps(f"{start:%Y-%m-%d}"))
        z = np.load(path)
        t0 = datetime.fromisoformat(json.loads(str(z["t0"])))
        return cls(t0, z["u"].shape[0], z["lats"], z["lons"], z["u"], z["v"], np.nan_to_num(z["blh"], nan=300.0))


def run(met: Met, lat, lon, t_rel, mass_kg, hours=36, n_per=40, dt_min=15, seed=0,
        out_every_h=1, h_min=H_MIN):
    """Release n_per particles per source (t_rel in hours since met.t0) and follow each for `hours`.

    Returns (conc, src_exposure): conc[k, y, x] ground PM2.5 (ug/m3) at output step k (hourly from
    the earliest release), and per-source population exposure (ug/m3 * person * h).
    """
    rng = np.random.default_rng(seed)
    pop, area = population(), cell_area_m2()
    src = np.repeat(np.arange(len(lat)), n_per)
    plat, plon = np.repeat(lat, n_per).astype(float), np.repeat(lon, n_per).astype(float)
    trel = np.repeat(t_rel, n_per).astype(float)
    m = np.repeat(mass_kg / n_per, n_per) * 1e9  # ug
    _, _, blh0 = met.at(trel, plat, plon)
    hp = np.maximum(blh0, h_min)
    t_start, t_end = trel.min(), trel.max() + hours
    steps = int(round((t_end - t_start) * 60 / dt_min))
    dt_h, dt_s = dt_min / 60, dt_min * 60
    n_out = int(np.ceil((t_end - t_start) / out_every_h)) + 1
    conc = np.zeros((n_out, NY, NX))
    expo = np.zeros(len(lat))
    sig = np.sqrt(2 * K_H * dt_s)
    for k in range(steps + 1):
        t = t_start + k * dt_h
        live = (trel <= t) & (t < trel + hours)
        if k % int(round(out_every_h / dt_h)) == 0 and live.any():
            iy = ((plat[live] - LAT0) / D).astype(int)
            ix = ((plon[live] - LON0) / D).astype(int)
            ok = (iy >= 0) & (iy < NY) & (ix >= 0) & (ix < NX)
            c = m[live][ok] * np.exp(-(t - trel[live][ok]) / TAU_H) / (area[iy[ok], ix[ok]] * hp[live][ok])
            np.add.at(conc[int(round((t - t_start) / out_every_h))], (iy[ok], ix[ok]), c)
            np.add.at(expo, src[live][ok], c * pop[iy[ok], ix[ok]] * out_every_h)
        if not live.any():
            continue
        la, lo = plat[live], plon[live]
        u1, v1, _ = met.at(np.full(la.shape, t), la, lo)
        lam = la + v1 * dt_s / 2 / 110570.0
        lom = lo + u1 * dt_s / 2 / (111320.0 * np.cos(np.radians(la)))
        u2, v2, _ = met.at(np.full(la.shape, t + dt_h / 2), lam, lom)
        la = la + (v2 * dt_s + rng.normal(0, sig, la.shape)) / 110570.0
        lo = lo + (u2 * dt_s + rng.normal(0, sig, la.shape)) / (111320.0 * np.cos(np.radians(la)))
        plat[live], plon[live] = la, lo
        _, _, blh = met.at(np.full(la.shape, t + dt_h), la, lo)
        hp[live] = np.maximum(hp[live], blh)
    return conc, expo


def hours_since(met: Met, t: datetime):
    return (t - met.t0) / timedelta(hours=1)
