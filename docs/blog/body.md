At about 1:30 every afternoon, NASA and NOAA satellites cross Punjab and Haryana and record every farm fire burning below. That snapshot becomes India's official stubble-fire count, the number quoted in the news each autumn and used in air-quality forecasts. In 2025 the count fell to a seven-year low. The air over North India did not get much better.

The reason is simple: the fires moved. Farmers now burn at 4 or 5 pm, after the satellites have passed. This post is about Saanjh ("dusk" in Hindi and Punjabi), a system I built on AWS that watches the hours the official count can't see. It finds the evening fires, follows their smoke to the towns that will breathe it, and tells field teams where to be before the fires are lit.

## What happens after the satellites pass

NASA scientist Hiren Jethva used the Korean geostationary satellite GK-2A to show that Punjab's burning has moved to 4–6 pm. iFOREST's 2025 report found that over 90% of large fires now start after 3 pm. In November 2024 the Supreme Court directed the Centre and the air-quality commission (CAQM) to get farm-fire data from geostationary satellites instead of relying on the polar orbiters.

The late shift matters twice over:

- **The fires go uncounted.** A fire that starts at 4 pm is never in the count, so it is missing from every forecast built on that count.
- **Evening smoke does more harm.** After sunset, the layer of air that dilutes smoke collapses from about a kilometre to a few dozen metres, right over the towns where people sleep and children line up for 8 am assembly.

*[Insert image: `evening_fires.png`. Caption: 18 November 2024 as GK-2A saw it: two strong fires at the 1:40 pm pass, seventy-eight three hours later.]*

## A satellite that never leaves

GK-2A sits 36,000 km above the Pacific and images all of Asia every 10 minutes. NOAA publishes every image to a public S3 bucket in us-east-1 (`noaa-gk2a-pds`) and announces each new file on an SNS topic. That made AWS the natural place to build: the data, its notifications and the compute are all in one region.

Each image is a 35 MB file per band, and I need two bands (3.8 µm and 11.2 µm) for a small patch of the disk. Two choices made it fast enough:

1. **Read one chunk, not the file.** The files are HDF5 with 1375×1375 compressed chunks, and Punjab and Haryana fit in a single chunk row. Opening the object over HTTP and slicing only the window pulls about 4 MB instead of 35 MB:

```python
fs = fsspec.filesystem("https")
with fs.open(url, block_size=2**20, cache_type="blockcache") as f, h5py.File(f, "r") as h:
    counts = h["image_pixel_values"][l0:l1, c0:c1]   # only the chunks covering the window are fetched
```

2. **Compute next to the bucket.** From my laptop in India each crop took about 17 seconds, so a season at 10-minute cadence was a day of downloading. In us-east-1, a Lambda reads one in about a second, and AWS Step Functions replays 47 days of every 10-minute image in about 25 minutes.

## The pipeline on AWS

Everything is one AWS SAM template, and the same Lambda code serves the live system and the season replays.

*[Insert image: `architecture.png`. Caption: Saanjh on AWS. One SAM template; the same Lambdas run the live system and the season replays.]*

- **Live detection:** NOAA's `NewGK2AObject` SNS topic → an SQS queue, with a dead-letter queue after three failed tries → a detection Lambda that writes each image's fires to S3.
- **Hourly smoke model:** EventBridge Scheduler runs a Lambda from 12:35 to 00:35 IST. It builds tonight's fire list, runs the smoke model across 9 weather scenarios, publishes the page's data to S3 and emails town alerts through Amazon SNS.
- **Noon plan:** a second schedule runs the fire-risk model and team planner at 11:30 IST.
- **Season replays:** a Step Functions Map over the archive.
- **Serving:** Lambda Function URLs for the web page and an open JSON API (OpenAPI 3.1, docs at `/api`). A one-page district briefing PDF is generated on demand in Lambda.
- **Assistant:** the Strands Agents SDK with open-weight Qwen3 on Amazon Bedrock, with read-only tools over the night's data, so an officer can ask why a fire ranks where it does.
- **Operations:** the Lambdas emit CloudWatch embedded metrics: images processed, detections, and latency from image to result. Alarms on errors, pipeline lag, queue backlog and failed images feed an ops email topic and a dashboard, and the page's System chip reads the same numbers. GitHub Actions runs the tests and lints the template on every push.

## Finding a fire from 66° off vertical

From 128°E, GK-2A sees Punjab at a steep slant, so its pixels there are about 4 km across. A fire raises the 3.8 µm signal far more than the 11.2 µm one, so Saanjh flags pixels where that difference stands out from their neighbours by several times the local noise. Getting there took three corrections:

- **An off-by-one.** My first detections did not line up with NASA's VIIRS fires at all. Searching for the best-aligning shift found exactly one row and one column: the projection's line and column numbers are 1-based.
- **"False alarms" that were real fires.** A third of detections had no VIIRS match, until I mapped them and found them in Pakistani Punjab, which the India-only FIRMS file leaves out.
- **A noise floor that hid the noise.** On hot October days the detector fired thousands of times. Its noise estimate came from quiet morning images and sat at its floor for 95% of pixels. Measuring noise from each image's own neighbourhood, tuned on 2024 only, cut unmatched detections on the held-out 2025 season from 53% to 30% with no loss of detection.

I also measured what GK-2A can see instead of assuming it: about 3% of fires under 5 MW and about 43% of 40–80 MW fires. It is a large-fire detector, so the missed energy below is a floor, not a total.

## What the satellites miss

Every method was tuned on the 2024 season and then tested on 2025, a season it never saw.

- **Most of the fire comes after the pass.** 86.8% of the fire energy GK-2A detected in 2024, and 91.7% in 2025, came from fires that started after the 1:30 pm overpass.
- **A second satellite confirms it.** VIIRS passes again around 1:30 am. Evening fires GK-2A saw for 30 minutes or more, 61% of the missed energy, show up in that night pass 3.0× as often as the same places on other nights (95% CI 1.8–4.7), about as strongly as fires VIIRS itself confirmed at 1:30 pm. Fires seen in a single image aren't confirmed, and without them the headline is still 89.5% (2025) and 83.0% (2024).
- **Evening smoke does more harm.** I released the same smoke from real fire locations at 1 pm and at 5 pm into a particle model driven by ERA5 winds and boundary-layer height. The 5 pm release caused 2.8× the people-hours of exposure, and was worse on all 47 days.
- **It shows up in real pollution.** Adding the missed fires made modelled smoke track measured PM2.5 at CPCB stations near the fires better through 2025 (correlation 0.23 → 0.28, 95% CI +0.02 to +0.10). In Delhi, where local sources dominate, it made no difference.

## Acting before dusk

Seeing the evening fires helps only if someone can act on them. Saanjh adds three things for the people who have to:

- **A noon plan.** A gradient-boosted fire-risk model (ROC AUC 0.90 on 2025) is combined with where each area's smoke would travel to give an expected-harm map by 11:30. Twenty field teams placed on it cover 75% of that evening's smoke harm, against 31% for teams sent to yesterday's counted fires.
- **Town notices.** Each town gets the hour farm smoke arrives, its peak, the chance of passing 25 µg/m³ across the weather scenarios, which fires sent it, and a notice in English, Hindi or Punjabi.
- **District accountability.** For each of 43 districts, Saanjh sets the official count against the fire energy GK-2A saw. From 2024 to 2025, Sangrur's count fell 69% while its fire energy rose 15%; Bathinda's fell 59% while energy rose 55%. Counting only fires seen for 30 minutes or more, the rise holds in both. Officers can download a one-page briefing for their district.

*[Insert image: `town.png`. Caption: Moga on 10 November 2025: farm smoke from 17:00, and the fires it comes from.]*

The web page shows all of this on a 3D map of tonight, with a timeline painted in the colours of the sky it covers. Saanjh works on a 2–4 km grid and never identifies farmers or plots.

## What isn't proven yet

- Fires under about 10 MW are mostly invisible to GK-2A.
- Single-image detections (22% of evening energy) are unconfirmed by any other source.
- The smoke model's hourly timing has little skill, so notices say which nights and towns, not exact hours.
- A night-before forecast does not beat "tomorrow morning will be like this morning" at picking the worst mornings, so Saanjh doesn't promise one.
- The pollution checks use 2025 only, because OpenAQ has no CPCB station data for 2023–24.
- No officer or school has used it yet.

## What's next

Next I'd add a second geostationary view (Meteosat over the Indian Ocean, or India's own INSAT-3DS) to catch smaller fires and confirm single-image detections. I'd also calibrate the smoke model against CPCB stations in real time and run the noon plan with one district's field teams for a full season.

The code, every number's source and the negative results are on GitHub: https://github.com/vaibhav375/saanjh
