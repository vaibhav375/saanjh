import numpy as np

from saanjh import detect, gk2a


def test_geolocation_round_trip_and_window():
    lat, lon = 30.90, 75.85  # Ludhiana
    line, col = gk2a.latlon_to_linecol(lat, lon)
    back = gk2a.linecol_to_latlon(line, col)
    assert np.allclose(back, (lat, lon), atol=1e-6)
    l0, l1, c0, c1 = gk2a.WIN
    assert l0 <= line < l1 and c0 <= col < c1
    assert l1 <= 1375  # one HDF5 chunk row


def test_detects_hot_pixel_and_rejects_cloud_edge():
    rng = np.random.default_rng(0)
    shape = (40, 40)
    morning = [(300 + rng.normal(0, .3, shape), 295 + rng.normal(0, .3, shape)) for _ in range(5)]
    base = detect.baseline(morning)
    elev = np.zeros(shape)
    bt38, bt112 = 300 + rng.normal(0, .3, shape), 295 + rng.normal(0, .3, shape)
    bt38[10, 10] += 8                      # fire on clear land
    bt38[30, 30] += 8                      # same anomaly ...
    bt112[28:33, 26:29] = 270              # ... next to a cold cloud
    fire, _ = detect.detect(bt38, bt112, base, 16, elev)
    assert fire[10, 10] and not fire[30, 30]
    assert fire.sum() == 1


def test_frp_scales_with_anomaly():
    bt = np.full((9, 9), 295.0)
    bt[4, 4] = 300.0
    small = detect.frp_mw(bt, 12.0)[4, 4]
    bt[4, 4] = 305.0
    assert 0 < small < detect.frp_mw(bt, 12.0)[4, 4]
