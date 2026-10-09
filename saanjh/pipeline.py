"""One evening, end to end: GK-2A scans -> fire events -> smoke -> ranked fires and town alerts."""
from datetime import datetime, timedelta

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
}


def scan_times(day, step_min=60):
    """Morning baseline scans and 12:00-21:00 IST scans of a UTC day, as UTC datetimes."""
    morning = [day + timedelta(hours=3, minutes=30 + 30 * i) for i in range(5)]
    evening = [day + timedelta(hours=6, minutes=30) + timedelta(minutes=step_min * i)
               for i in range(9 * 60 // step_min + 1)]
    return morning, evening


def fire_events(day, step_min=60, viirs=None):
    """Fire events for one day: one row per GK-2A pixel that burned, with first/last detection,
    peak and integrated energy, and whether the official polar-orbiter record could have counted it."""
    lat, lon = gk2a.crop_grid()
    area = gk2a.pixel_area_km2()
    elev = np.load(f"{smoke.DATA}/elevation_crop.npy")
    morning, evening = scan_times(day, step_min)
    base = detect.baseline([(gk2a.cached_bt("sw038", t), gk2a.cached_bt("ir112", t)) for t in morning])
    rows = []
    for t in evening:
        b38, b112 = gk2a.cached_bt("sw038", t), gk2a.cached_bt("ir112", t)
        if b38 is None or b112 is None:
            continue
        fire, z = detect.detect(b38, b112, base, (t + IST).hour, elev)
        frp = detect.frp_mw(b38, area)
        for i, j in zip(*np.nonzero(fire)):
            rows.append(dict(i=i, j=j, t=t, frp=frp[i, j], z=z[i, j]))
    d = pd.DataFrame(rows)
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


def tonight(day, met, events, hours=30):
    """Run every fire's smoke forward and rank. Each scan a fire was seen releases that scan's share
    of its PM2.5 at that time. Returns (events with harm, town table, hourly concentration frames, t0)."""
    if events.empty:
        return events, pd.DataFrame(), None, None
    reps = events.loc[events.index.repeat(events.scans)].copy()
    reps["k"] = reps.groupby(level=0).cumcount()
    rel_t = reps["first"] + pd.to_timedelta(reps.k * (reps["last"] - reps["first"]).dt.total_seconds()
                                            / np.maximum(reps.scans - 1, 1), unit="s")
    t_h = np.array([smoke.hours_since(met, t.to_pydatetime()) for t in rel_t])
    conc, expo = smoke.run(met, reps.lat.to_numpy(), reps.lon.to_numpy(), t_h,
                           (reps.pm25_kg / reps.scans).to_numpy(), hours=hours, n_per=30)
    events = events.copy()
    events["harm"] = pd.Series(expo, index=reps.index).groupby(level=0).sum()
    events = events.sort_values("harm", ascending=False)
    t0 = met.t0 + timedelta(hours=float(t_h.min()))
    towns = []
    for name, (la, lo) in TOWNS.items():
        series = conc[:, int((la - smoke.LAT0) / smoke.D), int((lo - smoke.LON0) / smoke.D)]
        k_peak = int(series.argmax())
        over = np.nonzero(series > 0.25 * series.max())[0] if series.max() > 0 else []
        towns.append(dict(town=name, peak_ugm3=series.max(), peak_ist=f"{t0 + timedelta(hours=k_peak) + IST:%a %H:%M}",
                          arrives_ist=f"{t0 + timedelta(hours=int(over[0])) + IST:%a %H:%M}" if len(over) else ""))
    return events, pd.DataFrame(towns).sort_values("peak_ugm3", ascending=False), conc, t0
