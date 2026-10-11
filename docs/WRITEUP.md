# Saanjh — submission writeup

**Track:** 01 Air · **Team:** AtoZ (solo) · **Repo:** https://github.com/vaibhav375/saanjh · **Live:** see README

## The problem
India's official farm-fire count comes from polar-orbiting satellites that pass over Punjab and Haryana around
13:30. Farmers have shifted burning to 16:00–17:00, after the pass (NASA, Jethva 2026; iFOREST 2025). The count —
and every air-quality forecast built on it — no longer sees most of the fires, and evening smoke is trapped in a
shallow night-time layer over the towns where people sleep and children gather for 8 am assembly.

In November 2024 the Supreme Court directed the Centre and CAQM to get farm-fire data from geostationary satellites
instead of relying on the polar orbiters, and to involve ISRO in all-day monitoring. Saanjh is a working,
open version of that monitoring, built on a geostationary satellite whose data is free on AWS.

## What we built
Saanjh reads every 10-minute image from the Korean geostationary satellite GK-2A, detects the fires, follows
their smoke with forecast winds and boundary-layer height, and turns that into (1) a ranked list of tonight's fires
by the people who will breathe their smoke, for district officers, and (2) smoke-arrival notices for each town in
English, Hindi and Punjabi. An assistant explains any ranking. At noon, before the fires are lit, a fire-risk
model places field teams where tonight's smoke would reach the most people. A Districts view sets each district's
official count against the fire energy GK-2A saw, and officers can download a one-page PDF briefing for tonight.

Measured (details and caveats in `results/NOTES.md`):
- 86.8% (2024) and 91.7% (2025, held out) of detected fire energy came from fires that started after the overpass.
  Because GK-2A misses most fires under ~10 MW at every hour, the missed energy (~670 TJ, ~1,540 t of PM2.5 in 2025)
  is a floor, not an estimate of the total.
- A second satellite confirms the evening fires: evening fires GK-2A saw for 30 minutes or more (61% of the missed
  energy) show up in the ~01:30 VIIRS night pass 3.0× as often as the same places on other nights (95% CI 1.8–4.7),
  and fires seen for an hour 3.4×. Dropping the single-image detections this test can't confirm, the headline is
  still 89.5% (2025) and 83.0% (2024).
- The same fire lit at 17:00 instead of 13:00 causes 2.8× the population smoke exposure (worse on all 47 days).
- Adding the missed fires to today's inventory improves day-to-day tracking of measured PM2.5 near the fires
  (correlation 0.23 → 0.28, 95% CI +0.02 to +0.10, 33 CPCB stations, 2025).
- GK-2A's limits, measured: ~3% of fires under 5 MW and ~43% of 40–80 MW fires are detected.
- A negative result we report: night-before smoke warnings do not beat "tomorrow will be like today".

## What we have checked, and what we haven't
Checked against independent data:
- Detector tuned on 2024 only, frozen, then tested on 2025: 70% of its 13:30 detections match a VIIRS fire.
- Evening fires lasting 30 minutes or more are confirmed by the VIIRS night pass well above chance (above).
- Adding them makes modelled smoke track measured PM2.5 better at CPCB stations near the fires (2025).
- The noon fire-risk model: ROC AUC 0.90 on the 2025 season it never saw.

Not checked, or weak:
- Single-image detections (22% of evening energy) are not confirmed by anything; the headline holds without them.
- Fires under ~10 MW are mostly invisible to GK-2A, which is ~66° off vertical over Punjab (~4 km pixels).
- Hourly smoke timing has little skill; notices say which nights and towns, not exact hours.
- Night-before warnings do not beat persistence (a negative result we report).
- The pollution tests use 2025 only: OpenAQ has no CPCB station data for 2023–24.
- No field trial: no officer, school or agency has used Saanjh yet.

## Where AWS fits
- **Data on AWS:** GK-2A (NOAA Open Data, `noaa-gk2a-pds`) and the OpenAQ archive, both in us-east-1.
- **Event-driven detection:** NOAA's `NewGK2AObject` SNS topic → SQS → Lambda reads one 4 MB chunk per image by
  HTTP range request, next to the bucket.
- **Season replays:** Step Functions Map runs the same Lambdas over the archive — 47 days of 10-minute images in
  ~25 minutes (a day of downloads from a laptop in India).
- **Hourly model and alerts:** EventBridge Scheduler → Lambda → S3 → SNS email alerts.
- **Public page and open API:** Lambda Function URL (HTTPS), with an OpenAPI 3.1 spec and docs at `/api`; the
  district briefing PDF is generated on demand in Lambda.
- **Operations:** CloudWatch embedded metrics (images, detections, latency), alarms on errors, pipeline lag, queue
  backlog and failed images (dead-letter queue), an ops dashboard, and a live status endpoint the page reads.
- **Noon plan:** EventBridge Scheduler → Lambda runs the fire-risk model and team planner daily at 11:30 IST.
- **Assistant:** Strands Agents SDK with open-weight Qwen3 on Amazon Bedrock (Mantle endpoint), read-only tools.
- **Infrastructure as code:** AWS SAM, linted and tested by GitHub Actions on every push. AWS open-source tools
  used: AWS SAM CLI, Strands Agents SDK.

## AI tools used
Claude Code (Anthropic) was used as a coding and research assistant throughout: literature and data-source research,
code, the SAM template, analysis scripts and drafting documentation. All results were produced by running the code
in this repository on public data.
