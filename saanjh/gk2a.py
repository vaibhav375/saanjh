"""GK-2A AMI L1B: find a scan on the NOAA open-data bucket, read only the North-India
crop over HTTP range requests, and calibrate counts to brightness temperature.

Geolocation follows the CGMS geostationary projection (scan angles from cfac/lfac);
calibration follows satpy's ami_l1b reader with the in-file Teff->Tbb coefficients.
"""
import os
import time
from datetime import datetime

import numpy as np

BUCKET = "https://noaa-gk2a-pds.s3.amazonaws.com"
# Central wavelengths (um), from satpy's ami_l1b.yaml.
WAVELENGTH = {"sw038": 3.83, "ir105": 10.35, "ir112": 11.23, "ir123": 12.36}

# Crop of the full disk (0-based rows/cols, end-exclusive): Punjab + Haryana, ~28.4-32.7N,
# 73-80E. It sits inside one 1375x1375 HDF5 chunk row, so each scan costs one chunk download.
WIN = (1178, 1375, 615, 905)

# Fixed AMI full-disk 2 km grid constants (identical in every file).
SUB_LON, H, REQ, RP = 128.2, 42164000.0, 6378137.0, 6356752.3
CFAC, LFAC, COFF, LOFF = 20425338.90333935, -20425338.90333935, 2750.5, 2750.5


def url(band, t: datetime):
    """Object URL of one full-disk scan; t is UTC on a 10-minute boundary."""
    return (f"{BUCKET}/AMI/L1B/FD/{t:%Y%m}/{t:%d}/{t:%H}/"
            f"gk2a_ami_le1b_{band}_fd020ge_{t:%Y%m%d%H%M}.nc")


def latlon_to_linecol(lat, lon):
    lat, dlon = np.radians(lat), np.radians(np.asarray(lon) - SUB_LON)
    c_lat = np.arctan((RP / REQ) ** 2 * np.tan(lat))
    e2 = 1 - (RP / REQ) ** 2
    rl = RP / np.sqrt(1 - e2 * np.cos(c_lat) ** 2)
    r1 = H - rl * np.cos(c_lat) * np.cos(dlon)
    r2 = rl * np.cos(c_lat) * np.sin(dlon)
    r3 = rl * np.sin(c_lat)
    x = np.degrees(np.arctan2(r2, r1))
    y = np.degrees(np.arcsin(r3 / np.sqrt(r1 ** 2 + r2 ** 2 + r3 ** 2)))
    # CGMS line/column numbers are 1-based; return 0-based array indices.
    return LOFF + y * LFAC / 2 ** 16 - 1, COFF + x * CFAC / 2 ** 16 - 1


def linecol_to_latlon(line, col):
    """Inverse of latlon_to_linecol; line/col are 0-based array indices."""
    x = np.radians((np.asarray(col) + 1 - COFF) * 2 ** 16 / CFAC)
    y = np.radians((np.asarray(line) + 1 - LOFF) * 2 ** 16 / LFAC)
    k = (REQ / RP) ** 2
    a = np.cos(y) ** 2 + k * np.sin(y) ** 2
    b = -2 * H * np.cos(x) * np.cos(y)
    sn = (-b - np.sqrt(b * b - 4 * a * (H * H - REQ * REQ))) / (2 * a)
    xe = H - sn * np.cos(y) * np.cos(x)
    ye = sn * np.cos(y) * np.sin(x)
    ze = sn * np.sin(y)
    lat = np.degrees(np.arctan(k * ze / np.hypot(xe, ye)))
    return lat, SUB_LON + np.degrees(np.arctan2(ye, xe))


def crop_grid(win=WIN):
    """Pixel-centre (lat, lon) arrays of the crop."""
    lines, cols = np.mgrid[win[0]:win[1], win[2]:win[3]]
    return linecol_to_latlon(lines, cols)


def pixel_area_km2(win=WIN):
    """Ground area of each crop pixel (km^2), from the Jacobian of the geolocation."""
    lat, lon = crop_grid(win)
    dlat_l, dlat_c = np.gradient(lat)
    dlon_l, dlon_c = np.gradient(lon)
    return np.abs(dlat_l * dlon_c - dlat_c * dlon_l) * 110.57 * 111.32 * np.cos(np.radians(lat))


def counts_to_bt(counts, attrs, band):
    """Counts -> brightness temperature (K); bad pixels become NaN."""
    valid = (counts >> 14) == 0  # top 2 bits are the quality flag; 0 = good
    dn = (counts & 0x3FFF).astype("f8")
    rad = dn * attrs["DN_to_Radiance_Gain"][0] + attrs["DN_to_Radiance_Offset"][0]
    c, h, k = (attrs[n][0] for n in ("light_speed", "Plank_constant_h", "Boltzmann_constant_k"))
    wn = 1e6 / WAVELENGTH[band]  # m^-1
    with np.errstate(invalid="ignore", divide="ignore"):
        teff = (h * c / k * wn) / np.log(2 * h * c * c * wn ** 3 / (rad * 1e-5) + 1)
    bt = attrs["Teff_to_Tbb_c0"][0] + attrs["Teff_to_Tbb_c1"][0] * teff + attrs["Teff_to_Tbb_c2"][0] * teff ** 2
    return np.where(valid & (rad > 0), bt, np.nan)


def _open(path):
    if not path.startswith("http"):
        return open(path, "rb")
    import certifi
    import fsspec
    os.environ.setdefault("SSL_CERT_FILE", certifi.where())  # python.org builds ship no CA roots
    return fsspec.filesystem("https").open(path, block_size=2 ** 20, cache_type="blockcache")


def read_bt(path, band, win=WIN):
    """Brightness temperature of the crop window from a local path or URL."""
    import h5py
    with _open(path) as f, h5py.File(f, "r") as h:
        counts = h["image_pixel_values"][win[0]:win[1], win[2]:win[3]]
        return counts_to_bt(counts, dict(h.attrs), band)


CACHE = os.environ.get("SAANJH_CACHE", os.path.join(os.path.dirname(__file__), "..", "data", "gk2a"))


def cached_bt(band, t: datetime):
    """read_bt for one scan, cached as float32 .npy. Missing scans return None."""
    path = os.path.join(CACHE, "_".join(map(str, WIN)), f"{band}_{t:%Y%m%d%H%M}.npy")
    if os.path.exists(path):
        return np.load(path)
    for attempt in range(4):
        try:
            bt = read_bt(url(band, t), band).astype("f4")
            break
        except FileNotFoundError:
            return None
        except Exception:  # S3 drops long range requests now and then
            if attempt == 3:
                raise
            time.sleep(2 ** attempt)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    np.save(path, bt)
    return bt


def fetch_many(jobs, workers=8):
    """Cache many (band, time) scans in parallel; returns {(band, time): bt or None}."""
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(workers) as ex:
        return dict(zip(jobs, ex.map(lambda j: cached_bt(*j), jobs)))
