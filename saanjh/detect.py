"""Active-fire detection on GK-2A AMI scans of Punjab/Haryana.

Signal: dT = BT(3.8um) - BT(11.2um); a burning sub-pixel raises 3.8um far more than 11.2um.
Context: dT minus its 7x7 neighbourhood median removes the regional diurnal cycle and haze.
Background: that excess has a per-pixel bias and noise (soil, towns, canals) which we take from
the same day's 09-11 IST scans, the normalisation Jethva (2026, Remote Sens. 18:1506) uses.
A fire is z = (excess - morning bias) / morning noise above Z, on cloud-free plains pixels with no
cold neighbours (cloud edges were the main false alarm on day one), and the 3.8um channel itself must
stand out from its neighbourhood (as in MODIS): on the 2024 season this removed 211 detections driven only
by a cold 11.2um pixel on the Thar desert edge, all unmatched by VIIRS, with no loss of detection.
"""
import warnings

import numpy as np
from scipy import ndimage

# BT11.2 cloud floor (K) by IST hour; daytime values from Jethva 2026 Table 1, evening extrapolated.
F112 = {12: 293, 13: 293, 14: 293, 15: 289, 16: 289, 17: 288, 18: 287, 19: 283, 20: 282, 21: 281,
        22: 280, 23: 279}
Z, MIN_EXCESS_K, MIN_MIR_K, MAX_ELEV_M = 6.0, 2.0, 0.5, 400.0


def excess(x, size=7):
    """x minus its size x size neighbourhood median (NaNs filled with the scene median)."""
    filled = np.where(np.isfinite(x), x, np.nanmedian(x))
    return x - ndimage.median_filter(filled, size)


def baseline(morning):
    """Per-pixel (bias, noise) of the dT excess over morning scans [(bt38, bt112), ...]."""
    stack = np.stack([np.where(b112 > 285, excess(b38 - b112), np.nan) for b38, b112 in morning])
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)  # all-NaN pixels (cloudy all morning)
        bias, noise = np.nanmedian(stack, 0), np.nanstd(stack, 0)
    return np.nan_to_num(bias), np.maximum(np.nan_to_num(noise, nan=1.0), 0.3)


def detect(bt38, bt112, base, ist_hour, elev, z_thr=Z):
    """Returns (fire mask, z score) for one scan."""
    bias, noise = base
    c = excess(bt38 - bt112)
    z = (c - bias) / noise
    floor = F112[ist_hour]
    with np.errstate(invalid="ignore"):
        clear = (bt112 > floor) & (ndimage.minimum_filter(np.nan_to_num(bt112), 5) > floor - 4)
        fire = (z > z_thr) & (c > MIN_EXCESS_K) & (excess(bt38) > MIN_MIR_K) & clear & (elev < MAX_ELEV_M)
    return fire, z


def frp_mw(bt38, pixel_km2):
    """Fire radiative power (MW) per pixel by the MIR radiance method (Wooster et al. 2003):
    FRP = A * sigma / a * (L - L_bg), a = 3.08e-9 W m-2 sr-1 um-1 K-4 near 3.9 um,
    L_bg from the 7x7 neighbourhood median brightness temperature."""
    def planck(t, wl=3.83e-6):  # W m-2 sr-1 um-1
        return 1.191042e-16 / wl ** 5 / (np.exp(1.4387770e-2 / (wl * t)) - 1) * 1e-6
    bg = bt38 - excess(bt38)
    return np.maximum(pixel_km2 * 1e6 * 5.670374e-8 / 3.08e-9 * (planck(bt38) - planck(bg)), 0) / 1e6
