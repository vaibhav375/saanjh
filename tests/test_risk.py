import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor

from saanjh import risk


def test_numpy_trees_match_sklearn():
    rng = np.random.default_rng(0)
    X = rng.normal(size=(600, len(risk.FEATURES)))
    X[rng.random(X.shape) < 0.05] = np.nan  # missing values take the learned branch
    y = (X[:, 0] + 0.5 * np.nan_to_num(X[:, 3]) > 0.3).astype(int)
    clf = HistGradientBoostingClassifier(max_iter=30, random_state=0).fit(X, y)
    reg = HistGradientBoostingRegressor(max_iter=30, random_state=0).fit(X, np.nan_to_num(X[:, 1]) * 2)
    assert np.allclose(risk.predict_proba(risk.export_model(clf), X), clf.predict_proba(X)[:, 1], atol=1e-9)
    assert np.allclose(risk.predict_raw(risk.export_model(reg), X), reg.predict(X), atol=1e-9)


def test_greedy_plan_covers_hotspots_without_double_counting():
    s = np.zeros((risk.NY, risk.NX))
    s[10, 10], s[10, 11], s[30, 30] = 5.0, 4.0, 3.0  # two adjacent cells fit one 3x3 block
    picks = risk.plan(s, 3)
    assert len(picks) == 2  # the third team would add nothing
    assert picks[0][2] == 9.0 and picks[1][2] == 3.0
    assert risk.covered(picks)[[10, 10, 30], [10, 11, 30]].all()
