# Saanjh — 3-minute demo video

No live demo is allowed; the video is the product. One idea per beat, every number on screen is measured
(source in `results/NOTES.md`). Record screen at 1920×1080; voice-over recorded separately.

| Time | On screen | Voice-over |
| --- | --- | --- |
| 0:00–0:15 | Black. A clock face: a satellite icon passes at 1:30 pm. Then a field burning at dusk (stock clip or still). | "Every farm fire in India's official count is seen by satellites that pass over Punjab around 1:30 in the afternoon. Farmers now light them at 4 or 5." |
| 0:15–0:40 | `figures/evening_fires_2024-11-18.png`, the three panels revealed left to right. | "This is one day, 18 November 2024, seen by GK-2A, a Korean weather satellite whose images NOAA hosts on AWS. At the 1:40 pm pass: two strong hotspots. Three hours later: seventy-eight." |
| 0:40–1:05 | `figures/season_2025.png` (bars fill in orange). Caption: *86.8% (2024) · 91.7% (2025)*. | "Saanjh reads every 10-minute image of two whole seasons. Ninety-two percent of the fire energy it sees in 2025 came from fires that started after the official satellites had left. We tuned on 2024 and tested on 2025." |
| 1:05–1:30 | Live page, "Play the night": smoke drifts from Fazilka to Sirsa to Delhi; the night strip's playhead moves through the dark band. Caption: *same fire, 5 pm vs 1 pm: 2.8× the smoke people breathe*. | "Evening fires are also worse. After sunset the air layer that dilutes smoke shrinks from a kilometre to a few dozen metres. The same fire lit at 5 instead of 1 puts 2.8 times as much smoke into people's lungs — on every one of 47 days." |
| 1:30–1:55 | "Send teams before dusk" tab on `?day=2025-11-10`: drag the teams slider 8 → 20; the blocks move; the white dots (fires that actually burned that evening) fall inside them. Caption: *20 teams: 75% of the evening's smoke harm vs 31% chasing yesterday's counted fires*. | "So Saanjh plans ahead. At 11:30, before anyone strikes a match, it predicts where tonight's fires will be and where their smoke would hurt most, and places the district's field teams. On the 2025 season, which the model never saw, the same 20 teams reach two and a half times more of the evening's smoke." |
| 1:55–2:15 | Officer tab: click fire #1 — its 10-minute fire-power curve starts after the "satellite pass" line; click "Ask Saanjh why", the answer appears. Then Residents tab → Delhi on `?day=2024-11-18`: origin bar *Punjab 84% · Haryana 16%*, the Hindi/Punjabi notice, "5 of 9 weather scenarios". | "Officers see each fire's story and can ask why it ranks where it does. Residents see when the smoke arrives, how sure we are, and whose smoke it is — in their language." |
| 2:15–2:35 | Scroll to "How we know it works": the six evidence cards, ending on the negative-result card. | "Every claim is measured on a season the model never saw — including the one where Saanjh doesn't beat a simple forecast. We show that too." |
| 2:35–3:00 | Architecture diagram (README). Highlight in turn: NOAA S3 → SNS → SQS → Lambda; Step Functions replay; Strands + Bedrock. | "It runs where the data lives: NOAA's own notification triggers a Lambda for every new image; Step Functions replays whole seasons in minutes; a Strands agent on Bedrock explains the ranking. Saanjh: seeing the fires after dusk, before the smoke arrives." |

Recording notes
- Use `?day=2024-11-18` on the live URL for the replay shots; the live page shows tonight.
- Keep cursor movements slow; zoom (OS accessibility zoom) on the night strip and the "Missed" badges.
- Say "the official count" not a specific agency name.
- Ethics line, if time allows in the 1:30 beat: "It works on a 2–4 km grid and never identifies farmers."
