# Saanjh — 3-minute demo video

One story, told in order: **the fires the count misses → proof they're real → the harm they do → what an officer
does about it → how it runs on AWS → what we haven't proven.** Every number on screen is measured (source in
`results/NOTES.md`). Record the screen at 1920×1080; record the voice-over separately.

Live URL: `https://vxm2hfcv2m5ncjsydmsnkon7n40azecu.lambda-url.us-east-1.on.aws/`. Add `?day=2025-11-10&notour`
for the replay shots (`notour` stops the first-visit tour from opening).

| Time | On screen | Voice-over |
| --- | --- | --- |
| 0:00–0:15 | Black. A clock: a satellite icon crosses at 1:30 pm. Cut to a field burning at dusk (stock clip or still). | "India counts its farm fires with satellites that pass over Punjab at 1:30 in the afternoon. Farmers now light them at 4 or 5. In 2024 the Supreme Court told the government to watch with geostationary satellites instead. Saanjh does that." |
| 0:15–0:35 | `figures/evening_fires_2024-11-18.png`, the three panels revealed left to right. | "This is one day seen by GK-2A, a Korean weather satellite that images Asia every ten minutes and whose data NOAA hosts on AWS. At the 1:40 pass: two strong fires. Three hours later: seventy-eight." |
| 0:35–0:55 | The page on `?day=2025-11-10`: hero number counts up to 91%. Then Evidence → first card, the bars fill in orange. Caption: *86.8% (2024) · 91.7% (2025, held out)*. | "Saanjh reads every image of two whole seasons. In 2025, ninety-two percent of the fire energy it saw came from fires that started after the official satellites had left. We tuned on 2024 and tested on 2025, a season the method never saw." |
| 0:55–1:10 | Evidence → "A second satellite confirms…" card. Hover the top row so its tooltip shows. Caption: *confirmed 3× as often as chance*. | "Are those fires real? A second satellite, VIIRS, passes again at 1:30 at night. Evening fires that burned for half an hour or more show up there three times as often as the same fields on other nights." |
| 1:10–1:35 | Close evidence. Fires tab → click fire #1: the map flies in, the fire-power curve starts after the "satellite pass" line. Then Smoke tab → press Play: smoke drifts from Fazilka toward Sirsa and Delhi. Caption: *same fire, 5 pm vs 1 pm: 2.8× the smoke people breathe*. | "Evening fires also do more harm. After sunset the layer of air that dilutes smoke collapses to a few dozen metres. The same fire lit at five instead of one puts 2.8 times as much smoke into people's lungs, on every one of 47 days." |
| 1:35–1:50 | Smoke tab → pick Moga: arrival time, peak, "chance above 25", the origin bar, then switch the notice to ਪੰਜਾਬੀ and हिन्दी. | "Each town sees when the smoke arrives, how sure the forecast is across nine weather scenarios, which fires sent it, and a notice in English, Hindi or Punjabi." |
| 1:50–2:10 | Teams tab: drag the teams slider from 8 to 20; the blocks move and the white dots (fires that actually burned that evening) fall inside them. Caption: *20 teams: 75% of the evening's smoke harm vs 31% chasing yesterday's counted fires*. | "Better still, prevent it. At 11:30, before anyone strikes a match, a model predicts where tonight's fires will be and whose air they'd reach, and places the field teams. On 2025, the same 20 teams cover 2.4 times more of the evening's smoke." |
| 2:10–2:25 | Districts tab: the choropleth; click Sangrur (count −69%, fire energy +15%); click "Download tonight's briefing (PDF)" and show the PDF for two seconds. | "District by district: Sangrur's official count fell 69 percent; the fire energy GK-2A saw rose 15. Every officer can download tonight's one-page briefing." |
| 2:25–2:45 | Click the System chip: images in 24 h, latency, alarms all OK. Evidence → scroll to the architecture diagram; let the animated flow run. Flash the `/api` docs page for one second. | "It runs where the data lives. NOAA's notification for each new image triggers a Lambda through a queue with a dead-letter queue; schedules run the smoke model hourly and the plan at noon; Step Functions replays whole seasons; CloudWatch alarms watch it all, and the data is an open API." |
| 2:45–3:00 | Evidence → "What we have checked, and what we haven't" card. End on the page with the sky-coloured timeline playing. | "We show what we haven't proven too: small fires, single-image detections, and no field trial yet. Saanjh: seeing the fires after dusk, before the smoke arrives." |

Recording notes
- Keep cursor movements slow; use OS zoom on the timeline, the "MISSED" badges and the tooltip in the 0:55 beat.
- Say "the official count", not an agency's name.
- If a beat runs long, cut the 1:35 town beat first; keep the night-satellite beat, it answers the judges' first question.
- Ethics line, if time allows in the 1:50 beat: "It works on a 2–4 km grid and never identifies farmers."
- The live System chip needs the stack running; record before `sam delete`.
