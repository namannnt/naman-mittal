# Report method and decisions

The coordinator-facing deliverable is `report.html` at the repository root. It answers which observations can support a qualified six-week summary and recommends one one-hour visit from the supplied March-April 2025 snapshot. It is a report recommendation, not the candidate's personal `DECISIONS.md`. No current/live station condition has been assumed.

## Sources and evidence checks

Sources read: assignment requirements; actual revised `flags.csv` and `diagnostics.csv`; `docs/checker_design.md`; the superseding `docs/step2b_review.md`; historical `docs/step2_validation.md`; and actual weather/GPS/metadata/maintenance inputs. The Step 2B review takes precedence over the older 14-flag validation description. Relevant checker code was inspected for timestamp reconstruction, source-row replay selection, channel masks, metadata treatment, and peer selection.

`analysis/build_report.py` reruns the unchanged checker into ignored `tmp/report-checker/` and requires its flag and diagnostic rows to match the reviewed root CSVs exactly. It then calculates coverage from provenance-bearing records, before building the report. A mismatch stops the build instead of quietly changing reviewed flags. Source hashes at build time:

```text
flags.csv        b4c3fc3817e553c369e63b1e1f382056370ef0d0055ef10bd36373aaa301ba56
diagnostics.csv  5574c1b8e4516ae2f578c7c3b26279669c9a1ea89e20c6d799e07ceba275e071
```

Directly checked supporting facts include S06's row 3,411 reset (+6 hours, raw 10:10 to 16:10 UTC), the source-specific S08 replay and distinct-time gap, S04's under-catch/release periods and resumed small rain readings, S05's location-only scope, and S07's sustained peer-relative wind change. No checker inconsistency requiring a Step 3 code change was found. Checker behavior and reviewed CSVs remain unchanged.

## Coverage definition

The common observation-label window is **2025-03-01 00:00 through 2025-04-11 23:50 UTC, inclusive**, after interpreting supported clock corrections. Timestamps label the end of a measurement interval. All eight metadata rows specify ten-minute logging and installation before this window.

For each station, expected slots are the common start plus integer multiples of its stated interval through the common end. Here:

```text
expected = (last UTC - first UTC) / 10 minutes + 1 = 6,048
```

The denominator is the common window, not a station's raw first/last row. Otherwise S08's appended old day and S06's clock reset would distort completeness. There are 48,384 expected station-times across the network. Raw row count is 48,314; remove 144 later replay occurrences to retain 48,170 genuine rows, corresponding to 214 missing station-times.

Processing rules:

1. Read weather records in source order and apply only the checker's supported timestamp reconstruction. S06 has 2,639 corrected rows; its 6,048 genuine observations all survive.
2. Identify complete raw-row signatures and retain the first occurrence only. This selects replay occurrences by identity, not every observation in the replay flag's calendar period. S08's original April 5 observations remain.
3. Build interpreted-UTC groups. Count distinct observed slots against the expected grid. Any off-grid timestamp stops this report calculation for review.
4. Apply `exclude` flags by matching station, actual channel or `all`, and inclusive UTC interval. Union sets of excluded observed slots, so overlapping exclusions count once. `coverage gap` identifies missing slots, rather than existing observations to subtract again. Replay copies have already been removed by source identity.
5. Never apply a `metadata` exclusion to weather channels. Never subtract a `keep` flag. A supported clock `correct` flag changes timestamp interpretation, not a measurement value or observation count.
6. Separate absent slots from excluded observed slots. A non-numeric/missing channel value in a present slot would be excluded for that channel; none occurs in this pack. Conflicting values, if present after clock reconstruction, are not allowed to become a single chosen reading.

Every station/channel partition satisfies:

```text
expected slots = missing slots + excluded observed slots + retained slots
retained slots = retained as observed + retained after supported correction
```

The derived assessment is written to ignored `tmp/report-data.json`. It contains all 56 station/channel combinations, their mechanical partition, unresolved diagnostics, metadata status and reporting policy. These count fields describe filtering/availability, not certified scientific reliability.

## Retained counts and explicit usability assessment

Counts below are mechanically retained observations **out of 6,048 expected slots per channel**. The separate policy table governs scientific use. No percentages are displayed in the coordinator report because they would conceal when the missing or suspect observations occur. If a retained percentage is used in the derived JSON, it is `100 × retained / expected`, rounded to one decimal; whole counts are exact. The displayed S04 1.8 C contrast is independently recalculated and rounded to one decimal, not hardcoded into the report.

| Station | Missing times | Replay copies removed | T | H | P | W | D | R | L |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| S01 | 0 | 0 | 6,048 | 6,048 | 6,048 | 6,048 | 6,048 | 6,048 | 6,048 |
| S02 | 0 | 0 | 6,048 | 6,048 | 2,984 | 6,048 | 6,048 | 6,048 | 6,048 |
| S03 | 0 | 0 | 5,563 | 6,048 | 6,048 | 6,048 | 6,048 | 6,048 | 6,048 |
| S04 | 0 | 0 | 6,048 | 6,048 | 6,048 | 6,048 | 6,048 | 5,391 | 6,048 |
| S05 | 0 | 0 | 6,048 | 5,544 | 6,048 | 6,048 | 6,048 | 6,048 | 6,048 |
| S06 | 0 | 0 | 6,048 | 6,048 | 6,048 | 6,048 | 6,048 | 6,048 | 6,048 |
| S07 | 0 | 0 | 6,048 | 6,048 | 6,048 | 3,694 | 6,048 | 6,048 | 6,048 |
| S08 | 214 | 144 | 5,834 | 5,834 | 5,834 | 5,834 | 5,834 | 5,834 | 5,834 |

Legend: T=`temp_c`, H=`rh_pct`, P=`pressure_hpa`, W=`wind_kmh`, D=`wind_dir_deg`, R=`rain_mm`, L=`ghi_wm2`.

| Station | Usable as observed / after correction | Excluded, missing, disputed or unresolved |
|---|---|---|
| S01 | All seven channels provisionally. Low station pressure is explicitly kept; elevation and GPS altitude support it. | Lack of close elevation-matched pressure/wind peers limits independent verification. Not an assumed clean reference. |
| S02 | T/H/W/D/R/L and earlier P provisionally. | Exclude 3,064 P readings from March 21 17:20 to end; no recovery established. T has an unresolved daylight peer warning; qualify extremes rather than claim certified maxima. |
| S03 | H/P/W/D/L, retained T and R provisionally. | Exclude 485 T readings (481-row stuck run plus four isolated spikes). R dry-spell discrepancy lacks proof of blockage; qualify rain claims and inspect before a strong total claim. |
| S04 | H/P/W/D/L and retained R provisionally; labelled night-only T summaries may be used provisionally. | Exclude 654 suspect R readings March 29 03:10-April 2 16:00 and three release readings April 2 16:10-16:30. Physical onset before corroborating peer rain is uncertain. Complete T timestamps coexist with an unresolved sunny deviation: hold daytime highs and unqualified full-period means as a reporting precaution. |
| S05 | Retained measurements can support a clearly labelled station time series; no blanket weather exclusion. | Exclude the 504-row H episode March 7 12:10-March 11 00:00. Location-only metadata dispute suspends mapping, spatial comparisons and location attribution, including geographically weighted network use. Which coordinate source is wrong is unknown. |
| S06 | All seven channels after +6-hour repair to rows 3,411-6,049 (header is row 1); 3,409 readings as observed and 2,639 after correction per channel. | No remaining mechanical gap/overlap. T daylight peer warning and sparse pressure peers still limit scientific confidence; qualify extremes. |
| S07 | T/H/P/D/R/L and earlier W provisionally. | Exclude 2,354 W readings from the estimated March 26 15:40 split to end. The end record still shows a shifted relationship; no calibrated multiplier exists. T daylight warning unresolved. |
| S08 | Available genuine observations in all channels, provisionally. | 214 absent times March 16 14:00-March 18 01:30. Remove only later 144 replay copies, not originals. T daylight and R dry-spell warnings unresolved; no complete six-week rain total. |

Mechanically there are 338,688 expected station/channel slots, 1,498 missing slots (214 × seven channels), 7,064 excluded observed slots, and 330,126 retained slots. This is bookkeeping, not a network reliability score or a claim that the retained observations form an unbiased climate sample.

## Summary-use policy

- Unflagged means provisionally usable under this review, not proven accurate. Label the source station, actual time coverage, exclusions and unresolved concerns when aggregating.
- Do not combine retained segments into an unqualified full-period climate mean. Missing/excluded periods can be seasonally or meteorologically unrepresentative. Report available-period results with coverage and interpretation limits; do not fill or scale them to the full six weeks.
- S04 has complete temperature timestamps but an unresolved measurement concern. For the whole supplied window, withhold unqualified full-period means and daytime maxima pending a shielding/reference check; labelled night-only descriptions remain provisional. This conservative metric-level reporting recommendation creates no new checker flag or measurement adjustment. A nighttime-only result is not a substitute for an all-day mean.
- Other T peer warnings in S02/S06/S07/S08 lack sufficient independent confirmation for new exclusions. Retain measurements provisionally but qualify daytime extremes and review the underlying evidence before strong comparison claims.
- Do not present S04 or S08 partial rain sums as complete six-week totals. S03's unexplained dry-period discrepancy also warrants qualification. Rain before the S04 confirmed discrepancy is not silently relabelled faulty just because the gauge may have blocked earlier.
- S05 weather values remain available, but a station label does not resolve geographic attribution. Do not use disputed coordinates for a map, spatial comparison or location-weighted network average until the identity/location check is complete.
- Do not compare absolute mountain and valley pressure as though both were sea-level pressure, invent wind/pressure/RH calibration, redistribute released rain, interpolate gaps, or infer long-term climate trends from six weeks.

## S04 temperature evidence and uncertainty

The report build recalculates the strong-sun and night contrasts from the actual observations, using corrected times, unique records, actual temperature exclusions and peers S02/S06/S03/S08/S07. S05 is excluded from spatial reference selection. The painting note date partitions an exploratory before/after comparison only; the note date itself is omitted. It is not treated as a causal timestamp or a UTC detection boundary.

Sunny GHI >=500 W/m2: S04-minus-peer median changes from -0.400 C (405 samples) to +1.425 C (884), a +1.825 C contrast. Night GHI <=10: +0.150 C (1,016) to 0.000 C (1,835), a -0.150 C contrast. Step 2B's cloudy comparison is +0.250 C with only 24/26 samples; wind strata show sunny changes of +1.7 to +2.1 C and individual peers +1.8 to +2.2 C. These support a radiation-related hypothesis, but painting causation, exact onset and correction remain unestablished. Real site heating, seasonal exposure, ventilation, terrain and imperfect peers are competing explanations. Detailed evidence and sensitivity are in `docs/step2b_review.md`; no solar-time calculation was performed for this report.

## Exactly one technician recommendation

**Recommend S07 (Riverbend Farm), conditional on a fresh contact confirming the issue persists before dispatch.** This is a recommendation from the March-April 2025 snapshot, not evidence of the network's condition today.

| Priority for the one specialist hour | End-of-record evidence and why |
|---|---|
| 1. S07 | Wind relationship remains shifted after the different-brand replacement; 2,354 observations excluded. A physical model/configuration/mounting check can establish compatibility and prevent more unusable data. It is feasible within one hour without inventing a calibration. |
| 2. S04, strongest runner-up | Temperature is central to the summary and its sunny deviation remains unresolved. A shielding/reference visit could help, but uncertain cause and weather-dependent comparison may require longer observation. Rain resumes small readings after cleaning, so the dramatic historical release does not itself justify first dispatch. |
| 3. S02 | Persistent pressure shift removes 3,064 readings, more than S07's wind loss. Traceable correction needs an appropriate pressure reference/calibration plan; first request board identity and calibration records remotely. If suitable equipment and an active pressure need dominate locally, this priority could change. |
| 4. S05 | Location disagreement affects spatial interpretation, but RH recovers. Request install-sheet/receiver identity, serials and site photos from the local volunteer before spending the specialist hour. A visit follows if remote reconciliation fails. |
| Other candidates | S03 has genuine historical spikes/stuck readings but no demonstrated end-of-record freeze. S06 has a supported time reconstruction and a configuration check can start remotely. S08's transmission resumes and replay/export work is primarily remote. S01's low pressure is supported by altitude. None beats S07 on this record for one hour of preventable ongoing loss. |

S07 first check: identify the replacement anemometer model/serial and compare its documented output with the logger's configured input and the old sensor documentation. The report's feasible sequence is 0-10 minutes labels/settings, 10-25 safe visual inspection/manual compatibility, 25-45 a short portable-reference comparison and documentation, 45-60 save evidence and define the repair/manufacturer-supported next step. Bring the manuals, settings access, camera and a borrowed/existing portable wind reference if available. If a reference or model documentation is unavailable, the useful outcome is an identified mismatch or a precise unresolved requirement, not a claimed calibration or arbitrary coefficient.

The report calls the S07 start "about 26 Mar". The 15:40 UTC L1 split is a statistical estimate; increasing the calm-wind floor moves it to 19:50. The reported smoothed relative factor 0.44 is not a transfer coefficient. Raising the change-factor threshold to 2.5 suppresses the flag; the independent replacement note and sustained relationship shift support review priority, but do not remove this sensitivity.

## Layout, rendering and validation

Design: one column, prominent two-decision recommendation, eight-station table with a channel legend, one-hour visit panel, runner-up comparison and concise limits. A graphic was omitted because the table and visit sequence communicate the decisions more directly. The HTML is self-contained: embedded CSS, system font stack, no scripts, external fonts, images, CDN or network asset. Semantic headings, table header scopes, legend and descriptive text support offline reading. Text labels and rules carry meaning in grayscale; colour is decorative.

Print settings: A4 portrait, CSS margins 11 mm top/bottom and 12 mm sides, 100% scale, browser headers/footers off. Table text is 9.3 pt; visit body 9 pt; footnotes 8.3-8.4 pt; footer 8 pt. Rows and the visit panel request no page splits. `analysis/render_report.cjs` uses a local headless Edge executable with the bundled Playwright package; these are validation tools only and are not report/checker runtime dependencies.

Commands actually executed (bundled Python/Node and Poppler executable paths were used):

```text
python analysis/build_report.py "ridgeline_data_pack (2)" --data-only
python analysis/build_report.py "ridgeline_data_pack (2)"
node analysis/render_report.cjs <bundled-playwright-module> <local-msedge-executable>
pdfinfo tmp/report-render/report-print.pdf
pdfinfo tmp/report-render/report-grayscale.pdf
pdftoppm -png -r 120 -singlefile tmp/report-render/report-print.pdf tmp/report-render/report-print
pdftoppm -png -r 120 -singlefile tmp/report-render/report-grayscale.pdf tmp/report-render/report-grayscale
```

The first sandboxed browser attempt failed to write its temporary profile; the authorized local headless-render rerun succeeded. The first visual proof was two pages because only the footer overflowed. Row spacing and redundant spacing were tightened, and a touching time label was fixed; readable table font size was retained. The revised colour and grayscale proofs were inspected visually: **one A4 page**, all station rows and the full visit panel visible, footer present, no clipped text or horizontal overflow. Final rendering of the exact committed HTML and preservation checks are recorded below.

| Final validation | Actual result |
|---|---|
| Colour print PDF | One page, A4 594.96 × 841.92 pt; rendered at 120 dpi and visually inspected. |
| Grayscale print PDF | One page, same A4 size; rendered at 120 dpi and visually inspected, with all information readable without colour. |
| Page text verification | 3,864 extracted characters; all eight station IDs, first check, runner-up, source-file instruction and displayed coverage counts present. |
| Text bounds | x=33.75-556.24 pt; y=42.13-807.94 pt inside the 594.96 × 841.92 pt page. |
| Print-width layout check | 703 px content viewport, 703 px document width, no elements overflowing horizontally; main height 1,036.23 px. |
| Offline load | Browser context explicitly offline; no external assets or attempted network requests. |
| Narrow-screen structural check | 390 px viewport and 390 px document width; no horizontal overflow. |
| Repeated report build | Byte-identical HTML; all figures recalculated from the reviewed inputs/flags. |
| Input preservation | All 19 supplied files still match Step 1 hashes; zero changes. |
| Checker preservation | No diff in `checker.py`, `quality_checker/`, `flags.csv` or `diagnostics.csv`. |
| HTML SHA-256 | `45d133a4d095d33e0c6849f1d2ee1a2f42fc11cc798a419d879c4648b8cfbcd1` (UTF-8 with portable LF line endings) |

Temporary PDFs, PNGs, browser QA JSON and the detailed derived assessment stay in ignored `tmp/` and are not committed. The report has no runtime dependency on Playwright, Edge or Python: it can be opened as a local HTML file and printed offline. The source script is intentionally specific to this reviewed snapshot and recommendation; the quality checker remains the general-purpose component. No new sensor flag or correction was introduced to simplify the report. Preserve the full AI conversation for later export to `ai_logs/`.
