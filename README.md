Naman Mittal
naman.mittal.btech2023@sitpune.edu.in
Recording link: https://drive.google.com/file/d/12xBzKS9RWaG5GZ5qF9YhhwhObZrIrYEN/view?usp=drive_link
Run: python checker.py "ridgeline_data_pack (2)"

# Ridgeline network quality review

This repository contains an offline quality checker for the Ridgeline weather-station data pack, the resulting flags and diagnostics, and a coordinator-facing network health report. Decisions and limitations are discussed in DECISIONS.md. The recording linked above demonstrates the evidence for the S03 temperature flatline and the less-certain S07 wind-scale exclusion.

## Run and reproduce

Use Python 3.11 or newer (`python --version`). Runtime, analysis scripts and synthetic tests use only the standard library plus the included `quality_checker` package; no pip installation, API key, network access or environment setup is needed. `requirements.txt` records this intentionally empty dependency set. The portability check verifies imports with site packages disabled.

Run the command shown above from the repository root with the supplied extracted folder at that path, or replace the quoted argument with the actual absolute/relative pack location:

```text
python checker.py "path with spaces/to/pack folder"
python -m unittest discover -s tests -v
```

Both `flags.csv` and supplementary `diagnostics.csv` are written to the **current working directory**, replacing files of those names. To preserve reviewed outputs, run from a separate output directory using the absolute path to `checker.py` and the pack. Keep the complete `quality_checker/` directory beside the entry script; sharing `checker.py` alone is insufficient. Inputs are read-only; no cleaned dataset is silently written.

Expected private input structure (not included in this repository/bundle):

```text
pack folder/
  stations.csv
  data/<station_id>.csv
  gps/<station_id>.nmea
  maintenance_log.md
```

`stations.csv` uses `station_id,name,lat,lon,elevation_m,installed,logger_interval_min`. Each weather CSV requires `timestamp_utc,temp_c,rh_pct,pressure_hpa,wind_kmh,wind_dir_deg,rain_mm,ghi_wm2`. GPS lines are `logger timestamp,NMEA sentence`. The `gps/` directory is required; an absent station GPS file supplies no timing/location evidence. Maintenance notes are optional corroboration, never an event timestamp or replacement for observations. Station IDs, dates, interval and row counts are read from inputs, not fixed to this pack.

## Implemented checks

Thresholds are in `quality_checker/config.py`; full evidence rules and processing order are in [checker design](docs/checker_design.md).

| Check | What it does |
|---|---|
| Schema and parsing | Reject missing required paths/weather columns; diagnose unparseable times and exclude missing/non-finite/non-numeric channel values. |
| Clock reconstruction | Validate NMEA checksums and full RMC date/time; require repeated coherent offsets and a uniquely GPS-bracketed source-order weather boundary before applying a clock correction. |
| Replay, conflicts, gaps | Remove later exact raw-row replay occurrences only; exclude unresolved differing observations at the same interpreted UTC; identify absent nominal time slots without filling them. |
| Physical domains | Check RH 0-100%, strictly positive absolute station pressure, nonnegative wind/rain/GHI and direction 0-360 degrees (360 is north); dense violation episodes can include short intervening in-domain runs only across continuous UTC. |
| Persistence | Detect exact temperature/pressure runs of at least six hours and direction runs of at least twelve hours with active wind; require valid increasing UTC at the nominal interval. Invalid times, outages, collisions and excluded rows break runs. Zero rain, night-zero GHI and RH 100% alone are not faults. |
| Temperature spikes | Require a large robust neighbourhood departure with an immediate return; not a hardcoded sentinel-value list. |
| Location | Compare repeated valid GPS position epochs with metadata; flag location only and suspend disputed coordinates in spatial peer selection. Timing and position validity are separate. |
| Pressure shift | Require a raw step and persistent station-minus-peer change, rather than rejecting mountain station pressure as too low. |
| Wind-scale change | Detect a persistent peer-relative ratio change with baseline/daily confirmation, refine an approximate split and check recovery; never infer a calibration multiplier. |
| Daylight temperature | Compare day/night peer residual changes using GHI, with weaker unresolved candidates in diagnostics. This is heuristic evidence, not proof of a shield fault. |
| Rain blockage/release | Require a long zero run, corroborating wet peers and a station-only release signature; start the suspect period at corroborating wet evidence, not the dry-run beginning. |
| Supported low pressure | Require a broad elevation-based plausibility screen for every pressure value, repeated valid GPS altitude evidence and no contradictory pressure/timeline/metadata exclusion; withhold keep if support is inadequate. This is not calibration. |

Peer checks require sufficient geographically/elevation-eligible, aligned observations, and mask known exclusions. Pressure/wind recovery requires sustained return to the prior relationship. Maintenance notes may corroborate detected events but cannot create their boundaries.

## Output and provenance

`flags.csv` has exactly these columns, in order:

```text
station_id,channel,start_utc,end_utc,issue,action,note
```

`channel` is a weather column, `all`, or `metadata`. `exclude` withholds affected observations/metadata; a gap describes absent slots, not another subtraction from existing data. `correct` states the supported timestamp transformation and source scope. `keep` records affirmative support for an odd-looking real measurement, not uncertain suspicion. `note` supplies one sentence of evidence and, for corrections, the transformation. The current supplied-pack output has 15 flags; this count is not a target for unseen packs. A successful flag-free pack produces a header-only file.

Times are `YYYY-MM-DD HH:MM` with **inclusive** endpoints in reconstructed UTC, where supported; raw logger labels denote interval ends and are intended UTC. Immutable records retain raw timestamp, original file, source row, interpreted UTC and correction evidence. Source-row references are one-based CSV record numbers with the header as row 1; they are not elapsed time. S06's supported correction adds six hours only to named affected source rows. No measurement calibration is applied.

A replay flag's calendar period does not invalidate genuine original observations in that period: its note selects only the later copy rows. Raw signatures use field names, not CSV column positions; moving the timestamp column cannot hide a conflict. Resolve occurrence identity before applying channel/time masks. Metadata exclusions do not blanket-exclude weather. `diagnostics.csv` separately records unresolved candidates, evidence and missing evidence; it has `station_id,channel,start_utc,end_utc,candidate,evidence,missing_evidence` and is not an extra set of automatic exclusions.

## Limits and report policy

Unflagged or retained does not mean certified accurate. Peers are contextual, not calibrated references; distance/elevation rules do not capture mountain barriers. Sparse peers can hide faults. Rain detection misses blockage without a convincing release. Pressure/wind handle the first supported persistent event and its recovery, not arbitrary recurrent cycles. Daylight-temperature action recovery is not implemented. Physical cause, exact onset, calibration, interpolation, rain redistribution, full climate aggregation and live operational monitoring are not provided. Synthetic tests exercise transfer to renamed/reordered/shifted packs, not every unseen-pack failure mode. [Step 2B review](docs/step2b_review.md) supersedes the older Step 2 counts and documents sensitivity; [independent-review fixes](docs/independent_review_fixes.md) records the subsequent four correctness fixes and expanded regression results.

The self-contained [coordinator report](report.html) makes a **separate reporting precaution** for unresolved S04 temperature: withhold daytime maxima and unqualified full-period means pending a shield/reference check; labelled night-only descriptions remain provisional. This adds no checker exclusion/correction. S05's location sources disagree: labelled weather time series remain available, but mapping, spatial attribution and location-weighted network use must wait for identity/location reconciliation. S07's March 26 15:40 split is statistical and approximate: changing the wind floor moves it to 19:50 and a stricter factor threshold suppresses the flag. It is not a known hardware-change instant or a justified multiplier. Other unresolved temperature/rain warnings also qualify summary use.

## Report and review tools

Open `report.html` directly offline. It uses embedded CSS/system fonts and no external figures, JavaScript, CDN or missing generated asset. Prior colour/grayscale A4 visual proofs and exact print settings are recorded in [report method](docs/report_method.md); Step 4 does not claim a new visual inspection. The ignored local proofs are retained, not shipped as runtime dependencies.

```text
python analysis/build_report.py "path with spaces/to/pack folder"
python analysis/validate_source_review.py "path with spaces/to/pack folder"
```

The first command rebuilds the **supplied-snapshot-specific** report at repository root and derived assessment under ignored `tmp/`, stopping if rerun checker rows differ from reviewed CSVs. It is not an unseen-pack report generator. The second requires Git, archives committed HEAD into a temporary tracked-only copy, checks imports/tests, runs both CWD cases, compares CSV bytes, rebuilds the report and checks raw hashes. Commit intended changes before using it; it deliberately does not validate uncommitted edits. Optional print QA uses `node analysis/render_report.cjs <playwright-module> <browser-executable>` plus Poppler; these local tools are not checker/test dependencies. Both tool arguments must be supplied for that optional script.

Audit/review sources are in `analysis/` and `docs/`. [Step 4 validation](docs/step4_validation.md) records actual clean-copy commands/results and bundle boundaries. The review ZIP contains tracked source, package, tests, outputs and documentation, **not the private pack or Git history**. Existing genuine commits remain in the local repository; no push, publication or form submission has been performed.
