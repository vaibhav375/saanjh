# How farmers outran the satellites, and how a Korean weather satellite on AWS caught up

*Draft for AWS Builder Center. Built during Environmental Hacks (AWS × WeMakeDevs), October 2026.*

Every autumn, North India's air turns hazardous, and every autumn the news quotes the same number: how many farm
fires satellites counted in Punjab and Haryana that day. In 2025 that number hit a seven-year low. The air did
not get much better. This post is about why, and about Saanjh ("dusk" in Hindi and Punjabi), the system I built to
see what the count misses, warn towns before the smoke arrives, and tell field teams where to be before the fires
are lit.

## The fires moved to dusk

The official count is built from polar-orbiting satellites, which pass over Punjab around 1:30 pm. Over the past
four years, farmers moved burning to 4–5 pm. NASA scientist Hiren Jethva used the Korean geostationary satellite
GK-2A to show the shift; iFOREST's 2025 report found over 90% of large fires now burn after 3 pm. In November 2024
the Supreme Court directed the Centre and the air-quality commission (CAQM) to get fire data from geostationary
satellites instead. The count did not fall only because fewer fields burned. It fell because the fires happen
after the satellites leave.

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

## The system on AWS

Everything is one AWS SAM template:

- **Live detection:** NOAA's `NewGK2AObject` SNS topic → an SQS queue (with a dead-letter queue after three failed
  tries) → a detection Lambda that writes each image's fires to S3.
- **Hourly smoke model:** EventBridge Scheduler runs a Lambda from 12:35 to 00:35 IST that builds tonight's fire
  list, runs the smoke ensemble, publishes the page's data to S3 and emails town alerts through SNS.
- **Noon plan:** a second schedule runs the fire-risk model and team planner at 11:30 IST.
- **Season replays:** a Step Functions Map over the archive, reusing the same Lambdas.
- **Serving:** Lambda Function URLs for the page, an open JSON API (OpenAPI 3.1 spec, docs at `/api`), and a
  one-page district briefing PDF generated on demand in Lambda.
- **Assistant:** Strands Agents with open-weight Qwen3 on Amazon Bedrock, with read-only tools over the night's data,
  so an officer can ask why a fire ranks where it does.
- **Operations:** the Lambdas emit CloudWatch embedded metrics (images processed, detections, latency from image to
  result). Alarms cover errors, pipeline lag, queue backlog and failed images, feeding an ops email topic and a
  dashboard; the page's System chip reads the same numbers. GitHub Actions runs the tests and lints the template on
  every push.

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
It is a large-fire detector, so the missed energy below is a floor, not a total.

## What the data says

- **86.8% (2024) and 91.7% (2025, held out)** of the fire energy GK-2A detected came from fires that started after
  the 1:30 pm overpass.
- **A second satellite agrees.** The obvious question is whether those evening detections are real. VIIRS passes
  again at about 1:30 am. Evening fires GK-2A saw for 30 minutes or more, 61% of the missed energy, show up in that
  night pass 3.0× as often as the same places on other nights (95% CI 1.8–4.7), about as strongly as fires VIIRS
  itself confirmed at 1:30 pm. Fires seen in a single image are not confirmed; without them the headline is still
  89.5% (2025) and 83.0% (2024).
- **The dusk penalty.** I released the same smoke from real fire locations at 1 pm and at 5 pm into a particle model
  driven by ERA5 winds and boundary-layer height, and summed exposure over where people live. Evening smoke caused
  **2.8×** the people-hours of exposure, and was worse on all 47 days.
- **Does it explain real pollution?** Adding the missed fires to the overpass-based inventory made modelled smoke
  track measured PM2.5 at CPCB stations near the fires better through the 2025 season (correlation 0.23 → 0.28,
  95% CI +0.02 to +0.10). In Delhi it made no difference.
- **Prevention works better than chasing.** A gradient-boosted fire-risk model (ROC AUC 0.90 on 2025, a season it
  never saw) multiplied by where each cell's smoke would go gives an expected-harm map at noon. Twenty field teams
  placed on it cover 75% of that evening's smoke harm, against 31% for teams sent to yesterday's counted fires.
- **A negative result.** A night-before smoke forecast did not beat "tomorrow morning will be like this morning" at
  picking the worst mornings. Bad mornings come in multi-day stagnation spells. So Saanjh's alerts say where and when
  farm smoke is heading, and tell schools to check the PM2.5 reading, rather than promising a forecast it cannot make.

## The product

The page is a 3D map of tonight, with a timeline painted in the colours of the sky it covers. It marks the
satellite pass and when each fire was first seen. A short tour walks a first-time visitor through it.

- **Fires**, ranked by the people who will breathe their smoke, each with its 10-minute fire-power curve and an
  "Ask Saanjh why" button.
- **Smoke**, hour by hour across 9 weather scenarios. Each town gets its arrival time, peak, chance of passing
  25 µg/m³, which fires and which state the smoke came from, and a notice in English, Hindi or Punjabi.
- **Teams**, the noon plan, with the fires that actually burned that evening overlaid on replays.
- **Districts**, two seasons of official counts set against the fire energy GK-2A saw. Sangrur's count fell 69%
  from 2024 to 2025 while the energy rose 15%; Bathinda −59% and +55%. Each district has a printable briefing for
  tonight.

Saanjh works on a 2–4 km grid and never identifies farmers or plots.

## What isn't proven yet

Fires under ~10 MW are mostly invisible to GK-2A. Single-image detections (22% of evening energy) are unconfirmed.
Hourly smoke timing has little skill. The pollution checks use 2025 only, because OpenAQ has no CPCB station data
for 2023–24. And no officer or school has used Saanjh yet; that is the next test.

## What I'd do next

Fuse a second geostationary view (Meteosat over the Indian Ocean, or India's own INSAT-3DS) for smaller fires and
to confirm single-image detections; calibrate the smoke model against CPCB stations in real time; and run the noon
plan with one district's field teams for a season.

*Code, data provenance and every number's source: https://github.com/vaibhav375/saanjh*
