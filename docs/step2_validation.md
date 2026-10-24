# Step 2 validation

## Result summary

The standard-library checker produced 14 provisional flags on the supplied pack: 12 `exclude`, one `correct`, and one `keep`. It also produced 12 diagnostics that were intentionally not promoted. Synthetic tests, repeat runs, an alternate-current-directory run, input hashing, source-row boundary review, and threshold sensitivity checks were completed.

## Commands and actual results

```text
python -m py_compile checker.py quality_checker/config.py quality_checker/core.py tests/test_checker.py
python -m unittest discover -s tests -v
python checker.py "ridgeline_data_pack (2)"
python checker.py "<absolute-pack-path>"                 # run from tmp/alternate-cwd
PowerShell Get-FileHash checks before/after and across repeat/alternate runs
PowerShell/Python source-row and reconstructed-time boundary reviews
Sensitivity runs using dataclasses.replace(DEFAULT_THRESHOLDS, ...)
```

Synthetic suite result: **11 tests run, all passed**. Tests cover replay versus conflict, gaps, both clock-offset signs, UTC date rollover, correction sign and row preservation, invalid checksums, void and missing GPS, coordinate hemispheres, temperature flatline, normal zero rain/night GHI, RH >100 versus genuine 100% saturation, shared regional pressure/wind changes, persistent local pressure/wind changes, daylight-only temperature shift, rain blockage/release, renamed/reordered stations, shifted dates, insufficient peers, exact output schema, header-only clean output, determinism, input preservation, and current-working-directory output.

Supplied-pack repeat/alternate results:

| Check | Result |
|---|---|
| `flags.csv` count | 14 |
| `diagnostics.csv` count | 12 |
| `flags.csv` SHA-256, repeat and alternate CWD | `807D8B079C106A43BA126DA64EF5C138BCBF424C91708B54776606048F467295` for every final run |
| Diagnostics SHA-256, repeat and alternate CWD | `CFF88DF421AD365C4A22F71A3568DDC7C1EEE7D000D9802DDABC788F1A677ECE` for every final run |
| Supplied input files hashed | 19 |
| Supplied input hash changes | 0 |

## Supplied-pack flags reviewed against source evidence

Intervals are inclusive reconstructed UTC. Confidence describes the existence/scope of the issue, not a speculative hardware cause.

| Station | Channel | Period | Action | Evidence | Confidence |
|---|---|---|---|---|---|
| S01 | `pressure_hpa` | 2025-03-01 00:00 to 2025-04-11 23:50 | keep | Median 709.4 hPa is consistent with 2,913 m metadata elevation and 2,913 m median trustworthy GPS altitude; it is station pressure. | High |
| S02 | `pressure_hpa` | 2025-03-21 17:20 to 2025-04-11 23:50 | exclude | Rows 2,985-2,986 jump 836.0 to 842.5 hPa; 72-hour station-minus-peer residual changes +6.7 hPa across 432 observations per side; same-date uncalibrated board-swap note corroborates but does not set UTC. | High |
| S03 | `temp_c` | 2025-03-05 14:20 | exclude | Row 664 is -40.0 C between -3.5 and -3.1 C, then immediately returns. | Very high |
| S03 | `temp_c` | 2025-03-12 03:40 | exclude | Row 1,608 is 85.0 C between 7.3 and 6.0 C, then immediately returns. | Very high |
| S03 | `temp_c` | 2025-03-18 06:00 to 2025-03-21 14:00 | exclude | Exactly 6.5 C for 481 consecutive rows (2,486-2,966; 80.2 hours) while other channels vary. | Very high |
| S03 | `temp_c` | 2025-04-02 22:10 | exclude | Row 4,743 is -40.0 C between 8.6 and 8.6 C, then immediately returns. | Very high |
| S03 | `temp_c` | 2025-04-08 09:50 | exclude | Row 5,533 is 85.0 C between 0.7 and 0.7 C, then immediately returns. | Very high |
| S04 | `rain_mm` | 2025-03-23 06:00 to 2025-04-02 16:30 | exclude | 1,501 zero rows while at least two peers are wet in 161 intervals, followed by station-only 11.0/11.2/11.2 mm; funnel-cleaning note corroborates, but water is not redistributed. | High |
| S05 | `metadata` | 2025-03-01 00:00 to 2025-04-11 23:50 | exclude | 1,146 trustworthy GPS positions have median separation 20.45 km from metadata; the checker does not decide which source is wrong. | Very high disagreement; low cause |
| S05 | `rh_pct` | 2025-03-07 12:10 to 2025-03-11 00:00 | exclude | 451 of 504 readings are 101-105%, with an abrupt 104% to 7% exit; intervening 100% values remain in the dense unreliable episode rather than being independently called faulty. | High |
| S06 | `all` | 2025-03-24 16:10 to 2025-04-11 23:50 | correct | Add six hours to source rows 3,411-6,049: 438 valid RMC offsets are -21,600 s and the original weather step exactly matches the predicted reset discontinuity. | Very high |
| S07 | `wind_kmh` | 2025-03-26 18:00 to 2025-04-11 23:50 | exclude | Station/peer non-calm relationship changes by factor 0.44 across 416/429 observations; different-brand anemometer note corroborates; six-hour scan boundary is approximate and no multiplier is inferred. | High change; medium boundary |
| S08 | `all` | 2025-03-16 14:00 to 2025-03-18 01:30 | exclude | 214 nominal observations are absent between source rows 2,245-2,246; no interpolation. | Very high |
| S08 | `all` | 2025-04-05 00:00 to 2025-04-05 23:50 | exclude | Exclude only replay source rows 5,836-5,979; retain identical originals at rows 4,828-4,971. | Very high |

## S06 and S08 reconciliation

S06 retains all 6,048 rows and source rows 2-6,049. Before correction, row 3,410 is 2025-03-24 16:00 and row 3,411 jumps to 10:10. GPS has a 567-observation 0-second segment through GPS row 664, then a 438-observation -21,600-second segment beginning at GPS row 665 (logger 11:00, GPS 17:00). Applying +21,600 seconds from weather row 3,411 maps rows 3,408-3,414 as follows:

```text
source  raw logger time       interpreted UTC      correction
3408    2025-03-24 15:40     2025-03-24 15:40     0
3409    2025-03-24 15:50     2025-03-24 15:50     0
3410    2025-03-24 16:00     2025-03-24 16:00     0
3411    2025-03-24 10:10     2025-03-24 16:10     +21600
3412    2025-03-24 10:20     2025-03-24 16:20     +21600
3413    2025-03-24 10:30     2025-03-24 16:30     +21600
3414    2025-03-24 10:40     2025-03-24 16:40     +21600
```

The corrected view is strictly increasing and contains 6,048 unique interpreted timestamps; no reading is dropped. This demonstrates both correction sign and row scope. The offset is observed in GPS messages; the first affected weather row is independently established by the matching row-order discontinuity.

S08 reconciliation is exact: 5,978 raw rows minus 144 later exact replay occurrences equals 5,834 unique observations; adding the 214 absent nominal intervals gives 6,048 expected slots over the pack coverage. The replay flag targets only later source rows, not both copies or the whole calendar day.

## Diagnostics not promoted

- All stations contain some ignored checksum-invalid or void-position GPS messages (55 checksum failures and 160 void RMC statuses in total). Validity is message-specific; these do not invalidate weather data.
- S01 pressure/wind peer checks lack enough elevation/geography-eligible references. Its low pressure has independent elevation/GPS support and is an explicit `keep`, not an unresolved keep.
- S03 has a 626-row zero-rain run with 15 regionally wet intervals, and S08 a 1,038-row run with 14. Neither has a station-only release or service evidence, so local dry weather versus under-catch is unresolved.
- S07's wind change is strong, but the exact instant is limited by six-hour candidate scanning and a date-only, timezone-free maintenance note.

## Sensitivity check

| Variation | Result versus default |
|---|---|
| Pressure residual threshold 3 to 2 hPa | No flag changes. |
| Pressure residual threshold 3 to 5 hPa | No flag changes; S02 remains because observed shift is +6.7 hPa. |
| Rain regional-wet minimum 12 to 30 intervals | No flag changes; S04 has 161 corroborating intervals. |
| Wind factor threshold 2.0 to 2.5 | S07 wind flag disappears; observed factor magnitude is about 2.27, so this is the main material sensitivity. The default factor-of-two rule is retained and disclosed. |
| Daylight temperature threshold 4 to 3 C | Adds a borderline S06 flag (+3.0 C daylight, 0.0 C night) without maintenance or other independent evidence. The conservative 4 C default rejects it. |

Temperature persistence (80.2 hours versus a 6-hour minimum), isolated spikes (36-84 C deviations versus a 20 C minimum), location mismatch (20.45 km versus 5 km), and S06 clock offset (360 minutes versus a 5-minute minimum) are not near their thresholds.

## Corrections considered and rejected

- **Accepted:** S06 +6-hour timestamp correction only, because repeated RMC evidence establishes magnitude/sign and source order establishes the exact weather boundary.
- **Rejected:** infer S02 pressure calibration from peers; meteorology and non-certified peers prevent an exact correction.
- **Rejected:** clamp or subtract an offset from S05 RH; the failure mode is unknown.
- **Rejected:** move S05 metadata to GPS coordinates; the checker cannot determine which identity/location source is wrong.
- **Rejected:** redistribute S04's released rain into earlier intervals; timing and retained water are unknown.
- **Rejected:** multiply S07 wind by the inverse peer factor; terrain and anemometer transfer functions are unknown.
- **Rejected:** replace S03 spikes/flatline by interpolation; the requested deliverable is flags, not fabricated measurements.
- **Rejected:** interpolate S08's outage or delete both copies of the repeated day; only later exact replay rows are excluded.

## Remaining risks before report writing

- Peer selection uses distance/elevation, not topographic barriers or calibrated references.
- Pressure/wind/daylight detectors do not automatically prove a later recovery; current flags extend to coverage end unless a separately supported boundary is implemented.
- S07 boundary precision and action should be described carefully in the coordinator report.
- S05 metadata disagreement affects location-dependent interpretation; a physical/serial-number check is still needed.
- `flags.csv` is provisional until the candidate reviews action wording and evidence in their own judgement. This validation does not make the assignment submission-ready.
