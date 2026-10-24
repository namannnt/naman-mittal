# Initial exploratory audit

## Scope and method

This is a read-only Step 1 audit, not the final checker or final quality decision. `analysis/audit_pack.py` reads the extracted pack in original file order, retains source row numbers and raw timestamps, validates NMEA checksums, and emits a deterministic JSON summary. It does not sort, interpolate, clamp, correct, or write into the pack.

The supplied attachment was already extracted as `ridgeline_data_pack (2)/`; no ZIP archive was present. The folder contains the complete documented shape: 19 files (README, station metadata, maintenance log, eight weather CSVs, and eight GPS files). The raw folder and assignment PDF are ignored by Git. The audit found 48,314 weather rows and 9,346 GPS lines.

All eight weather files have the documented columns and parseable `YYYY-MM-DD HH:MM` timestamps. All channel fields are numeric and none are blank. The modal positive adjacent step is 600 seconds. Seven files contain 6,048 rows; S08 contains 5,978 because its original sequence includes both an outage and a later repeated block. These counts are observations, not hard-coded expectations.

Across the network, observed ranges are: temperature -40.0 to 85.0 degrees C, RH 2% to 105%, station pressure 683.5 to 869.8 hPa, wind 0.0 to 61.3 km/h, direction 0 to 360 degrees, interval rain 0.0 to 11.2 mm, and GHI 0 to 1,050 W/m2. Low S01 pressure is consistent with its 2,913 m elevation and is not compared as sea-level pressure. Zero rain, nighttime zero GHI, and isolated 100% RH are not treated as failures.

## Station-by-station findings

### S01 - no strong weather fault found

**Observed facts.** The 6,048 weather rows are continuous and ordered, with no missing/non-numeric values, timestamp collisions, or repeated rows. Four of 1,174 GPS sentences fail checksum and 14 RMC sentences have void (`V`) status; valid fixes put the station within 14 m of metadata, and valid RMC logger-minus-GPS offsets are 0-2 seconds. The 67-row zero-GHI run is overnight and the long zero-rain run is not evidence by itself.

**Assessment.** No strong exclude/correct case from this audit. Confidence: moderate. S01 is high and topographically unlike most peers, so neighbour differences are weak evidence. Further evidence: sensor specifications and a longer seasonal baseline.

### S02 - discrete pressure-board shift

**Observed facts.** Pressure jumps from 836.0 to 842.5 hPa between CSV rows 2,985-2,986 (2025-03-21 17:10-17:20 logger time); the next-largest adjacent pressure change is only 0.9 hPa. The maintenance log (row 8) says the pressure board was swapped around 11 am that date without calibration. As a contextual comparison, median S02-minus-S03 pressure changes from -10.10 hPa over 2025-03-18 through the pre-note window to -3.35 hPa after 2025-03-21 12:00 through 2025-03-24. GPS has 30 checksum failures and 18 void RMC statuses, but trustworthy fixes agree with metadata within 14 m and valid time offsets are 0-2 seconds.

**Suspected cause.** A replacement-board offset is strongly supported, but the note's timezone is unstated. A 17:20 UTC jump would be compatible with about 11:20 local daylight time; that is a hypothesis, not proof. The before/after difference does not establish an exact calibration correction because pressure changed meteorologically and S03 is not a certified reference. Confidence: high that a step exists; low on correction magnitude. Further evidence: old/new board calibration records or a co-located reference trace.

### S03 - temperature channel freeze and isolated extreme values

**Observed facts.** Temperature is exactly 6.5 degrees C for 481 consecutive rows, CSV rows 2,486-2,966 (2025-03-18 06:00 through 2025-03-21 14:00), while other channels continue changing. Four isolated temperature values are extreme relative to adjacent readings: -40.0 at rows 664 and 4,743, and 85.0 at rows 1,608 and 5,533. The 6.5 value occurs 497 times in total. Weather timestamps are otherwise complete and ordered. GPS has three checksum failures and 13 void RMC statuses; trustworthy position and time agree with metadata/logger.

**Suspected cause.** Temperature-sensor/logger sentinel values plus a stuck temperature channel. Confidence: high for those observations, high that the 481-row persistence is not natural, but the hardware failure mode is unverified. Other S03 channels should not be excluded merely because temperature failed. Further evidence: logger firmware/sentinel documentation and raw ADC or service logs.

### S04 - rain gauge blocked, then a large release/reading

**Observed facts.** Rain is exactly 0.0 for 1,501 rows, CSV rows 3,206-4,706 (2025-03-23 06:00 through 2025-04-02 16:00). During that same interval every other station records rain (28.0-44.6 mm total; 96-141 wet intervals, with S06 having 103 despite its clock issue). S04 then reports 11.0, 11.2, and 11.2 mm at 16:10, 16:20, and 16:30; all seven peers report 0.0 at those three timestamps. Maintenance row 12 says leaves and part of a bird nest were removed from the funnel "around 10" on 2025-04-02. GPS position/time evidence is sound apart from four checksum failures and 26 void RMC statuses.

**Suspected cause.** Blockage followed by water/debris release during cleaning is strongly plausible. The six-hour difference between "around 10" and the logger timestamps could match local daylight time, but the note has no timezone, so the exact alignment remains unproved. The three large intervals should not be redistributed without bucket/service evidence. Confidence: high that pre-cleaning rain capture is unreliable; medium on the mechanism and affected boundaries. Further evidence: volunteer timezone/actual visit time, bucket counts during cleaning, and a nearby gauge/radar series.

### S05 - impossible RH episode and GPS/metadata location disagreement

**Observed facts.** There are 451 RH values above 100%, spanning CSV row 939 (2025-03-07 12:10) through row 1,442 (2025-03-11 00:00); values vary from 101% to 105%, so this is not merely a constant 100% saturation run. RH then drops from 104% to 7% between rows 1,442-1,443. Maintenance row 5 records a complaint on 2025-03-10 that humidity had shown 100 all week. Separately, 1,146 checksum-valid/status-valid GPS positions have a median distance of 20.454 km from S05 metadata (maximum 20.462 km). Their median longitude matches S05 closely, while median latitude 39.75395 is near S04's metadata latitude rather than S05's 39.57000. Valid GPS time offsets remain 0-2 seconds.

**Suspected cause.** RH calibration/scaling or sensor failure is likely, but no exact offset or clamp is justified. The GPS mismatch could be wrong station metadata, receiver/configuration coordinates, or a pack-generation/cabling mix-up; valid checksums prove sentence integrity, not station identity. Confidence: high that RH >100 is invalid and the coordinate sources disagree; low on correction. Further evidence: inspect S05 placement and receiver, compare install sheet/serials, and perform a traceable humidity check.

### S06 - six-hour clock reset with conflicting timestamps

**Observed facts.** Original weather order goes backward from 2025-03-24 16:00 at row 3,410 to 10:10 at row 3,411 (minus 5 h 50 min). This creates 36 timestamps from 10:10 through 16:00 that each contain two different readings; they were retained, not deduplicated. GPS RMC evidence changes from a repeated 0-minute logger offset through source row 664 to a repeated -360-minute offset from row 665 onward: at GPS row 665 the logger says 11:00:01 while checksum-valid RMC says 17:00:00 on the same UTC date. The maintenance log (row 9) reports a flat battery, replacement, and logger reboot that day. Trustworthy GPS positions agree with metadata within 13 m.

**Suspected cause.** Reboot reset the logger to a local-time-like clock six hours behind UTC. The repeated RMC date/time evidence makes a +6-hour correction candidate strong, including across UTC date rollover, but implementation must preserve the 36 conflicting original timestamps and define boundaries from evidence rather than overwrite rows. Confidence: very high on the offset and transition. Further evidence: logger timezone/configuration and reboot time; confirm whether all post-transition weather and GPS logger stamps share the same clock.

### S07 - wind scale changes after anemometer replacement

**Observed facts.** Maintenance row 10 says cracked cups were replaced on 2025-03-26 with a different-brand anemometer. Three-day median wind is 10.5 km/h before the note date and 1.9 km/h after it (note date excluded). Against same-elevation S03, the median S07/S03 wind-speed ratio changes from 1.14 over 2025-03-23 to 25 to 0.24 over 2025-03-27 to 29 (432 eligible matched observations in each window, excluding S03 values <=0.5). Other S07 channels remain variable. GPS position/time evidence is sound apart from two checksum failures and 24 void RMC statuses.

**Suspected cause.** Different pulse calibration or incompatible anemometer scaling is plausible. Terrain and real wind differences prevent treating S03 as truth, and the before/after shift does not license a guessed multiplier. Confidence: high that S07's relationship to peers changed; medium-high that the replacement caused it. Further evidence: both anemometer transfer functions, logger pulse setting, and a temporary co-located reference.

### S08 - outage/gap and appended duplicate day

**Observed facts.** Original order jumps from CSV row 2,245 at 2025-03-16 13:50 to row 2,246 at 2025-03-18 01:40: 214 nominal 10-minute intervals are absent. Maintenance row 7 says the website stopped updating since the previous morning and service returned on 2025-03-17 after a SIM top-up. Later, after row 5,835 reaches 2025-04-11 23:50, row 5,836 jumps backward to 2025-04-05 00:00 and appends 144 exact repeated rows covering that full day; maintenance row 13 notes on 2025-04-05 that the website showed the same day twice. No conflicting readings share those repeated timestamps. GPS has eight checksum failures and 22 void RMC statuses; trustworthy fixes agree with metadata and valid time offsets are 0-2 seconds.

**Suspected cause.** Communications loss explains the gap, and an export/website append fault explains the repeated day. Confidence: high. The duplicate copy may be safely suppressible for analysis only after the checker records the evidence; the outage cannot be reconstructed by interpolation. Further evidence: server ingestion/export logs and confirmation whether station-local storage exists.

## GPS evidence in aggregate

- Every station contains at least one checksum-invalid sentence: 55 total. Across all stations, 160 RMC records have void status. These records are explicitly treated as untrustworthy GPS evidence, not as proof that contemporaneous weather is bad.
- All GGA records parsed by the audit report fix quality 1. Trustworthy positions agree with station metadata to within about 15 m for seven stations; S05 is the clear 20.45 km exception.
- Trustworthy RMC date/time comparisons are repeatedly within 0-2 seconds for seven stations. S06 alone changes to a stable -21,600-second logger-minus-GPS offset. Full RMC dates are used, so offsets crossing UTC midnight are not reduced modulo 24 hours.

## Peer-comparison usefulness and limits

Peer comparisons use only parseable timestamps, exclude any timestamp with conflicting readings, collapse identical repeated timestamps to one observation, and use circular distance for wind direction. Eligible counts are 6,048 per station except S06 (5,976 after excluding 36 conflicted timestamps) and S08 (5,834 after the gap/repeated-day handling).

There is useful contextual overlap: S02-S03 are 17.2 km apart with 100 m elevation difference; S05-S06 are 18.7 km apart but differ by 247 m; S03-S07 differ by only 2 m in elevation but are 48.1 km apart. Global median absolute temperature differences for these pairs are about 1.1, 4.0, and 1.1 degrees C respectively. These comparisons can corroborate steps, outages, and gross scale changes, but terrain, distance, storm cells, and elevation can produce real differences. No station is assumed clean.

## Facts established versus hypotheses

**Established by direct parsing:** the schema/units and 10-minute modal interval; row/file counts; no blank/non-numeric weather values; S03 persistence/extremes; S04 zero-rain interval and subsequent three large readings; S05 RH >100 and GPS/metadata coordinate mismatch; S06 backward clock transition, 36 conflicting timestamps, and repeated -6-hour GPS offset; S07 pre/post wind relationship change; S08 gap and exact repeated day; per-sentence checksum/status/fix outcomes.

**Still hypotheses:** exact sensor failure modes; the timezone of every maintenance note; exact fault start/end when notes give only a date or approximate time; any numeric calibration for S02 pressure, S05 humidity, or S07 wind; redistribution/correction of S04 rain; whether S05 metadata or GPS identity is wrong; whether every peer difference is instrumental rather than real weather.

## Evidence needed before exclude/correct/keep decisions

1. Logger manuals and sentinel conventions for S03; board/anemometer calibration sheets for S02/S07.
2. S05 install sheet, receiver/logger serial mapping, physical inspection, and a traceable RH comparison.
3. S04 service time/timezone and any bucket counts or nearby independent rainfall trace.
4. S06 timezone/configuration and reboot logs, followed by tests for collision-safe timestamp correction.
5. S08 ingestion/export logs; do not interpolate the outage.
6. A documented policy for channel-specific exclusions so one bad channel or invalid GPS line does not discard otherwise usable rows.

## Prioritized Step 2 implementation plan

1. Build an input validator and immutable row model carrying station ID, source path, source row, raw timestamp, parsed timestamp, and original values.
2. Add deterministic detectors/tests for timestamp reversals, gaps, exact repeats, conflicting timestamp readings, malformed/checksum-invalid GPS, repeated GPS clock offsets, and metadata-position disagreement.
3. Add channel-scoped detectors for physical-domain violations, implausible sentinels, persistence, steps, and peer-relative changes, with evidence thresholds documented and learned from format/domain rules rather than this pack's IDs, dates, or counts.
4. Represent proposed intervals and actions separately from detection evidence. Require explicit review before any correction; never interpolate, clamp RH, invent a wind multiplier, or apply an arbitrary clock shift.
5. Test on synthetic mini-packs covering midnight rollover, circular wind direction, duplicate conflicts, invalid NMEA, station pressure by elevation, normal zero rain/night GHI/100% RH, and partial-channel failures.
6. Only then generate candidate `flags.csv` and the coordinator report. `DECISIONS.md`, the by-hand solar question, recording, and submission remain candidate-owned.

## Commands executed and unresolved items

Representative commands actually executed:

```text
git status --short --branch
git config --get user.name
git config --get user.email
git init
pdfinfo Aeron-AI-Research-Engineer-Intern-AssignmentNew.pdf
pdftoppm -png -r 120 Aeron-AI-Research-Engineer-Intern-AssignmentNew.pdf tmp/pdfs/assignment
python -c "...PdfReader(...).extract_text()..."
python -m py_compile analysis/audit_pack.py
python analysis/audit_pack.py "ridgeline_data_pack (2)" > tmp/audit.json
PowerShell read-only summaries over tmp/audit.json and Import-Csv spot checks
git check-ignore -v <raw-input paths>
git ls-files
git diff --check
```

The PDF renderer emitted missing-display-font warnings for Symbol/ArialUnicode, but rendered pages 3, 5, 6, and 7 were visually checked and legible; exact limits were taken from the rendered pages where extraction was garbled. No ZIP archive was available to preserve or extract, but the already-extracted pack is complete enough for the audit. No raw input has been modified. The full machine audit remains in ignored `tmp/audit.json` and is reproducible from the committed script.

Remember to preserve and later export this complete Codex conversation from the first prompt into `ai_logs/`; do not tidy out mistakes or dead ends.
