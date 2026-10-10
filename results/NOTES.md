# Results log

## N2: GK-2A detection vs VIIRS at overpass, 2024 tuning set (10 peak days, Oct 28 – Nov 19)

`scripts/eval_pod.py data/firms/viirs_snpp_2024_punjab_both_octnov.csv results/pod2024 6`
(VIIRS SNPP India + Pakistan; a VIIRS-fire pixel counts as detected if GK-2A flags it or a neighbour in
either scan bracketing the overpass; z threshold 6.)

Probability of detection by summed VIIRS FRP in the AMI pixel: see `pod2024_pod.csv`.
4% below 5 MW, 10% at 5–10 MW, 16% at 10–20 MW, 32% at 20–40 MW, 51% at 40–80 MW, 44% above 80 MW (n=25).
79% of GK-2A detections have a VIIRS fire within one pixel (443 detections).

Lesson: the first run showed 46% unmatched detections. Mapping them showed most were in Pakistani
Punjab, which the India-only FIRMS file leaves out. Scoring against both countries fixed it.

This is the hardest hour for a geostationary sensor (13:30–14:00 IST, solar heating of the soil).
For reference, INSAT-3DS reports POD 45% / precision 73% against MODIS (Singh et al. 2025).

## N3: the dusk penalty (pilot, 10–19 Nov 2024)

`scripts/dusk_penalty.py 2024-11-10 2024-11-19 <h_min>`: 1 kg PM2.5 released from 150 real 2024 VIIRS
fire locations in Punjab/Haryana at 13:00 vs 17:00 IST, followed 36 h on ERA5 100 m winds and
boundary-layer height, exposure summed over WorldPop 2020 (India only).

| Plume injection floor | Exposure ratio 17:00 / 13:00 (pooled) | Daily range |
| --- | --- | --- |
| 100 m | 4.4× | 2.6–7.6 |
| 200 m (default) | 3.2× | 2.3–5.1 |
| 400 m | 2.0× | 1.6–2.9 |
| 800 m | 1.3× | 1.0–1.7 |

The same fire lit at 5 pm instead of 1 pm causes 2–4× the population exposure for plausible injection
heights, and is never better at any floor tested. Mechanism: the afternoon boundary layer at Ludhiana on
18 Nov 2024 was 830 m at 15:00 IST, 70 m at 18:00 and 40 m at 21:00 (ERA5), so evening smoke is
trapped near the ground overnight while afternoon smoke stays diluted in the residual layer.
Caveats: no Pakistan population (receptors east of the border dominate under NW winds); no chemistry;
uniform mixing within H_p.

## End-to-end evening, 18 Nov 2024 (hourly scans 12:00–21:00 IST)

500 GK-2A fire events in Punjab/Haryana. First-seen times peak at 16:00 IST (237 events); 98% of fire
energy is in events first seen at or after 14:00 IST. Only 50 events were already burning at the VIIRS
overpass with VIIRS fire in the pixel: **87% of the day's detected fire energy was uncounted.**
Smoke arrives at Fazilka/Muktsar 17–18 IST, Sangrur 23 IST, Sirsa 01 IST, Noida/Ghaziabad 04–07 IST next day.

## N1: the 2024 season, replayed in the cloud (15 Oct – 30 Nov, every 10-minute GK-2A image)

Step Functions → 47 parallel day runs of the same Lambdas that serve the live system (~90 s per day).
`scripts/season_summary.py <data bucket> 2024` → `results/season_2024.csv`, `figures/season_2024.png`.

- 45,342 fire events; 1,092 TJ of fire radiative energy; ~2,500 t PM2.5 (from the energy, before any
  correction for fires too small for GK-2A to see).
- **90.8% of the season's detected fire energy came from fires that started after the polar overpass.**
  iFOREST, using Meteosat, independently reports over 90% of large fires after 3 pm (2024–2025).
- Fire events by hour first seen (IST): 12h 1,201 · 13h 2,723 · 14h 4,231 · 15h 12,670 · **16h 14,440** · 17h 7,023 ·
  18h 760 · 19h 1,103 · 20h 1,007 · 21h 184.
- Daily energy peaks on 31 Oct–1 Nov (Diwali) and 17–19 Nov (Delhi's "severe+" week), as expected.

Caveats: the share is of energy GK-2A can see, which favours larger fires; midday detection is harder than
evening (solar heating), which can push the share up. The 18:00 dip is likely the sunset threshold change
in the detector, not a real lull.

## N3, full season (15 Oct – 30 Nov 2024, 47 days)

`scripts/dusk_penalty.py 2024-10-15 2024-11-30 200 400` → `results/dusk_penalty_20241015_20241130.csv`

| Plume injection floor | Pooled exposure ratio 17:00 / 13:00 | Daily mean | Daily range | Days where dusk is worse |
| --- | --- | --- | --- | --- |
| 200 m | **2.9×** | 3.2× | 1.5–5.2× | 47 / 47 |
| 400 m | **1.9×** | 2.0× | 1.4–2.9× | 47 / 47 |

## Detector revision (tuned on 2024 only, then frozen)

Scoring the whole 2024 season (43 days with VIIRS) showed unmatched detections rising on quiet days, concentrated
on 20 Oct and 14–15 Nov at 28–29°N (Thar desert edge) with zero 3.8 µm excess: a cold 11.2 µm pixel, not a fire.
Added the MODIS-style requirement that 3.8 µm itself exceeds its neighbourhood by 0.5 K. Effect on 2024:
detection by FRP bin unchanged; unmatched detections 46% → ~33% (season) and 21% → 16% (10 peak days).
Both seasons were re-run in the cloud with the frozen detector; 2025 was never used for tuning.

## Data gap

OpenAQ has no CPCB station data for 2023–2024 (old sensor ids end Oct 2022, new ones start 2025), so the
PM2.5 tests (N4, N5) use the 2025 season only.

## Both seasons with the frozen detector (cloud replays, every 10-minute image, 15 Oct – 30 Nov)

| Season | Fire events | Fire energy | PM2.5 (from detected energy) | Energy from fires started after the overpass |
| --- | --- | --- | --- | --- |
| 2024 (tuning) | 38,908 | 1,090 TJ | 2,510 t | **90.9%** |
| 2025 (held out) | 46,203 | 1,510 TJ | 3,478 t | **95.1%** (95.0% without 18–21 Oct) |

Official polar-orbiter counts called 2025 a low year; the fire energy GK-2A sees was 39% higher than 2024.
Treat as indicative: detection depends on clouds and haze, and 18–21 Oct 2025 contains false alarms (below).

## N2 held out on 2025 (`eval_pod.py ... --cloud`, 46 days, frozen threshold)

Probability of detection by summed VIIRS FRP per pixel: 3% (<5 MW), 7% (5–10), 11% (10–20), 24% (20–40),
43% (40–80), 37% (>80 MW, n=41): the same curve as 2024. Unmatched detections: 53% over all days, **34%
excluding 18–21 Oct 2025**, when weak (~5 MW) detections scattered 30–50 km from any VIIRS fire across the
region (not a navigation offset: no consistent shift). Cause not yet diagnosed; those days are 5.9% of the
season's detected energy. Median unmatched per day: 3 (2025) vs 4 (2024).

## N4: the ablation, 2025 held-out season (`scripts/ablation.py 2025`)

Same smoke model and ERA5 weather, two inventories: **A** VIIRS fires at the overpass with the midday-peaked
diurnal profile operational inventories assume; **B** Saanjh's GK-2A fires at the times they were seen.
Score: Pearson r between daily station-mean anomalies of modelled farm smoke and measured PM2.5
(82 CPCB stations via OpenAQ), with a 500-sample bootstrap over days for the gain B − A.

| Stations | Period | r (overpass-only) | r (Saanjh) | Gain [95% CI] |
| --- | --- | --- | --- | --- |
| Punjab/Haryana/W-UP (33) | season | 0.23 | 0.28 | +0.06 [0.00, +0.12] |
| Punjab/Haryana/W-UP | Nov | 0.21 | 0.29 | **+0.08 [+0.01, +0.16]** |
| All (82) | Oct | 0.13 | 0.26 | **+0.13 [+0.04, +0.22]** |
| All (82) | season | 0.28 | 0.33 | +0.05 [−0.01, +0.11] |
| Delhi-NCR (49) | season | 0.36 | 0.37 | +0.01 [−0.07, +0.08] |

Adding the evening fires the overpass misses makes modelled smoke track measured PM2.5 better near the fires,
significantly in November there and across all stations in October. In Delhi there is no difference: local
sources dominate and both inventories share the same transport. At the hourly scale neither inventory explains
much (R² < 0.04 after removing each station's diurnal cycle), so Saanjh's alerts are about which nights and
which towns, not exact hours. (First run had a bug: OpenAQ stamps hourly means at xx:30 UTC; fixed by using
the hour midpoint.)

## N5: the alert replay, 2025 held out (`scripts/alert_replay.py 2025`) — a negative result

Question: would a warning decided at 21:30 IST from that day's fires have picked the mornings (06–10 IST) whose
measured PM2.5 was in a station's worst third? Each method warns on its own top third of mornings per station.
ERA5 weather (perfect-weather replay). 82 stations, ~3,400 station-mornings.

| Method | Hit rate | False-alarm ratio | Heidke skill |
| --- | --- | --- | --- |
| Saanjh smoke forecast | 0.60 | 0.54 | 0.23 |
| Overpass-inventory smoke forecast | 0.55 | 0.52 | 0.24 |
| Persistence (this morning was bad → tomorrow will be) | 0.59 | 0.42 | **0.37** |
| Persistence + Saanjh (equal-weight ranks) | 0.58 | 0.42 | 0.35 |
| Persistence + overpass | 0.57 | 0.43 | 0.35 |

Persistence beats both smoke forecasts, and adding modelled smoke to it does not help (Saanjh vs overpass on
top of persistence: +0.001, 95% CI [−0.07, +0.08]). Exploratory split by the regions defined for N4: same
picture; near the fires Saanjh has the highest hit rate (0.69) but more false alarms.

Reading: polluted mornings come in multi-day stagnation spells that persistence captures; farm smoke is one
contributor among many, and the model's hourly skill is low (N4). Saanjh's demonstrated value is in seeing the
fires the count misses (N1, N2), ranking them by downwind harm (N3), and explaining more of the day-to-day PM2.5
near the fires (N4). Its alerts should say "farm smoke is heading to your town tonight", alongside the station
reading, not promise to beat a persistence forecast of a bad morning. Next step: warn only when predicted
farm smoke is a large share of the expected level, and test that.

## Detector v3: scan-local noise (the fix for the October 2025 false alarms)

Diagnosis: the morning-scan noise estimate sat at its 0.3 K floor for 95–98% of plains pixels, so z was in effect
a fixed 2 K threshold; on hot, patchy afternoons ordinary surface heating crossed it (7,787 detections on
20 Oct 2025). A 10-minute persistence rule did not help (those pixels persist; it halved detection instead).
Fix: divide by max(morning noise, the current scan's robust spread of the dT excess in an 11×11 window), the
MODIS background-statistics approach; threshold re-tuned on 2024 only (z = 4), then frozen.

| Season | Unmatched detections, v2 → v3 | POD 20–40 MW, v2 → v3 | POD 40–80 MW, v2 → v3 |
| --- | --- | --- | --- |
| 2024 (tuning, 43 days) | 29% → **17%** | 0.26 → 0.27 | 0.43 → 0.44 |
| 2025 (held out, 46 days) | 53% → **30%** | 0.24 → 0.24 | 0.43 → 0.43 |

Season totals with v3 (supersede the v2 numbers above):

| Season | Fire events | Fire energy | PM2.5 (from detected energy) | Energy from fires started after the overpass |
| --- | --- | --- | --- | --- |
| 2024 | 27,235 | 657 TJ | 1,514 t | **86.8%** |
| 2025 (held out) | 29,333 | 729 TJ | 1,679 t | **91.7%** |

The earlier "2025 energy 39% above 2024" was inflated by the false alarms; with v3 it is +11%, too small to claim.

## N3 with height-aware winds (smoke in shallow night layers moves with 10 m winds)

Pooled 17:00/13:00 exposure ratio, 47 days of 2024: **2.8×** at a 200 m floor (was 2.9×), **1.9×** at 400 m
(unchanged); daily minimum 1.48× and 1.41×, so evening burning is worse on all 47 days. The result does not
depend on which wind level carries the smoke.

## N4 and N5 after the improvements (detector v3, height-aware winds, hybrid inventory)

Inventory C ("hybrid") = the overpass inventory A plus only the GK-2A fires it missed: how Saanjh would be added
to an existing forecast. Daily-anomaly correlation with measured PM2.5, 2025 held out, bootstrap over days:

| Stations | Period | r overpass (A) | r GK-2A only (B) | r hybrid (C) | Gain C − A [95% CI] |
| --- | --- | --- | --- | --- | --- |
| Punjab/Haryana/W-UP (33) | season | 0.23 | 0.27 | **0.28** | **+0.06 [+0.02, +0.10]** |
| Punjab/Haryana/W-UP | Nov | 0.20 | 0.28 | 0.28 | **+0.08 [+0.02, +0.14]** |
| All (82) | Oct | 0.14 | 0.22 | 0.24 | **+0.10 [+0.03, +0.16]** |
| All (82) | season | 0.29 | 0.30 | 0.33 | +0.04 [−0.01, +0.09] |
| Delhi-NCR (49) | season | 0.37 | 0.34 | 0.37 | 0.00 [−0.06, +0.07] |

Adding the missed fires to today's inventory improves day-to-day PM2.5 tracking near the fires over the whole
season (CI excludes zero), and never hurts in Delhi. GK-2A alone is not better than the hybrid: the overpass
inventory still carries the small fires GK-2A cannot see, so the two satellites complement each other.

Alerts (Heidke skill, top-third mornings): persistence 0.370; persistence + hybrid smoke 0.375 (all days),
0.323 vs 0.328 (November). A +0.005 gain is within noise: N5 stays negative.

Tried and rejected: a 10-minute persistence rule (halved detection, no precision gain); a fitted MOS combination
(unstable: early-October smoke is near zero at many stations, so its October-based standardisation blew up in
November).

## N6: tomorrow's fire risk and where to send teams (`scripts/build_risk.py`)

0.1° cells (~11 km) over Punjab/Haryana farmland (1,135 cells with VIIRS fire in the two prior seasons). Features
known by the evening of day d: GK-2A fire energy in the cell and its 5×5 / 9×9 neighbourhood over 1–7 days (the
harvest-burning wave), yesterday's VIIRS count, last season's VIIRS count, rain on d and d+1, day of season,
weekday. Two HistGradientBoosting models (P(fire tomorrow); expected energy if it burns), trained on 2024, tested on
2025; trees exported to numpy (identical predictions, unit-tested) so the Lambda needs no scikit-learn.

Prediction, 2025 held out (base rate 18% of cell-days burn): ROC AUC **0.90**, average precision **0.73**; yesterday's
VIIRS count alone: 0.59 / 0.27.

Team placement: K teams, each a 3×3-cell (~33 km) patrol block, greedy maximum coverage ((1 − 1/e)-optimal) of
expected harm = P(fire) × expected energy × population exposure per kg released at 17:00 IST under that day's
weather. The formula was chosen on a 2024-only split (first half train, second half validate) before the 2025 test.
Share of next-evening smoke harm covered, 2025, energy-weighted over days [bootstrap 95% CI]:

| Placement | 10 teams | 20 teams |
| --- | --- | --- |
| **Saanjh: expected harm** | **57%** [53–60] | **75%** [73–77] |
| Saanjh: risk only | 48% | 68% |
| Yesterday's GK-2A fires | 47% | 65% |
| Last season's hotspots | 22% | 36% |
| Chase yesterday's VIIRS (officially counted) fires | 16% | 31% |

With the same 20 teams, Saanjh's noon plan covers 2.4× the evening's smoke harm that chasing yesterday's counted fires
does. Most of that comes from seeing the evening fires at all; the model adds ~10 points over reusing yesterday's
GK-2A fires. Caveat: harm weights used ERA5 (actual) weather; the live plan uses forecasts.
