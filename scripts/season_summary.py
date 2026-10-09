"""N1 for a replayed season: pull results/<day>.json from the data bucket and summarise.

usage: season_summary.py DATA_BUCKET YYYY  ->  results/season_<YYYY>.csv, figures/season_<YYYY>.png
"""
import json
import sys

import boto3
import matplotlib
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

bucket, year = sys.argv[1], sys.argv[2]
s3 = boto3.client("s3", region_name="us-east-1")
rows, hours = [], {}
for p in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=f"results/{year}"):
    for o in p.get("Contents", []):
        d = json.loads(s3.get_object(Bucket=bucket, Key=o["Key"])["Body"].read())
        st = d["stats"]
        rows.append(dict(day=d["day"], events=st["events"], counted=st["counted"], fre_mj=st["fre_mj"],
                         uncounted_share=st["uncounted_energy_share"], pm25_t=st["pm25_t"]))
        for hm, c in st["first_seen"].items():
            hours[hm[:2]] = hours.get(hm[:2], 0) + c
r = pd.DataFrame(rows).sort_values("day")
r.to_csv(f"results/season_{year}.csv", index=False)
fre = r.fre_mj.sum()
print(f"{len(r)} days, {r.events.sum()} fire events, {fre / 1e6:.0f} TJ fire energy, {r.pm25_t.sum():.0f} t PM2.5")
print(f"season energy missed by the overpass: {(r.fre_mj * r.uncounted_share).sum() / fre:.1%}")
print("first seen by IST hour:", dict(sorted(hours.items())))

fig, ax = plt.subplots(1, 2, figsize=(13, 4.2), gridspec_kw=dict(width_ratios=[2, 1]))
x = pd.to_datetime(r.day)
ax[0].bar(x, r.fre_mj * (1 - r.uncounted_share) / 1e6, color="#D6A93F", label="burning at the polar overpass")
ax[0].bar(x, r.fre_mj * r.uncounted_share / 1e6, bottom=r.fre_mj * (1 - r.uncounted_share) / 1e6,
          color="#EE5A24", label="started after it (missed)")
ax[0].set_ylabel("fire radiative energy (TJ / day)")
ax[0].legend(frameon=False)
ax[0].set_title(f"Punjab + Haryana, {year}: daily fire energy seen by GK-2A")
h = pd.Series(hours).sort_index()
ax[1].bar(h.index, h.values, color=["#EE5A24" if int(k) >= 14 else "#D6A93F" for k in h.index])
ax[1].axvline(1.5, color="#555", ls="--", lw=1)
ax[1].text(1.6, h.max() * 0.95, "polar overpass ~13:30", fontsize=8)
ax[1].set_title("fire events by hour first seen (IST)")
for a in ax:
    a.spines[["top", "right"]].set_visible(False)
plt.tight_layout()
plt.savefig(f"figures/season_{year}.png", dpi=110)
