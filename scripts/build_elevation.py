"""Elevation (m) on the GK-2A crop grid, from Open-Meteo's elevation API on a 0.1 deg grid."""
import time

import numpy as np
import requests
from scipy.interpolate import RegularGridInterpolator

from saanjh import gk2a

lat, lon = gk2a.crop_grid()
# The slant view makes the crop a tilted quadrilateral; only the plains box matters.
la = np.arange(28.0, 33.01, 0.1)
lo = np.arange(73.0, 80.51, 0.1)
G = np.array(np.meshgrid(la, lo, indexing="ij")).reshape(2, -1).T
out = []
for i in range(0, len(G), 100):
    q = G[i:i + 100]
    for attempt in range(5):
        r = requests.get("https://api.open-meteo.com/v1/elevation", timeout=30, params={
            "latitude": ",".join(f"{x:.2f}" for x in q[:, 0]),
            "longitude": ",".join(f"{x:.2f}" for x in q[:, 1])})
        if r.ok:
            break
        time.sleep(5 + 10 * attempt)
    r.raise_for_status()
    out += r.json()["elevation"]
    time.sleep(1)
elev = RegularGridInterpolator((la, lo), np.array(out).reshape(len(la), len(lo)), bounds_error=False,
                               fill_value=9999.0)(np.c_[lat.ravel(), lon.ravel()])  # outside box = excluded
np.save("data/elevation_crop.npy", elev.reshape(lat.shape).astype("f4"))
print("saved", lat.shape, "max", elev.max())
