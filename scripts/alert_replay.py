"""N5, the alert replay: would Saanjh's night-before warning have picked the bad school mornings?

For every station and night of the season, the warning is decided at 21:30 IST from smoke already
emitted by fires seen that day (the modelled farm smoke for 06:00-10:00 IST next morning comes only
from fires that burned before the warning). The event is the next morning's measured 06-10 IST PM2.5
being in that station's worst third of mornings. Each method warns on the same number of mornings per
station (its own top third), so hit rates compare fairly:
  saanjh       modelled smoke from GK-2A fires (inventory B)
  overpass     modelled smoke from the VIIRS overpass inventory (A)
  persistence  this morning was in the worst third, so tomorrow will be
  persistence+X  equal-weight average of the two predictors' within-station ranks (nothing fitted)
Weather is ERA5 (a perfect-weather replay); the live system uses forecasts.

usage: alert_replay.py YEAR    (needs results/ablation_model_<YEAR>.pkl and data/pm25_<YEAR>.csv)
"""
import sys

import numpy as np
import pandas as pd

year = sys.argv[1]
model = pd.read_pickle(f"results/ablation_model_{year}.pkl")
obs = pd.read_csv(f"data/pm25_{year}.csv", parse_dates=["datetime"])
obs["datetime"] = (obs.datetime + pd.Timedelta(minutes=30)).dt.floor("h")
obs = obs[(obs.value > 0) & (obs.value < 1500)].pivot_table(index="datetime", columns="location_id", values="value")


def mornings(df):
    """Mean over 06:00-10:00 IST, indexed by the date of that morning (IST)."""
    ist = df.index + pd.Timedelta(hours=5, minutes=30)
    m = df[(ist.hour >= 6) & (ist.hour < 10)]
    return m.groupby((m.index + pd.Timedelta(hours=5, minutes=30)).date).mean()


o = mornings(obs.reindex(columns=model["A"].columns))
pred = {"saanjh": mornings(model["B"]), "overpass": mornings(model["A"])}
pred["persistence"] = o.shift(1)  # yesterday morning's value, known at 21:30 the night before
# Combined warnings: equal-weight average of within-station percentile ranks (nothing fitted).
rank = lambda df: df.rank(pct=True)
pred["persistence+saanjh"] = (rank(pred["persistence"]) + rank(pred["saanjh"].reindex_like(pred["persistence"]))) / 2
pred["persistence+overpass"] = (rank(pred["persistence"]) + rank(pred["overpass"].reindex_like(pred["persistence"]))) / 2
days = [d for d in o.index if pd.Timestamp(d).month in (10, 11) and pd.Timestamp(d) >= pd.Timestamp(f"{year}-10-17")]
o = o.loc[days]
event = o.ge(o.quantile(2 / 3))

rows = []
for name, p in pred.items():
    p = p.reindex(index=days, columns=o.columns)
    ok = o.notna() & p.notna()
    warn = p.ge(p.where(ok).quantile(2 / 3)) & ok
    ev = event & ok
    hits, misses, fa = (warn & ev).sum().sum(), (~warn & ev & ok).sum().sum(), (warn & ~ev & ok).sum().sum()
    cn = (~warn & ~ev & ok).sum().sum()
    n = hits + misses + fa + cn
    expected = ((hits + misses) * (hits + fa) + (cn + misses) * (cn + fa)) / n
    rows.append(dict(method=name, station_mornings=int(n), hit_rate=hits / (hits + misses),
                     false_alarm_ratio=fa / (hits + fa), heidke=((hits + cn) - expected) / (n - expected)))
r = pd.DataFrame(rows)


def heidke(name, pick):
    p = pred[name].reindex(index=days, columns=o.columns).loc[pick]
    oo, ev0 = o.loc[pick], event.loc[pick]
    ok = oo.notna() & p.notna()
    w = p.ge(p.where(ok).quantile(2 / 3)) & ok
    ev = ev0 & ok
    h, m, f, c = [(x).sum().sum() for x in (w & ev, ~w & ev & ok, w & ~ev & ok, ~w & ~ev & ok)]
    n = h + m + f + c
    e = ((h + m) * (h + f) + (c + m) * (c + f)) / n
    return ((h + c) - e) / (n - e)


rng = np.random.default_rng(0)
diff = [heidke("persistence+saanjh", pick) - heidke("persistence+overpass", pick)
        for pick in (rng.choice(days, len(days)) for _ in range(300))]
print("Heidke gain of persistence+saanjh over persistence+overpass: %+.3f, 95%% CI [%+.3f, %+.3f]"
      % (np.mean(diff), *np.percentile(diff, [2.5, 97.5])))
r.to_csv(f"results/alert_replay_{year}.csv", index=False)
print(r.round(3).to_string(index=False))
