"""Score the detector against VIIRS at overpass time.

For each cached day: collocate VIIRS SNPP fires onto the GK-2A grid, sum their FRP per AMI pixel,
and count a VIIRS-fire pixel as detected if GK-2A flags it (or an adjacent pixel, allowing for
navigation error) in either scan bracketing the overpass. Output: probability of detection by
per-pixel FRP bin, and the share of GK-2A detections with no VIIRS fire nearby (an upper bound on
false alarms: VIIRS misses some fires too).

usage: eval_pod.py viirs.csv out_prefix [z_thr ...]
"""
import os
import sys
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
from scipy import ndimage
from scipy.spatial import cKDTree

from saanjh import detect, gk2a

viirs = pd.read_csv(sys.argv[1])
out = sys.argv[2]
z_list = [float(z) for z in sys.argv[3:]] or [detect.Z]
lat, lon = gk2a.crop_grid()
elev = np.load("data/elevation_crop.npy")
grid = cKDTree(np.c_[lat.ravel(), lon.ravel()])
BINS = [0, 5, 10, 20, 40, 80, 1e9]

rows = []
for day_s, v in viirs.groupby("acq_date"):
    day = datetime.fromisoformat(day_s)
    hhmm = int(v.acq_time.median())
    t0 = day + timedelta(hours=hhmm // 100, minutes=hhmm % 100 // 10 * 10)
    morning = [day + timedelta(hours=3, minutes=30 + 30 * i) for i in range(5)]
    scans = [(gk2a.cached_bt("sw038", t), gk2a.cached_bt("ir112", t))
             for t in morning + [t0, t0 + timedelta(minutes=10)]] if all(
        os.path.exists(os.path.join(gk2a.CACHE, "_".join(map(str, gk2a.WIN)), f"{b}_{t:%Y%m%d%H%M}.npy"))
        for t in morning + [t0, t0 + timedelta(minutes=10)] for b in ("sw038", "ir112")) else None
    if scans is None:
        continue
    base = detect.baseline(scans[:5])
    ist_hour = (t0 + timedelta(hours=5, minutes=30)).hour
    _, idx = grid.query(np.c_[v.latitude, v.longitude])
    frp = np.bincount(idx, weights=v.frp, minlength=lat.size).reshape(lat.shape)
    plains = elev < detect.MAX_ELEV_M
    for z_thr in z_list:
        det = np.zeros(lat.shape, bool)
        for b38, b112 in scans[5:]:
            det |= detect.detect(b38, b112, base, ist_hour, elev, z_thr)[0]
        hit = ndimage.binary_dilation(det)  # within one pixel of a detection
        near_fire = ndimage.binary_dilation(frp > 0)
        for lo, hi in zip(BINS[:-1], BINS[1:]):
            pos = plains & (frp > lo) & (frp <= hi)
            rows.append(dict(day=day_s, z=z_thr, frp_lo=lo, frp_hi=hi, n=int(pos.sum()),
                             detected=int((pos & hit).sum()), frp_total=frp[pos].sum(),
                             frp_detected=frp[pos & hit].sum()))
        rows.append(dict(day=day_s, z=z_thr, frp_lo=-1, frp_hi=-1, n=int(det.sum()),
                         detected=int((det & ~near_fire).sum()), frp_total=np.nan, frp_detected=np.nan))

r = pd.DataFrame(rows)
os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
r.to_csv(out + "_by_day.csv", index=False)
fa = r[r.frp_lo == -1].groupby("z")[["n", "detected"]].sum()
pod = r[r.frp_lo >= 0].groupby(["z", "frp_lo", "frp_hi"])[["n", "detected", "frp_total", "frp_detected"]].sum()
pod["pod"] = pod.detected / pod.n
summary = pod.reset_index()
summary.to_csv(out + "_pod.csv", index=False)
print("days scored:", r.day.nunique())
print(summary.to_string(index=False, float_format="%.3f"))
for z, row in fa.iterrows():
    tot = pod.loc[z]
    print(f"z>{z}: detections={row.n}, no VIIRS fire within 1 px={row.detected / max(row.n, 1):.2f}, "
          f"FRP share of VIIRS fire pixels detected={tot.frp_detected.sum() / tot.frp_total.sum():.2f}")
