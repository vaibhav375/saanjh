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
