"""Collect the measured results into site/evidence.json for the page's evidence section."""
import json
import re

import numpy as np
import pandas as pd

ev = {}

s = pd.read_csv("results/season_2025.csv").sort_values("day")
ev["season"] = dict(
    year=2025, missed_share=round(float((s.fre_mj * s.uncounted_share).sum() / s.fre_mj.sum()), 3),
    days=[dict(day=r.day, missed_tj=round(r.fre_mj * r.uncounted_share / 1e6, 2),
               counted_tj=round(r.fre_mj * (1 - r.uncounted_share) / 1e6, 2)) for r in s.itertuples()])
s24 = pd.read_csv("results/season_2024.csv")
ev["season"]["missed_share_2024"] = round(float((s24.fre_mj * s24.uncounted_share).sum() / s24.fre_mj.sum()), 3)

pod = {}
for y in (2024, 2025):
    p = pd.read_csv(f"results/pod{y}_detections_pod.csv")
    pod[y] = [dict(bin=f"{int(r.frp_lo)}–{int(r.frp_hi)}" if r.frp_hi < 1e8 else f">{int(r.frp_lo)}",
                   pod=round(r.pod, 3), n=int(r.n)) for r in p.itertuples()]
ev["detection"] = pod

d = pd.read_csv("results/dusk_penalty_20241015_20241130.csv")
ev["dusk"] = {str(int(h)): dict(pooled=round(float(g.e17.sum() / g.e13.sum()), 2),
                                days=[dict(day=r.day, ratio=round(r.ratio, 2)) for r in g.itertuples()])
              for h, g in d.groupby("h_min")}

a = pd.read_csv("results/ablation_2025.csv")
ev["ablation"] = [dict(region=r.region, period=r.period, stations=int(r.stations), overpass=round(r.r_overpass, 3),
                       hybrid=round(r.r_hybrid, 3), ci=[float(x) for x in re.findall(r"[-+]?\d*\.\d+", r.ci_hybrid)])
                  for r in a.itertuples() if r.period in ("season", "Nov") or (r.region == "all" and r.period == "Oct")]

pl = pd.read_csv("results/risk_planner_2025.csv")
rows = []
for (k, m), g in pl.groupby(["k", "method"]):
    w = g.total / g.total.sum()
    rows.append(dict(teams=int(k), method=m, harm=round(float(np.average(g.harm, weights=w)), 3),
                     energy=round(float(np.average(g.energy, weights=w)), 3)))
ev["planner"] = rows

al = pd.read_csv("results/alert_replay_2025.csv")
ev["alerts"] = [dict(method=r.method, heidke=round(r.heidke, 3), hit=round(r.hit_rate, 3)) for r in al.itertuples()]

json.dump(ev, open("site/evidence.json", "w"), separators=(",", ":"))
print({k: (len(v) if isinstance(v, list) else list(v)) for k, v in ev.items()})
