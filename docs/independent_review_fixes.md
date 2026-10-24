# Step 4B: independently reproduced correctness fixes

Baseline: clean `master` at `23047fda7689fc0c782897fb861d58acbd939ec9`. The four reported cases were converted to regression tests and **executed against the original implementation before any detection fix**. Each failed as reported. The existing 17-test pass did not cover these cases; it was not evidence that the implementation was generally correct. This record supersedes earlier implementation-correctness claims where these cases are concerned, without rewriting the historical validation records.

## Before / after reproductions

| Case | Observed before the fix | Observed after the fix |
|---|---|---|
| Forty ten-minute temperature readings fixed at 6.5, final timestamp `not-a-time` | `AssertionError` in `_persistence_checks`: the equal-value loop consumed the untimed last row. | Completes; all 40 source records preserved, row 41 retains its raw text and `interpreted_utc=None`; one untimed timestamp diagnostic identifies row 41. The independently valid 39-row run is excluded only through 06:20 (rows 2-40), not the invalid row. |
| Four daily ten-observation bursts at 6.5 | Incorrect persistence exclusion joins 40 source-adjacent observations across outages, describing 6.7 hours of persistence. | No persistence exclusion: each burst is only ten nominal slots. Three separate gaps remain, each with 134 absent slots, from 01:40 through 23:50 on its day. |
| Twenty-four pressures alternating -5/-4 hPa at 2,913 m with valid matching GPS | Affirmative keep for median -4.5 hPa; no pressure physical-domain exclusion. Zero and tiny positive controls were also wrongly kept. | Nonpositive pressure is excluded; no keep. Tiny positives 1/2 hPa get no automatic keep and are not forced into a guessed elevation-based exclusion. Plausible 709/710 hPa with adequate GPS remains eligible. |
| Twenty-four observations plus a changed-temperature same-time observation; timestamp-first versus temperature-first CSV | Timestamp-first detects conflict; temperature-first loses it. The failure was reproduced before changing signatures. | Both orders produce identical flag rows, including a conflict at 01:40 naming source rows 12-13. A later exact replay at row 27 alone is removed; its genuine original at row 6 survives. Peer-series grouping independently rejects the conflict in both orders. |

The fixtures use synthetic 2036 dates, not supplied station identities or dates. For the column-order test, a redundant test-level `IndexError` followed the initial failed subtest before the final comparison was guarded by an explicit result-count assertion; the detector failure itself was the missing conflict. Failed attempts are not erased or converted into successful claims.

## Root causes and focused changes

### 1-2. UTC continuity, not source adjacency

`_persistence_checks` originally checked the first timestamp, then extended on equal values and source adjacency alone. It neither validated later timestamps nor required the metadata interval between them. Removing its assertion alone would have concealed the error instead of fixing it.

`_continuous_links` now admits a link only when both adjacent source observations have interpreted UTC, neither is timeline-excluded and their UTC difference is exactly the stated positive recording interval. The persistence loop can extend only over these links. Invalid times, outages, backward time, off-grid steps, unresolved conflicts and replay exclusions therefore break runs. Independently valid long runs still flag, and original raw records/diagnostics remain intact. Duration retains the existing interval-end-slot convention (`count × interval`), rather than silently changing thresholds or supplied evidence notes.

The requested nearby audit found two **demonstrated** related failures: missing-value and physical-domain groups merged four separated bursts into one interval, and backwards-ordered bursts raised `ValueError: flag interval is reversed`. Both were reproduced before fixing those consumers. `_group_temporal` now gates their existing grouping/density rules with the same UTC links, including every intervening row in a dense episode. Afterward each case emits four correctly bounded ten-reading groups and three gaps, without a crash. This is a concrete related correction, not a general detector rewrite.

Other grouping uses were inspected. Replay groups describe source occurrences, not sensor persistence; rain zero-runs already require nominal UTC spacing. No unrelated heuristic or threshold was adjusted to recover a preferred supplied-pack count.

### 3. Pressure validity and affirmative keep evidence

`_physical_violation` had no pressure rule, while `_high_elevation_keep` treated any median below 800 hPa as altitude-supported. GPS altitude also needed stronger validity, repetition and coherence checks.

- Nonpositive **absolute station pressure** is now a physical-domain violation. Missing/nonfinite values retain the existing missing-value handling.
- Keep requires metadata height in 2,000-11,000 m and every timestamped pressure inside a wide 0.70-1.30 band around an approximate tropospheric reference, as well as the existing low-median criterion. A plausible median cannot conceal one tiny positive reading. Withhold keep outside support; the band is **not** a pressure exclusion, expected reading, calibrated correction or accuracy guarantee.
- The model and limits are documented in `checker_design.md`, with the [NASA Glenn primary reference](https://www1.grc.nasa.gov/beginners-guide-to-aeronautics/earth-atmosphere-equation-metric/). NASA supplies an approximate altitude relationship, **not** the chosen ±30% screening policy. The band is deliberately coarse and cannot certify climate-quality measurements.
- Altitude support requires a valid checksum/position, measured-fix quality 1-5, explicit metre units, finite altitude and parseable logger/GGA fix times. Estimated/manual/simulated/unknown modes cannot support keep. Require at least 20 distinct logger-minute labels and 20 logger-date/GGA-fix-minute buckets; at least 80% of per-bucket median heights and the overall median must agree with metadata within 150 m. Duplicate/stale fixes do not gain votes merely because logger labels advance. GGA has no date; the logger-date bucket is a deduplication device, not an invented absolute GPS timestamp. [Trimble's primary GGA documentation](https://receiverhelp.trimble.com/oem-gnss/nmea0183-messages-gga.html) describes quality/height/unit fields; no receiver-specific calibration has been assumed.
- Any existing all/pressure/metadata exclusion still vetoes a whole-period pressure keep. Tests cover missing pressure, nonpositive pressure, pressure flatline, replay and disputed location.

Additional altitude subtests caught malformed and stale GGA fix times in the first attempted guard, which initially checked only logger time/units/finiteness. Those subtests failed, then the fix-time validity/deduplication guard was added and the full suite rerun. The final result below includes these cases, not just the earlier partial fix.

Supplied S01 remains a qualified keep, not a certified reference: pressure min/median/max **683.5 / 709.4 / 730.1 hPa**; metadata height **2,913 m**; **166** accepted altitude buckets with median **2,912.85 m**, all within the 150 m tolerance. The broad screening band at that height is approximately **496.9-922.7 hPa**; all pressures pass and the median also meets the existing <=800 hPa condition. That does not establish small-bias accuracy, traceable calibration or trustworthy peers.

### 4. Keyed signatures, not positional slices

`WeatherRecord.signature()[1:]` discarded whichever field happened to be first. Moving `temp_c` ahead of `timestamp_utc` thus erased the only changed reading from conflict comparison. Both `_timeline_checks` and `_unique_series` used this assumption.

Signatures are now sorted `(name, raw value)` pairs. Full signatures include every field and the raw timestamp for exact-replay identity; `include_timestamp=False` explicitly omits only the field named `timestamp_utc` for same-interpreted-time readings. Raw strings, extra columns and source rows are preserved. All `signature()[1:]` uses were removed. The report builder and historical replay audit use full signatures and need no compatibility workaround.

## Regression methods and actual execution

All additions are in `tests/test_checker.py`, using generated private-pack-free fixtures:

| New regression method | Outcome |
|---|---|
| `test_invalid_timestamp_breaks_persistence_and_preserves_diagnostic` | Pass: retained record/diagnostic and independently bounded valid run. |
| `test_persistence_does_not_bridge_daily_outages` | Pass: no flatline; three exact coverage gaps. |
| `test_high_elevation_pressure_requires_positive_plausible_values` | Pass: negative, zero, tiny positive and plausible controls. |
| `test_conflicts_and_replays_are_independent_of_column_order` | Pass: identical decisions, source provenance and peer-series safeguards in both orders. |
| `test_missing_and_domain_groups_require_continuous_utc` | Pass: missing/domain bursts in forward and backward source order. |
| `test_high_elevation_keep_requires_repeated_valid_altitude_epochs` | Pass: valid control plus single/repeated/sparse fixes, wrong units, bad checksums, invalid/estimated/simulated fixes, invalid logger/fix time, stale fixes, nonfinite and inconsistent heights. |
| `test_pressure_keep_cannot_contradict_existing_exclusions` | Pass: all five exclusion controls. |
| `test_persistence_breaks_at_invalid_backward_offgrid_and_conflicted_rows` | Pass: five discontinuity/exclusion controls. |
| `test_pressure_keep_checks_whole_series_and_elevation_plausibility` | Pass: one tiny value, mismatched elevation pressure, plausible higher site and unsupported model height. |

Actual baseline reproduction commands used the bundled Python executable with `-E -S -m unittest discover -s tests -k <method-substring> -v`, separately for the four primary methods and then for demonstrated audit/altitude failures. After the final fixes, the full command was:

```text
python -E -S -m unittest discover -s tests -v
```

Observed final working-tree result: **26 tests passed in 8.098 s**, exit 0 (**17 existing + 9 new methods**; parameter subtests are not inflated into the method count). Executable: `C:\Users\dell\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe`, Python 3.12.14 on Windows. This is a fresh executed result, not an inference from earlier test history. Earlier intermediate runs and failures are distinct from this final pass.

## Supplied-pack validation and report

From separate CWD `C:\Users\dell\Desktop\bb bn\tmp\step4b supplied output`, actually executed:

```text
python -E -S "C:\Users\dell\Desktop\bb bn\checker.py" "C:\Users\dell\Desktop\bb bn\ridgeline_data_pack (2)"
```

The same exact bundled executable was used. It exited 0 and wrote **15 flags / 22 diagnostics** into that CWD. Direct byte comparisons against both root reviewed files and `git show 23047fd:<file>` passed for both CSVs: **no supplied-pack action, interval or evidence-note change**. The count was not forced; stronger predicates happen to retain these supplied-pack decisions.

```text
flags.csv        b4c3fc3817e553c369e63b1e1f382056370ef0d0055ef10bd36373aaa301ba56
diagnostics.csv  5574c1b8e4516ae2f578c7c3b26279669c9a1ea89e20c6d799e07ceba275e071
report.html      45d133a4d095d33e0c6849f1d2ee1a2f42fc11cc798a419d879c4648b8cfbcd1
```

All **19 raw files** were compared with Step 1's retained inventory and matched. Running `python -E -S analysis/build_report.py "C:\Users\dell\Desktop\bb bn\ridgeline_data_pack (2)"` then regenerated the assessment and unchanged HTML successfully. The exact report content/layout bytes remain unchanged, so prior print evidence is retained and **no new visual render is claimed or needed**. Scientific caveats for S04 temperature, S05 location, S07 sensitivity and other unresolved diagnostics have not been weakened.

## Commit / clean bundle procedure and remaining limits

The six staged files (core/config/tests, README, design and this findings record) were inspected; no private input, PDF, environment, cache, render or secret was staged. Genuine local fix commit: `a919c95e8aab8c03ba6967d1d32f9d3e7fc2f73b`.

After that commit, actually ran `python -E -S analysis/validate_source_review.py "C:\Users\dell\Desktop\bb bn\ridgeline_data_pack (2)"` with the same bundled interpreter. It archived **all 26 committed tracked files** into `tmp/source review n024zzx7/tracked copy`, with the private pack separate and no ignored helper copied. The clean-copy suite passed **26 tests in 9.833 s**, exit 0. The package import, both checker CWD cases and report regeneration all exited 0; CSV/report hashes matched those above, the input hash inventory was unchanged for all 19 files, and AST import checking found no third-party Python dependency. Full subprocess argv/results are retained locally in ignored `tmp/step4b-clean-copy.json`. This is distinct from the working-tree run above. The follow-up commit records only this observed validation; the delivered archive is regenerated from final HEAD.

Regenerate only the clean source bundle with:

```text
git archive --format=zip --output=tmp/review_bundle.zip HEAD
```

Check its member set and each file's bytes against final HEAD. The full package, tests, configuration, README, documentation and reviewed outputs belong in this archive; raw inputs, assignment PDF, `.git`, secrets, caches and temporary renders do not. `tmp/` is ignored, preventing recursive inclusion. The externally shared whole-working-folder ZIP reportedly contained raw data and temporary files: **it is not this source archive and must not become the public submission**. This step does not delete or publish any outer archive.

Limits remain: coarse plausibility is not calibration; repeated GPS fixes do not prove receiver identity/vertical accuracy; terrain peers are not certified; recurrent pressure/wind cycles and daylight-temperature recovery remain limited as documented. Nominal-interval continuity is intentionally conservative and may split runs at timestamp jitter. Regression coverage does not guarantee all malformed/unseen packs. No new report verdict, manual solar-time working, personal `DECISIONS.md`, genuine AI export, own-voice video, public remote or form submission was created. Those candidate-owned requirements and README identity/link placeholders remain pending. This is readying a source review, not declaring submission readiness.
