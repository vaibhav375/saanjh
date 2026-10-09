# Saanjh — submission writeup

**Track:** 01 Air · **Team:** AtoZ (solo) · **Repo:** https://github.com/vaibhav375/saanjh · **Live:** see README

## The problem
India's official farm-fire count comes from polar-orbiting satellites that pass over Punjab and Haryana around
13:30. Farmers have shifted burning to 16:00–17:00, after the pass (NASA, Jethva 2026; iFOREST 2025). The count —
and every air-quality forecast built on it — no longer sees most of the fires, and evening smoke is trapped in a
shallow night-time layer over the towns where people sleep and children gather for 8 am assembly.

## What we built
Saanjh reads every 10-minute image from the Korean geostationary satellite GK-2A, detects the fires, follows
their smoke with forecast winds and boundary-layer height, and turns that into (1) a ranked list of tonight's fires
by the people who will breathe their smoke, for district officers, and (2) smoke-arrival notices for each town in
English, Hindi and Punjabi. An assistant explains any ranking.

Measured (details and caveats in `results/NOTES.md`):
- 86.8% (2024) and 91.7% (2025, held out) of detected fire energy came from fires that started after the overpass.
- The same fire lit at 17:00 instead of 13:00 causes 2.8× the population smoke exposure (worse on all 47 days).
- Adding the missed fires to today's inventory improves day-to-day tracking of measured PM2.5 near the fires
  (correlation 0.23 → 0.28, 95% CI +0.02 to +0.10, 33 CPCB stations, 2025).
- GK-2A's limits, measured: ~3% of fires under 5 MW and ~43% of 40–80 MW fires are detected.
- A negative result we report: night-before smoke warnings do not beat "tomorrow will be like today".

## Where AWS fits
- **Data on AWS:** GK-2A (NOAA Open Data, `noaa-gk2a-pds`) and the OpenAQ archive, both in us-east-1.
- **Event-driven detection:** NOAA's `NewGK2AObject` SNS topic → SQS → Lambda reads one 4 MB chunk per image by
  HTTP range request, next to the bucket.
- **Season replays:** Step Functions Map runs the same Lambdas over the archive — 47 days of 10-minute images in
  ~25 minutes (a day of downloads from a laptop in India).
- **Hourly model and alerts:** EventBridge Scheduler → Lambda → S3 → SNS email alerts.
- **Public page:** Lambda Function URL (HTTPS).
- **Assistant:** Strands Agents SDK with Claude on Amazon Bedrock, read-only tools.
- **Infrastructure as code:** AWS SAM. AWS open-source tools used: AWS SAM CLI, Strands Agents SDK.

## AI tools used
Claude Code (Anthropic) was used as a coding and research assistant throughout: literature and data-source research,
code, the SAM template, analysis scripts and drafting documentation. All results were produced by running the code
in this repository on public data.
