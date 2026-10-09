"""Active-fire detection on GK-2A AMI scans.

Signal: dT = BT(3.8um) - BT(11.2um). A burning sub-pixel raises 3.8um far more than 11.2um.
Background: each pixel's own dT averaged over the 09-11 IST scans of the same day
(Jethva 2026, Remote Sens. 18:1506), which removes hot bare soil and surface emissivity.
Context: the pixel must also stand out from its 7x7 neighbourhood (MODIS-style contextual test),
which removes regional warming that the morning baseline cannot.
"""
import numpy as np
from scipy import ndimage

# Absolute floors (K) on BT3.8 / BT11.2 by IST hour: cloud screening, from Jethva 2026 Table 1
# (12-14 / 15-16 / 17 IST), extended past sunset where 3.8um no longer carries reflected sunlight.
FLOORS = {12: (303, 293), 13: (303, 293), 14: (303, 293), 15: (299, 289), 16: (299, 289),
          17: (297, 288), 18: (295, 287), 19: (290, 283), 20: (288, 282), 21: (287, 281)}
# dT_norm threshold (K) for a "nominal" fire, same source; lower in the evening as the
# morning-referenced background falls with the sun.
DT_NORM = {12: 4.0, 13: 4.0, 14: 4.0, 15: 3.5, 16: 3.5, 17: 3.0, 18: -3.0, 19: -3.0, 20: -3.0, 21: -3.0}


def baseline(morning):
    """Per-pixel mean dT over cloud-free morning scans; morning = [(bt38, bt112), ...]."""
    stack = np.stack([np.where(b112 > 285, b38 - b112, np.nan) for b38, b112 in morning])
    return np.nanmean(stack, axis=0)


def contextual(dt, size=7, k=3.0, min_excess=2.0):
    """True where dt beats its neighbourhood median by k robust sigmas and min_excess K."""
    filled = np.where(np.isfinite(dt), dt, np.nanmedian(dt))
    med = ndimage.median_filter(filled, size)
    mad = ndimage.median_filter(np.abs(filled - med), size) * 1.4826
    excess = dt - med
    return (excess > k * np.maximum(mad, 0.5)) & (excess > min_excess)


def detect(bt38, bt112, base, ist_hour, dt_norm_offset=0.0):
    """Boolean fire mask for one scan. dt_norm_offset shifts the threshold for tuning."""
    f38, f112 = FLOORS[ist_hour]
    dt = bt38 - bt112
    with np.errstate(invalid="ignore"):
        return ((dt - base > DT_NORM[ist_hour] + dt_norm_offset)
                & (bt38 > f38) & (bt112 > f112) & contextual(dt))


def frp_mw(bt38, bg38, pixel_km2):
    """Fire radiative power (MW) by the MIR radiance method (Wooster et al. 2003):
    FRP = A * sigma / a * (L - L_bg), with a = 3.08e-9 W m^-2 sr^-1 um^-1 K^-4 at 3.8-3.9um."""
    def planck(t, wl=3.83e-6):
        return 1.191042e-16 / wl ** 5 / (np.exp(1.4387770e-2 / (wl * t)) - 1) * 1e-6  # W m-2 sr-1 um-1
    sigma, a = 5.670374e-8, 3.08e-9
    return np.maximum(pixel_km2 * 1e6 * sigma / a * (planck(bt38) - planck(bg38)), 0) / 1e6
