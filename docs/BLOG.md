# How farmers outran the satellites, and how a Korean weather satellite on AWS caught up

*Draft for AWS Builder Center. Built during Environmental Hacks (AWS × WeMakeDevs), October 2026.*

Every autumn, North India's air turns hazardous, and every autumn the news quotes the same number: how many farm
fires satellites counted in Punjab and Haryana that day. In 2025 that number hit a seven-year low. The air did
not get much better. This post is about why, and about Saanjh ("dusk" in Hindi and Punjabi), the system I built to
see what the count misses and to warn people before the smoke arrives.

## The fires moved to dusk

The official count is built from NASA's polar-orbiting satellites, which pass over Punjab around 1:30 pm. Over
the past four years, farmers moved burning to 4–5 pm. A NASA study published this May used the Korean
geostationary satellite GK-2A to show the shift; iFOREST's 2025 report found over 90% of large fires now burn
after 3 pm. The count did not fall because fewer fields burned. It fell because the fires happen after the
satellites leave.

That matters twice. Fires the count never sees do not enter the air-quality forecasts built on it. And evening
smoke is worse: after sunset the layer of air that dilutes it collapses from about a kilometre to a few dozen
metres, right over the towns where people sleep and children line up for 8 am assembly.

## Reading a satellite where it lives

GK-2A images all of Asia every 10 minutes, and NOAA publishes every image to a public S3 bucket in us-east-1 with an
SNS notification for each new file. Each image is a 35 MB NetCDF file per band. I needed two bands (3.8 and
11.2 µm) for a small patch of the disk.

Two engineering choices made this work:

1. **Read one chunk, not the file.** The files are HDF5 with 1375×1375 compressed chunks. Punjab and Haryana fit in
   one chunk row, so an HTTP range read pulls ~4 MB instead of 35 MB.
2. **Compute next to the bucket.** From my laptop in India each crop still took ~17 seconds, so a season at 10-minute
   cadence was about a day of downloading. In us-east-1, a Lambda reads it in about a second. AWS Step Functions
   fans one Lambda run per day across the archive: 47 days of every 10-minute image in about 25 minutes, using the
   same code that serves the live system.

The live path is a few lines of SAM: NOAA's `NewGK2AObject` topic → an SQS queue → a detection Lambda; an hourly
EventBridge schedule runs the smoke model and publishes the page's data to S3; SNS emails alerts.

## Finding fires from 36,000 km away, at a slant

GK-2A sits over the Pacific at 128°E. It sees Punjab at about 66° from vertical, so its pixels there are ~4 km
across. A fire raises the 3.8 µm signal far more than 11.2 µm; Saanjh looks for pixels where that difference stands
out from their neighbours by several times the local noise.

Things that went wrong, and what they taught me:

- **An off-by-one.** My first detections did not line up with NASA's VIIRS fires at all. Searching for the shift that
  best aligned the two found exactly one row and one column: the projection's line and column numbers are 1-based.
- **"False alarms" that were real fires.** A third of detections had no VIIRS match, until I noticed they were in
  Pakistani Punjab, which the India-only FIRMS file leaves out.
- **A noise floor that hid the noise.** On some hot October days the detector fired thousands of times. The noise
  estimate came from quiet morning images and sat at its floor for 95% of pixels. Measuring noise from the current
  image's neighbourhood (as MODIS does), tuned on 2024 only, cut unmatched detections on the held-out 2025 season
  from 53% to 30% with no loss of detection.

I measured, rather than assumed, what GK-2A can see: about 3% of fires under 5 MW and about 43% of 40–80 MW fires.
It is a large-fire detector, and the numbers below are about the energy it can see.

## What the data says

- **86.8% (2024) and 91.7% (2025, held out)** of the fire energy GK-2A detected came from fires that started after
  the 1:30 pm overpass.
- **The dusk penalty.** I released the same smoke from real fire locations at 1 pm and at 5 pm into a particle model
  driven by ERA5 winds and boundary-layer height, and summed exposure over where people live. Evening smoke caused
  **2.8×** the people-hours of exposure, and was worse on all 47 days.
- **Does it explain real pollution?** Adding the missed fires to the overpass-based inventory made modelled smoke
  track measured PM2.5 at 33 CPCB stations near the fires better through the 2025 season (correlation 0.23 → 0.28,
  95% CI +0.02 to +0.10). In Delhi it made no difference.
- **A negative result.** A night-before smoke forecast did not beat "tomorrow morning will be like this morning" at
  picking the worst mornings. Bad mornings come in multi-day stagnation spells. So Saanjh's alerts say where and when
  farm smoke is heading, and tell schools to check the PM2.5 reading, rather than promising a forecast it cannot make.

## The product

The page shows tonight's fires and smoke on a map, with a time strip painted in the colours of the sky it covers,
marking the satellite pass and when each fire was first seen. District officers get the fires ranked by the people
who will breathe their smoke, and can ask an assistant (Strands Agents with Claude on Amazon Bedrock, read-only tools)
why a fire ranks where it does. Residents pick their town and get a notice in English, Hindi or Punjabi. Saanjh works
on a 2–4 km grid and never identifies farmers.

## What I'd do next

Fuse a second geostationary view (Meteosat over the Indian Ocean or India's own INSAT-3DS) for smaller fires;
calibrate the smoke model against CPCB stations in real time; and test alerts targeted at the farm-smoke share of
pollution rather than total PM2.5.

*Code and every number's provenance: https://github.com/vaibhav375/saanjh*
