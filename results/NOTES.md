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
