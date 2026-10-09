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
