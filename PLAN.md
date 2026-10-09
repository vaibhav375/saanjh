# Saanjh: plan of record

Environmental Hacks (AWS × WeMakeDevs), Oct 8–11 2026 · Track 01 Air · solo (team AtoZ)
Revised Fri 9 Oct, 17:15 IST, after a day-one check of the original plan against primary sources and real data.

## Decision

**Track 01 (Air), project Saanjh. Kept after research, with the pitch and the science corrected.**

Saanjh watches every 10-minute geostationary scan of Punjab and Haryana. It catches the crop fires lit after
the official satellites have passed, turns their burning energy into smoke that it follows through the
night-time air, and tells district officers which fires matter tonight and tells schools when the smoke will arrive.

Why Air beats the other two tracks (unchanged from the first plan, re-checked):

| Track | Best non-obvious idea | Verdict |
| --- | --- | --- |
| **Air** | Saanjh: catch evening farm fires from a geostationary satellite, model their night-time smoke, warn before it lands | **Pick.** The season is live during the event, the failure in official data is documented, all data is free and on AWS, and the result can be measured. |
| Heat & Water | GNN leak localisation on BattLeDIM L-Town | Strong ML, but European 24×7 network vs India's intermittent supply; no visible user for the video. |
| Heat & Water | Wet-bulb shift planner for outdoor workers | Real gap, but heat season is over and the physics is one known formula. |
| Waste & Energy | Rooftop-solar soiling: when cleaning pays | Clever, but little public Indian inverter data to prove it in 3 days. |
| Waste & Energy | Landfill fire/methane watch from Sentinel | Single user (municipality), no action loop to demo. |

## What day-one research changed

| Original plan said | What the sources/data show | Change |
| --- | --- | --- |
| "No other team will think to look at a Korean weather satellite." | NASA's Hiren Jethva published exactly this in May 2026: GK-2A fire detection over NW India, hourly, 12–18 IST, 2019–2025 ([Remote Sens. 18:1506](https://doi.org/10.3390/rs18101506)). His stated implication: forecasts that assimilate only MODIS/VIIRS fires underestimate emissions. | **Pitch:** "NASA showed the fires moved to dusk and that forecasts are blind to them. Saanjh is the missing operational system." Cite it; never claim the detection idea is ours. |
| Detector finds the fires VIIRS sees. | Over Punjab GK-2A looks at ~66° from vertical; pixels are ~4 km (Jethva). A 5 MW paddy fire warms a 4 km pixel by <1 K at 3.8 µm. On 18 Nov 2024 the mean VIIRS fire was 4.8 MW. Jethva reports false-alarm rate only, never recall. | Measure and publish **probability of detection vs fire power** (our first research result). Report fire *energy* captured, not counts. |
| Ground truth from Sentinel-2 burn scars. | FIRMS public yearly CSVs give 2024 VIIRS with no key; 2025 needs a free MAP_KEY. | **Tune on the 2024 season, test on 2025** (clean held-out season). Sentinel-2 scars are a spot-check only. |
| GK-2A L2 cloud mask. | Not on the AWS bucket (L1B only). | Own cloud tests: per-hour BT floors (Jethva Table 1) + cold-neighbour rejection. |
| Download scans locally. | From this laptop each Punjab crop takes ~17 s even with 10 parallel streams (one 1375² HDF5 chunk ≈ 4 MB). A season at 10-min cadence ≈ 2,400 scans × 2 bands ≈ 23 h. | **Process the archive where it lives:** Lambda in us-east-1 fanned out by a Step Functions Distributed Map. AWS becomes load-bearing, not decoration. |
| LocalStack counts as an AWS open-source tool. | It is not an AWS project. | Use AWS SAM CLI (IaC) and the Strands Agents SDK (both AWS open source), plus deploy on AWS. |
| CPCB PM2.5 via OpenAQ API key. | OpenAQ's full hourly archive is a public S3 bucket (`openaq-data-archive`), no key. | Validation data costs nothing and lives in us-east-1 too. |
| Submission = video + blog. | Rules: **public repo + YouTube video ≤3 min + short writeup that lists the AI tools used**; repo history must fall inside the event dates; deadline is strict. | Repo created Oct 9; commit often; writeup lists Claude Code. |

## Day-one evidence (already reproduced)

`figures/evening_fires_2024-11-18.png`: on 18 Nov 2024, GK-2A shows **2 strong hotspots** (3.8 µm >6 K above
the 7×7 neighbourhood, ~12× the 0.52 K noise) at the 13:40 IST VIIRS overpass, and **70–78** at 16:00–16:30 IST,
clustered in Ferozepur–Muktsar–Fazilka where VIIRS saw the day's densest small fires. Once 1-based CGMS indexing was
fixed, the contextual 3.8 µm anomaly ranks VIIRS fire pixels with AUC 0.80 (≥20 MW) and 0.88 (≥40 MW).
The signal grows with fire power, as the physics says it should.

## The five numbers the project will report

The judges' test is "one number that moves". Saanjh reports five, each from a named dataset and method.

| # | Number | Data | Method |
| --- | --- | --- | --- |
| N1 | **Share of fire energy released after the VIIRS overpass**, Punjab+Haryana, 2024 and 2025 seasons | GK-2A 10-min, Oct 15–Nov 30 | Integrate FRP over time per fire (MIR radiance method, Wooster 2003); split at 13:30 IST |
| N2 | **GK-2A detection limit**: probability of detection vs per-pixel FRP | VIIRS SNPP + NOAA-20 at overpass | Collocate on the AMI grid, logistic fit of POD(FRP); tune 2024, test 2025 |
| N3 | **Dusk penalty**: how many times more person-hours of smoke the same fire causes when lit at 17:00 vs 13:00 | Open-Meteo/ERA5 winds + boundary-layer height, WorldPop | Same emission released at both times through the particle model, every day of the season |
| N4 | **Explained PM2.5**: R² gain at downwind CPCB stations when evening fires are added to the overpass-only inventory | OpenAQ archive, ~10 stations | Linear model fit Oct, tested Nov; overpass-only vs Saanjh emissions (the ablation) |
| N5 | **Warning lead time**: median hours between a Saanjh smoke alert and the PM2.5 spike, with hit/false-alarm rates | Replay of Nov 2025 | Hour-by-hour replay; spike = PM2.5 above 95th pct of the station's October |

N3 is new and cheap. Night-time boundary layers in November Punjab are a few hundred metres deep against
1–1.5 km at midday, so evening smoke has far less air to dilute into. If the model confirms a large multiplier,
that is the headline: *the farmers' shift to dusk didn't just hide the fires; it made each one worse.*
If it doesn't, we report that honestly.

## Method

1. **See (detector).** Per 10-min scan: dT = BT3.8 − BT11.2; contextual anomaly against the 7×7 median;
   per-pixel noise and bias from the same day's 09–11 IST scans (Jethva's normalisation); hour-dependent BT floors for
   cloud; reject pixels with cold neighbours (cloud edges, the false alarms seen in the Himalayan foothills on day one).
   Extended past 18 IST, where Jethva stops: with no reflected sunlight at 3.8 µm the background gets quieter.
2. **Count energy.** FRP per pixel by the MIR radiance method, integrated over a fire's lifetime → fire radiative energy →
   dry matter (0.368 kg/MJ, Wooster et al. 2005) → PM2.5 (crop residue emission factor, Akagi et al. 2011).
   Both constants to be checked against the papers before quoting.
3. **Follow the smoke.** Lagrangian particles per fire, RK2 advection on hourly winds (10 m / 925 hPa), random-walk
   spread, uniform mixing through the boundary layer. Concentration = particle mass / (cell area × BLH). Linear in
   emissions, so each fire's share of each town's smoke is exact within the model: Harm_f = Σ_t Σ_c C_f,c,t · Pop_c · Δt.
4. **Act.** Officer console: tonight's top 20 fires by Harm_f, with village, first-seen time, counted/uncounted, people
   exposed and towns hit. Smoke-arrival alerts: "Smoke from farm fires expected over Ludhiana from ~2 am; worst 6–9 am;
   hold assembly indoors", sent only above a threshold. Village/2 km grid only: never names farmers.

## AWS architecture

| Layer | Service | Notes |
| --- | --- | --- |
| Trigger | NOAA's SNS topic `NewGK2AObject` → SQS | Live path; one message per new file |
| Detect | Lambda (container: numpy, scipy, h5py), us-east-1 | Reads one HDF5 chunk per band by range request, same region as the bucket |
| Backfill | Step Functions Distributed Map over the archive | Same Lambda; a season in minutes instead of a day |
| Store | DynamoDB (fires, rankings), S3 (crops, smoke grids) | |
| Model | EventBridge Scheduler → Lambda (smoke model) hourly 12–23 IST | |
| Serve | S3 + CloudFront static site (MapLibre), API Gateway + Lambda | Public "smoke tonight" view; officer view |
| Explain | Bedrock model called through a Strands agent, tools `get_fire`, `get_trajectory`, `get_station_pm25` | Cut first if time runs short |
| Alert | Telegram bot (SMS to India needs DLT registration) or SNS email | |
| IaC | AWS SAM | AWS open-source tool for eligibility |

## Schedule (remaining)

| When | Work | Done means |
| --- | --- | --- |
| Fri 17:00–21:00 | Detector v1 (cloud-edge rejection, region mask, FRP); POD(FRP) on 5–10 days of 2024 from local cache | N2 curve for 2024 plotted |
| Fri 21:00–24:00 | SAM template: detector Lambda + Distributed Map backfill; run 2024 + 2025 seasons in us-east-1 | Season fire tables in S3 |
| Sat 08:00–13:00 | Smoke model, population grid, CPCB stations; N1, N3, N4 | Numbers frozen in `results/` |
| Sat 13:00–19:00 | Live path (SNS→SQS→Lambda), hourly model, alerts, N5 replay | A real 2026 scan flows end to end |
| Sat 19:00–24:00 | Console (map + ranked table), public page | URL works signed-out |
| Sun 08:00–12:00 | Agent (optional), README, writeup, blog draft | |
| Sun 12:00–16:00 | Record and upload the 3-min video; make repo public; submit | Submitted with margin before the page's deadline |

Fallback order if time slips: agent → live 2026 ingest (keep the replay) → console map (keep the ranked table).
Never drop the measured numbers.

## Video (3:00)

| Time | Shows | Says |
| --- | --- | --- |
| 0:00–0:20 | Satellite pass clock; field burning at dusk | Official fire count comes from satellites that pass by 1:30 pm; farmers now burn at 4–5. |
| 0:20–0:50 | Day-one figure as an animation, 13:40 → 16:30 | Same day, same fields: 2 fires at the overpass, 78 three hours later. |
| 0:50–1:20 | Season curve (N1) and detection limit (N2) | X% of the season's fire energy is released after the satellites leave. |
| 1:20–1:50 | Smoke drifting overnight toward Ludhiana/Delhi; dusk-penalty bar (N3); ablation (N4) | Evening fires do N× more harm, and adding them explains more of the measured smoke. |
| 1:50–2:30 | Console top-20, "why #3?", phone alert the night before | Officers get fires ranked by people exposed; schools get warned hours ahead. |
| 2:30–3:00 | Architecture | NOAA's own S3 notification triggers Lambda on every scan; a season of archive reprocessed in minutes. |

## What I need from you

1. **AWS:** account with the $200 credits, CLI credentials on this Mac (`aws configure` or SSO), region us-east-1.
   Install `awscli` and `aws-sam-cli` (Homebrew), plus Docker Desktop for the container Lambda.
2. **FIRMS MAP_KEY** (free, emailed instantly): https://firms.modaps.eosdis.nasa.gov/api/map_key/. Unlocks the 2025 test season and live VIIRS.
3. **Bedrock model access** in us-east-1 (only for the agent).
4. **Telegram bot token** from @BotFather if you want phone alerts in the video.
5. **GitHub push:** your account blocks pushes that expose a private email. Either untick *Settings → Emails →
   Block command line pushes that expose my email*, or make pes1ug23cs665@pesu.pes.edu public. Then `git push -u origin main`.

## Sources

- Event page and rules: https://www.wemakedevs.org/aws/env, https://www.wemakedevs.org/aws/rules (read Oct 9, 2026)
- Jethva, H. (2026) Timing the Flames: Geostationary Satellite Detection of Diurnally Shifting Stubble Burning in Northwestern India. Remote Sensing 18:1506. https://doi.org/10.3390/rs18101506
- Singh et al. (2025) Active Fire Detection using Indian Geostationary Satellite INSAT-3DS. https://link.springer.com/article/10.1007/s41976-025-00233-4
- FIRMS geostationary (MSG-IODC, provisional) layer: https://firms.modaps.eosdis.nasa.gov/descriptions/FIRMS_GOES_EUMETSAT_MSG_IODC.html
- FIRMS area API sources (no geostationary): https://firms.modaps.eosdis.nasa.gov/api/area/
- iFOREST Stubble Burning Status Report 2025: https://iforest.global/wp-content/uploads/2025/12/StubbleBurning_StatusReport_2025_Website.pdf
- NASA Earth Observatory, New timing for stubble burning in India: https://science.nasa.gov/earth/earth-observatory/new-timing-for-stubble-burning-in-india
- GK-2A on AWS: https://registry.opendata.aws/noaa-gk2a-pds (bucket `noaa-gk2a-pds`, L1B FD, Feb 2023 → today)
- OpenAQ archive on AWS: `s3://openaq-data-archive/records/csv.gz/locationid=…/year=…/month=…/`
- satpy AMI L1B reader (calibration and wavelengths): https://github.com/pytroll/satpy/blob/main/satpy/readers/ami_l1b.py
- Wooster et al. (2003) MIR radiance method for FRP; Wooster et al. (2005) combustion coefficient; Akagi et al. (2011) emission factors (to verify before quoting)
