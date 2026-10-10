"""Tomorrow's fire risk and where to send field teams.

Grid: 0.1 deg cells (~11 km, a cluster of villages) over Punjab and Haryana. For each cell, features known by
the evening of day d predict whether GK-2A will see fire there on day d+1: the cell's and its neighbourhood's
recent fire energy (the harvest-burning wave moves across the state), yesterday's VIIRS count (what the official
count shows), how far the season has progressed locally, last season's burning, rain, and the day.

Two scikit-learn HistGradientBoosting models are trained offline: P(fire tomorrow) and the expected fire energy
if it burns. Their trees are exported to plain arrays and evaluated here with numpy, so the Lambda needs no
scikit-learn (its layer is at the size limit).

The planner places K teams, each patrolling a 3x3 block of cells (~33 km square), to cover the most expected
smoke harm = P(fire) x expected energy x population exposure per kg released from that cell at dusk under
tomorrow's weather (this formula was chosen on a 2024-only split before the 2025 test).
Greedy selection for this maximum-coverage problem is within (1 - 1/e) of optimal.
"""
import numpy as np
from scipy import ndimage

LAT0, LON0, D, NY, NX = 28.4, 73.8, 0.1, 42, 38
FEATURES = ["e0", "e1", "e_2to6", "n0", "n3", "n7", "v0", "vn", "season_cum", "clim", "day", "weekday",
            "rain_d", "rain_next"]


def cell_of(lat, lon):
    """(row, col) of each point, -1 where outside the grid."""
    r = np.floor((np.asarray(lat) - LAT0) / D).astype(int)
    c = np.floor((np.asarray(lon) - LON0) / D).astype(int)
    ok = (r >= 0) & (r < NY) & (c >= 0) & (c < NX)
    return np.where(ok, r, -1), np.where(ok, c, -1)


def grid_sum(lat, lon, w=None):
    r, c = cell_of(lat, lon)
    ok = r >= 0
    g = np.zeros((NY, NX))
    np.add.at(g, (r[ok], c[ok]), 1.0 if w is None else np.asarray(w, float)[ok])
    return g


def centres():
    lat = LAT0 + (np.arange(NY) + 0.5) * D
    lon = LON0 + (np.arange(NX) + 0.5) * D
    return np.meshgrid(lat, lon, indexing="ij")


def neigh(g, size=5):
    """Sum over a size x size block of cells around each cell."""
    return ndimage.uniform_filter(g, size, mode="constant") * size * size


def features(fre, viirs, clim, rain, day_index, weekday_next):
    """Feature stack (NY, NX, len(FEATURES)) for predicting day d+1.

    fre:   GK-2A fire energy (MJ) per cell for days d, d-1, ..., oldest last (at least 7 days; zeros if unknown)
    viirs: VIIRS fire count per cell on day d
    clim:  last season's VIIRS count per cell
    rain:  (rain on d, rain forecast for d+1) in mm, per cell
    """
    f = np.asarray(fre)
    l1 = np.log1p
    layers = [l1(f[0]), l1(f[1]), l1(f[2:7].sum(0)), l1(neigh(f[0])), l1(neigh(f[:3].sum(0))),
              l1(neigh(f[:7].sum(0))), l1(viirs), l1(neigh(viirs)), l1(neigh(f.sum(0), 9)), l1(clim),
              np.full((NY, NX), float(day_index)), np.full((NY, NX), float(weekday_next)), rain[0], rain[1]]
    return np.stack(layers, -1)


def export_model(est):
    """HistGradientBoosting classifier (binary) or regressor -> dict of arrays for predict_raw()."""
    trees = [p[0].nodes for p in est._predictors]
    nodes = np.concatenate(trees)
    offsets = np.cumsum([0] + [len(t) for t in trees])[:-1]
    return dict(feature=nodes["feature_idx"].astype("i4"), threshold=nodes["num_threshold"].astype("f8"),
                left=nodes["left"].astype("i4"), right=nodes["right"].astype("i4"),
                missing_left=nodes["missing_go_to_left"].astype("u1"), leaf=nodes["is_leaf"].astype("u1"),
                value=nodes["value"].astype("f8"), roots=offsets.astype("i4"),
                baseline=np.asarray(est._baseline_prediction, "f8").ravel())


def predict_proba(m, X):
    """P(fire) for rows of X with an exported classifier (numpy only)."""
    return 1 / (1 + np.exp(-predict_raw(m, X)))


def expected_harm(models, X, harm_per_kg):
    """P(fire) x expected energy (MJ, if it burns) x exposure per kg, per row; models = (classifier, regressor)."""
    return predict_proba(models[0], X) * np.expm1(predict_raw(models[1], X)) * harm_per_kg


def predict_raw(m, X):
    """Sum of tree outputs plus baseline (log-odds for the classifier, log1p(MJ) for the regressor)."""
    X = np.asarray(X, float)
    raw = np.full(len(X), m["baseline"][0])
    rows = np.arange(len(X))
    for root in m["roots"]:
        node = np.full(len(X), root)
        for _ in range(64):  # tree depth bound
            leaf = m["leaf"][node].astype(bool)
            if leaf.all():
                break
            x = X[rows, m["feature"][node]]
            go_left = np.where(np.isnan(x), m["missing_left"][node].astype(bool), x <= m["threshold"][node])
            nxt = root + np.where(go_left, m["left"][node], m["right"][node])
            node = np.where(leaf, node, nxt)
        raw += m["value"][node]
    return raw


def plan(score, k, block=3):
    """Greedy maximum coverage: k team blocks (block x block cells) covering the most total score.
    Returns [(row, col, covered_score)], centres of the blocks, in pick order."""
    s = np.nan_to_num(np.asarray(score, float)).copy()
    picks = []
    h = block // 2
    for _ in range(k):
        gain = neigh(s, block)
        r, c = np.unravel_index(np.argmax(gain), gain.shape)
        if gain[r, c] <= 0:
            break
        picks.append((int(r), int(c), float(gain[r, c])))
        s[max(r - h, 0):r + h + 1, max(c - h, 0):c + h + 1] = 0
    return picks


def covered(picks, block=3):
    m = np.zeros((NY, NX), bool)
    h = block // 2
    for r, c, _ in picks:
        m[max(r - h, 0):r + h + 1, max(c - h, 0):c + h + 1] = True
    return m


def payload(day, eh, pr, actual=None, k=20):
    """JSON for the page's "Send teams" view. `eh` and `pr` are (NY, NX) grids of expected harm and P(fire);
    `actual` (replays only) is the GK-2A fire energy that evening, to show how the plan did."""
    q = lambda g, scale: [int(round(v)) for v in (np.asarray(g) * scale).ravel()]
    total = float(eh.sum())
    out = dict(day=str(day), grid=dict(lat0=LAT0, lon0=LON0, d=D, ny=NY, nx=NX), k=k,
               expected_harm=q(eh / max(eh.max(), 1e-12), 1000), p_fire=q(pr, 100),
               teams=[dict(row=r, col=c, share=round(g / max(total, 1e-12), 4)) for r, c, g in plan(eh, k)])
    if actual is not None:
        out["actual_energy"] = q(np.log1p(actual), 100)
        cov = covered(plan(eh, k))
        out["actual_covered_share"] = round(float(actual[cov].sum() / max(actual.sum(), 1e-12)), 3)
    return out
