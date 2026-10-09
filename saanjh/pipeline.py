"""One evening, end to end: GK-2A scans -> fire events -> smoke -> ranked fires and town alerts."""
import base64
import json
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
from scipy import ndimage

from saanjh import detect, gk2a, smoke

IST = timedelta(hours=5, minutes=30)
KG_PER_MJ = 0.368    # dry matter burned per MJ of fire radiative energy (Wooster et al. 2005)
EF_PM25 = 6.26e-3    # kg PM2.5 per kg crop residue burned (Akagi et al. 2011)
TOWNS = {  # name: (lat, lon)
    "Delhi": (28.61, 77.21), "Gurugram": (28.46, 77.03), "Noida": (28.54, 77.39), "Ghaziabad": (28.67, 77.45),
    "Faridabad": (28.41, 77.32), "Meerut": (28.98, 77.71), "Sonipat": (28.99, 77.02), "Panipat": (29.39, 76.97),
    "Karnal": (29.69, 76.99), "Rohtak": (28.89, 76.61), "Hisar": (29.15, 75.72), "Sirsa": (29.53, 75.03),
    "Ambala": (30.38, 76.78), "Chandigarh": (30.73, 76.78), "Patiala": (30.34, 76.39), "Sangrur": (30.25, 75.84),
    "Ludhiana": (30.90, 75.85), "Jalandhar": (31.33, 75.58), "Amritsar": (31.63, 74.87), "Moga": (30.82, 75.17),
    "Bathinda": (30.21, 74.95), "Ferozepur": (30.93, 74.61), "Muktsar": (30.47, 74.52), "Fazilka": (30.40, 74.03),
    "Fatehabad": (29.52, 75.45),
    "Ratia": (29.69, 75.58),
    "Tohana": (29.71, 75.9),
    "Mansa": (29.99, 75.4),
    "Barnala": (30.38, 75.55),
    "Kaithal": (29.8, 76.4),
    "Jind": (29.32, 76.31),
    "Tarn Taran": (31.45, 74.93),
    "Kapurthala": (31.38, 75.38),
    "Faridkot": (30.67, 74.76),
    "Abohar": (30.14, 74.2),
    "Malerkotla": (30.53, 75.88),
    "Gurdaspur": (32.04, 75.4),
    "Hoshiarpur": (31.53, 75.91),
    "Rupnagar": (30.97, 76.53),
    "Kurukshetra": (29.97, 76.85),
    "Yamunanagar": (30.13, 77.27),
    "Bhiwani": (28.79, 76.13),
    "Ellenabad": (29.45, 74.66),
    "Talwandi Sabo": (29.98, 75.08),
}


def scan_times(day, step_min=60):
    """Morning baseline scans and 12:00-21:00 IST scans of a UTC day, as UTC datetimes."""
    morning = [day + timedelta(hours=3, minutes=30 + 30 * i) for i in range(5)]
    evening = [day + timedelta(hours=6, minutes=30) + timedelta(minutes=step_min * i)
               for i in range(9 * 60 // step_min + 1)]
    return morning, evening


def morning_base(day, read=gk2a.cached_bt):
    """Per-pixel detector baseline from the day's 09:00-11:00 IST scans."""
    return detect.baseline([(read("sw038", t), read("ir112", t)) for t in scan_times(day)[0]])


def detect_scan(t, base, read=gk2a.cached_bt):
    """Fire pixels in one scan as rows (i, j, t, frp, z); None if the scan is missing."""
    b38, b112 = read("sw038", t), read("ir112", t)
    if b38 is None or b112 is None:
        return None
    elev = np.load(f"{smoke.DATA}/elevation_crop.npy")
    fire, z = detect.detect(b38, b112, base, (t + IST).hour, elev)
    frp = detect.frp_mw(b38, gk2a.pixel_area_km2())
    i, j = np.nonzero(fire)
    return pd.DataFrame(dict(i=i, j=j, t=t, frp=frp[i, j], z=z[i, j]))


def fire_events(day, step_min=60, viirs=None, detections=None):
    """Fire events for one day: one row per GK-2A pixel that burned, with first/last detection,
    peak and integrated energy, and whether the official polar-orbiter record could have counted it.
    `detections` (rows from detect_scan) are computed from the local cache when not given."""
    lat, lon = gk2a.crop_grid()
    if detections is None:
        base = morning_base(day)
        detections = pd.concat([detect_scan(t, base) for t in scan_times(day, step_min)[1]])
    d = detections
    if d.empty:
        return d
    dt_s = step_min * 60
    ev = d.groupby(["i", "j"]).agg(first=("t", "min"), last=("t", "max"), scans=("t", "size"),
                                   frp_peak=("frp", "max"), frp_sum=("frp", "sum"), z_max=("z", "max")).reset_index()
    ev["lat"], ev["lon"] = lat[ev.i, ev.j], lon[ev.i, ev.j]
    ev["fre_mj"] = ev.frp_sum * dt_s           # MW * s = MJ
    ev["pm25_kg"] = ev.fre_mj * KG_PER_MJ * EF_PM25
    ev["first_ist"] = (ev["first"] + IST).dt.strftime("%H:%M")
    ev["counted"] = False
    if viirs is not None and len(viirs):
        from scipy.spatial import cKDTree
        _, k = cKDTree(np.c_[lat.ravel(), lon.ravel()]).query(np.c_[viirs.latitude, viirs.longitude])
        seen = np.zeros(lat.size, bool)
        seen[k] = True
        seen = ndimage.binary_dilation(seen.reshape(lat.shape))  # one pixel of navigation slack
        hhmm = int(viirs.acq_time.median())
        overpass = day + timedelta(hours=hhmm // 100, minutes=hhmm % 100)
        # Counted = this fire was already burning when VIIRS passed and VIIRS saw fire there.
        ev["counted"] = seen[ev.i, ev.j] & (ev["first"] <= overpass + timedelta(minutes=30))
    return ev


def overpass_sources(day, viirs):
    """The inventory forecasts use today: VIIRS fires summed on the 0.05 deg model grid, released 09:00-19:00
    IST with a midday-peaked profile (Gaussian, peak 13:30 IST, sigma 2 h). Returns one row per grid cell
    and its hourly releases (row index, UTC time, kg PM2.5)."""
    g = viirs.assign(cy=((viirs.latitude - smoke.LAT0) / smoke.D).astype(int),
                     cx=((viirs.longitude - smoke.LON0) / smoke.D).astype(int))
    cells = g.groupby(["cy", "cx"]).frp.sum().reset_index()
    hours = np.arange(9, 20)
    w = np.exp(-((hours + 0.5 - 13.5) ** 2) / (2 * 2.0 ** 2))
    kg = np.outer(cells.frp, w) * 3600 * KG_PER_MJ * EF_PM25  # MW * s = MJ
    src = pd.DataFrame(dict(lat=smoke.LAT0 + (cells.cy + 0.5) * smoke.D, lon=smoke.LON0 + (cells.cx + 0.5) * smoke.D,
                            first=day + timedelta(hours=8), first_ist="13:30", scans=0, frp_peak=cells.frp,
                            pm25_kg=kg.sum(1), counted=True, source="VIIRS"))
    rel = pd.DataFrame(dict(row=np.repeat(src.index, len(hours)),
                            t=np.tile([day + timedelta(hours=float(h) - 5.5) for h in hours], len(src)),
                            kg=kg.ravel()))
    return src, rel


def _gk2a_releases(events):
    """Each GK-2A fire event releases its PM2.5 evenly over the scans it was seen in."""
    reps = events.loc[events.index.repeat(events.scans)].copy()
    reps["k"] = reps.groupby(level=0).cumcount()
    t = reps["first"] + pd.to_timedelta(reps.k * (reps["last"] - reps["first"]).dt.total_seconds()
                                        / np.maximum(reps.scans - 1, 1), unit="s")
    return pd.DataFrame(dict(row=reps.index, t=t.to_numpy(), kg=(reps.pm25_kg / reps.scans).to_numpy()))


def tonight(day, met, events, hours=30, viirs=None):
    """Run the smoke forward and rank the fires. With `viirs`, the inventory is the hybrid that tested best
    (results/NOTES.md, N4): the overpass inventory plus only the GK-2A fires it missed. Without it, all GK-2A
    events. Returns (ranked sources with harm, town table, hourly concentration frames, t0)."""
    if events.empty and (viirs is None or viirs.empty):
        return events, pd.DataFrame(), None, None
    if viirs is not None and len(viirs):
        missed = events[~events.counted].assign(source="GK-2A") if len(events) else events
        vsrc, vrel = overpass_sources(day, viirs)
        src = pd.concat([missed.drop(columns=["i", "j"], errors="ignore"), vsrc], ignore_index=True)
        rel = pd.concat([_gk2a_releases(src.iloc[:len(missed)]) if len(missed) else None,
                         vrel.assign(row=vrel.row + len(missed))])
    else:
        src = events.assign(source="GK-2A").reset_index(drop=True)
        rel = _gk2a_releases(src)
    t_h = np.array([smoke.hours_since(met, pd.Timestamp(t).to_pydatetime()) for t in rel.t])
    conc, expo = smoke.run(met, src.lat.to_numpy()[rel.row], src.lon.to_numpy()[rel.row], t_h,
                           rel.kg.to_numpy(), hours=hours, n_per=30)
    src["harm"] = pd.Series(expo).groupby(rel.row.to_numpy()).sum().reindex(src.index, fill_value=0.0)
    src = src.sort_values("harm", ascending=False)
    t0 = met.t0 + timedelta(hours=float(t_h.min()))
    towns = []
    for name, (la, lo) in TOWNS.items():
        series = conc[:, int((la - smoke.LAT0) / smoke.D), int((lo - smoke.LON0) / smoke.D)]
        k_peak = int(series.argmax())
        over = np.nonzero(series > 0.25 * series.max())[0] if series.max() > 0 else []
        towns.append(dict(town=name, lat=la, lon=lo, peak_ugm3=series.max(), peak_ist=f"{t0 + timedelta(hours=k_peak) + IST:%a %H:%M}",
                          arrives_ist=f"{t0 + timedelta(hours=int(over[0])) + IST:%a %H:%M}" if len(over) else ""))
    return src, pd.DataFrame(towns).sort_values("peak_ugm3", ascending=False), conc, t0


def _frames(conc, factor=2):
    """Hourly ground-smoke grids, block-averaged to 0.1 deg and log-scaled to uint8, base64."""
    k, ny, nx = conc.shape
    c = conc[:, :ny // factor * factor, :nx // factor * factor].reshape(k, ny // factor, factor, nx // factor, factor)
    q = np.clip(np.log10(np.maximum(c.mean((2, 4)), 1e-3)) * 50 + 150, 0, 255).astype("u1")  # 1e-3..1e2 ug/m3
    return [base64.b64encode(f.tobytes()).decode() for f in q]


def summary(day, ranked, towns, conc, t0, n_scans, replay=False, events=None):
    """The JSON the web page reads (tonight.json / results/<day>.json). `ranked` is tonight()'s output;
    `events` (all GK-2A fire events) feeds the counted/missed statistics when the hybrid inventory is used."""
    ev = events if events is not None else ranked
    # The officer list ranks the fires Saanjh saw (burning this afternoon and evening); fires already in the
    # official count still shape the smoke and appear on the map as `counted_cells`.
    gk_ranked = ranked[ranked.get("source", pd.Series("GK-2A", index=ranked.index)) == "GK-2A"]
    counted_cells = ranked[ranked.get("source", pd.Series("", index=ranked.index)) == "VIIRS"]
    top = gk_ranked.head(50).copy()
    top["near"] = [f"{n} {np.hypot((la - r.lat) * 111, (lo - r.lon) * 96):.0f} km"
                   for r in top.itertuples()
                   for n, (la, lo) in [min(TOWNS.items(), key=lambda kv: (kv[1][0] - r.lat) ** 2 + (kv[1][1] - r.lon) ** 2)]]
    if "source" not in top:
        top["source"] = "GK-2A"
    gk = ev[ev.get("source", pd.Series("GK-2A", index=ev.index)) == "GK-2A"] if len(ev) else ev
    fre = gk.fre_mj.sum() if len(gk) else 0
    return dict(
        day=f"{day:%Y-%m-%d}", generated=f"{datetime.now(timezone.utc):%Y-%m-%dT%H:%MZ}", scans=n_scans, replay=replay,
        stats=dict(events=len(gk), counted=int(gk.counted.sum()) if len(gk) else 0,
                   uncounted_energy_share=round(float(gk.fre_mj[~gk.counted].sum() / fre), 3) if fre else 0.0,
                   fre_mj=round(float(fre)), pm25_t=round(float(ranked.pm25_kg.sum()) / 1000, 1),
                   top20_harm_share=round(float(gk_ranked.harm.head(20).sum() / ranked.harm.sum()), 3),
                   missed_harm_share=round(float(gk_ranked.harm.sum() / ranked.harm.sum()), 3),
                   harm_total=float(ranked.harm.sum()),
                   first_seen=gk.groupby("first_ist").size().to_dict() if len(gk) else {}),
        fires=json.loads(top[["lat", "lon", "near", "first_ist", "scans", "frp_peak", "pm25_kg", "counted", "harm", "source"]]
                         .round(3).to_json(orient="records")),
        counted_cells=counted_cells[["lat", "lon"]].round(3).to_numpy().tolist(),
        towns=json.loads(towns.round(1).to_json(orient="records")),
        grid=dict(lat0=smoke.LAT0, lon0=smoke.LON0, d=smoke.D * 2, ny=smoke.NY // 2, nx=smoke.NX // 2,
                  t0=f"{t0:%Y-%m-%dT%H:%MZ}", scale="ug/m3 = 10**((v-150)/50)"),
        frames=_frames(conc))
