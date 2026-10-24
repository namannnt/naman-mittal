# Step 2B correctness review

This review supersedes the provisional interpretations in `step2_validation.md` where they differ. The review examined actual code, output CSVs, synthetic tests, and source records. Its outcome is 15 flags (13 exclude, one correct, one keep), not a target count. No supplied inputs were changed.

## Output contract

The previous CSV already used `temp_c`, `pressure_hpa`, `rh_pct`, `rain_mm`, and `wind_kmh`; friendly labels appeared only in the chat summary. No channel rename was needed. The exact header remains:

```text
station_id,channel,start_utc,end_utc,issue,action,note
```

Actions are exactly `exclude`, `correct`, `keep`. Generated timestamps use `YYYY-MM-DD HH:MM`, in UTC, and intervals are inclusive and ordered. Runtime validation now rejects invalid channels and reversed intervals. Output still goes to the current working directory. The supplied-pack schema check and the clean-pack subprocess test exercise actual CSV output and alternate-CWD behavior.

## Material problems and resolutions

| Concern | Finding and resolution |
|---|---|
| Sustained-change recovery | Pressure and wind previously extended exclusions to coverage end unconditionally. They now require a populated 24-hour return toward the established baseline before ending a flag and refine the recovery boundary locally. A synthetic temporary pressure/wind/RH test verifies exact onset and last bad observation. |
| Wind event versus recovery | Selecting the numerically strongest split could choose recovery as the fault, and shorter windows could promote an earlier transient. The checker now considers chronological event clusters, checks that the local pre-change relationship agrees with the earlier established relationship, and requires three populated daily windows of sustained change. The synthetic transient-plus-later-fault test checks default and 48-hour windows independently. |
| S04 temperature omission | The old detector silently suppressed subthreshold candidates. The reviewed S04 evidence supports an unresolved daylight effect, documented below; diagnostics now expose it. No temperature correction or exclusion is forced. |
| Disputed location used in peers | S05 could previously participate in spatial selection despite its coordinate conflict. Both target and reference use of a disputed station are now disabled for geography-based checks. Its weather remains available for independent channel/domain checks. |
| Replays contaminated original observations | Source-index masking removed later copies, but the interval mask also removed original observations at those times from peer references. Replay interval flags are now ignored by that second mask; source identity alone selects the later copies. |
| Conflict misreported as missing | Removing conflicted timestamps before coverage analysis could create an artificial gap. Coverage now counts a timestamp as present even when its readings cannot serve as a reference. |
| Clock reset plus outage | The former exact-one-interval test rejected a reset coinciding with missing observations and searched outside the GPS transition. Boundaries now use absolute GPS constraints, a unique source-order discontinuity, and positive interval-grid elapsed UTC; source row count never supplies elapsed time. Ambiguous or late initial evidence stays diagnostic. |
| GPS repetition | Position repetition is now counted as distinct logger-minute epochs as well as messages. Repeated copies of one RMC epoch cannot establish a timing segment or repeated position evidence. Coordinate parsing also rejects invalid minutes and wrong hemispheres. |
| Detector ordering | Each detector now sees one reference mask across all stations in its pass; metadata row ordering no longer changes which newly detected flags contaminate references within that pass. |

## S04 temperature investigation

`analysis/review_step2b.py` reproduces these derived comparisons from the inputs. The painting note date is used to examine the hypothesis, never in detection. Exclude the note date itself; compare March 1-14 with March 16-April 11. Use corrected UTC, unique observations, and metadata-eligible peers S02, S06, S03, S08, S07; exclude disputed-location S05 and mask S03's known temperature failures. No peer is assumed calibrated or clean in every channel.

| Conditions | Before: median S04-minus-peer temperature, count | After: median, count | Difference in medians |
|---|---|---|---|
| Strong sunlight, GHI >=500 W/m2 | -0.400 C, 405 | +1.425 C, 884 | +1.825 C |
| Night, GHI <=10 W/m2 | +0.150 C, 1,016 | 0.000 C, 1,835 | -0.150 C |
| Cloudy at high-sun clock bins | -1.250 C, 24 | -1.000 C, 26 | +0.250 C |
| Strong sunlight, wind <5 km/h | -0.100 C, 125 | +1.975 C, 202 | +2.075 C |
| Strong sunlight, wind 5-15 km/h | -0.300 C, 231 | +1.600 C, 515 | +1.900 C |
| Strong sunlight, wind >=15 km/h | -1.200 C, 49 | +0.500 C, 167 | +1.700 C |

Cloudy classification uses clock bins whose empirical 95th-percentile GHI is at least 500 W/m2, with actual GHI at most 35% of that potential. This avoids labelling dawn/dusk as cloudy; it is a rough empirical control, not a solar-position calculation. Cloudy samples are few. Pairwise sunny residual changes are +2.0 C versus S02, +1.8 versus S03, +2.2 versus S06, +2.1 versus S07, and +1.9 versus S08, so the result is not only one neighbour's failure or a pre-existing absolute station offset. S03 has fewer after samples because its failed temperature intervals are masked.

**Outcome: unresolved, with a supported radiation-related hypothesis.** The pattern survives wind strata and differs from night/cloudy behavior. Painting/changed radiation exposure is plausible, but the note does not establish causation or UTC onset. Real local surface heating, seasonally changing solar exposure, terrain, radiation-shield ventilation and imperfect references remain alternatives. No exact onset or recovery is established, and matching S04 temperatures to neighbours would not be a calibration. The broad 72-hour daylight detector's largest contrast is +1.25 C versus +0.10 C at night around March 21 06:00, below its 4 C action rule; that statistical candidate is not the painting time. Previously there was neither a flag nor a visible diagnostic; it is now explicitly present in `diagnostics.csv` and in limitations. A co-located shielded reference and a shielding/exposure inspection would settle the action more effectively than lowering a threshold until a flag appears.

## S07 wind boundary, metric and persistence

The old March 26 18:00 start came from a six-hour search grid and did not identify the first affected interval. A local fixed-level L1 split on log-ratios now selects **March 26 15:40 UTC**. Raw speed falls from 2.3 at 15:30 to 0.3 km/h at 15:40, with subsequent values 0.4, 0.2, 0.3, 0.4. This is useful supporting local evidence, not proof of the exact physical replacement instant. An interval-end timestamp also cannot identify when within that interval a hardware change occurred.

Peers are S08, S03, S02, S04. Eligibility requires matching unique corrected UTC, usable wind data, two peers, the distance/elevation limits, and peer median wind >=3 km/h. Define `R=(station wind+3)/(peer median wind+3)`. The reported **0.44** is `exp(median(log R) after - median(log R) before)`, with 416 before and 429 after observations in the 72-hour windows around the coarse March 26 18:00 candidate. It is a change in a smoothed relative metric, not a raw wind-speed ratio or a calibrated correction multiplier.

The first qualifying event must agree with an earlier established baseline and persist across three populated daily windows. Recovery requires the full-day baseline-return rule. Daily smoothed ratios remain about 0.37-0.54 after March 27 through pack end, compared with a variable established pre-event relationship near one; no sustained recovery is demonstrated. The date-only different-brand replacement note corroborates the failure hypothesis but supplies no UTC boundary. Boundary sensitivity remains material: using a 4 km/h floor moves the local estimate to 19:50, so the default 15:40 exclusion is a statistical choice, not a precise technician timestamp.

## S04 rain: onset, release and recovery

The zero run begins March 23 06:00 (CSV row 3,206), immediately after a 0.2 mm reading at 05:50. A dry run alone does not establish failure. After excluding disputed-location S05 from spatial evidence, the first interval with at least two wet peers is **March 29 03:10**. There are 144 corroborating regional-wet intervals within the zero run. The conservative suspect exclusion now starts at that first affirmative discrepancy and ends April 2 16:00; the earlier dry portion is visible as onset uncertainty in diagnostics and remains outside exclusion. Dry slots within the suspect interval are included because the subsequent release and maintenance evidence corroborate a persistent gauge state, though the exact physical blockage time is unknown.

Release readings are separate: rows 4,707-4,709 at April 2 16:10, 16:20, 16:30 contain 11.0, 11.2, 11.2 mm. Eligible peers are dry at those times. These observations are excluded without guessing when the water originally fell. The April 2 note reports debris/funnel cleaning around 10; its timezone is unspecified.

After 16:40 there are 1,340 observations, 26 wet intervals, 5.2 mm total, and a maximum of 0.2 mm per interval. Other stations' totals over the same reconstructed-UTC interval range from 1.8 to 9.0 mm (S02 4.2, S03 3.2, S06 7.6, S07 1.8, S08 3.6). The first subsequent small rain is April 2 19:20. This supports resumed operation and gives no basis for extending the blockage/release exclusion to pack end; it does not certify gauge calibration.

## S02 and S05 recovery

S02's source-row pressure step remains March 21 17:20; the residual shift changes from +6.7 to **+6.9 hPa** because disputed-location S05 is no longer a spatial reference. Each side has 432 valid observations. Daily S02-to-eligible-peer residuals remain separated from the earlier baseline through April 11; the recovery check does not find a return, so the end stays at coverage end. No pressure calibration is inferred.

S05 RH exclusion still ends at March 11 00:00 (row 1,442, RH 104%). Row 1,443 at 00:10 is 7%. All **4,607 later readings** are in-domain; none is excluded by this episode. Dense clustering includes 53 intervening in-domain observations among 451 above-domain values in a 504-row episode. This is justified by a highly concentrated fault episode, not a rule that 100% saturation alone is bad. Synthetic genuine saturation remains unflagged.

## S05 location interpretation

Metadata latitude/longitude are **39.57000, -104.89570**. Trustworthy GPS median coordinates are approximately **39.75395, -104.89569**. There are **1,146 valid position messages across 982 distinct logger-minute epochs**, with median separation **20.45 km**. Same-epoch RMC/GGA messages corroborate one receiver epoch; they are not independent site visits, receivers or measurements of station identity.

Confidence that the sources disagree is very high; confidence that metadata specifically is wrong is low. Alternatives include metadata error, receiver/static-coordinate configuration, relocation, mixed files or identity/cabling errors. No coordinates are replaced. The `metadata/exclude` flag targets disputed location information only, explicitly retaining weather channels. Spatial attribution and location-based comparisons involving S05 are suspended until checked. Its RH flag depends only on physical RH constraints and no disputed coordinate. Other stations' peer-based flags now exclude S05 as a reference.

## S06 and S08 provenance

CSV source row numbers **include the header as row 1**. S06 row 3,410 raw 2025-03-24 16:00 stays 16:00 UTC. Row **3,411** raw **10:10** becomes **16:10 UTC** by **+21,600 seconds**. Row 3,412 raw 10:20 becomes 16:20. GPS row 664 says logger 16:00:01/GPS 16:00; GPS row 665 says logger 11:00:01/GPS 17:00, followed by 438 coherent offset observations. The original discontinuity independently determines which weather rows receive correction.

All **6,048 S06 records** and their source identities survive; reconstructed UTC is strictly increasing and has 6,048 unique timestamps. There is no artificial overlap or gap. The synthetic reset-plus-outage case deliberately omits six intervals at a -90-minute reset across year rollover: every remaining row maps to independently specified UTC, six missing slots stay missing, and source row number is never used as elapsed time. Another test leaves an offset change without a matching weather boundary unresolved.

S08 still has **5,978 raw = 5,834 unique + 144 replay extras**. Missing slots are **214** between March 16 14:00 and March 18 01:30, determined from distinct observed timestamps. `5,834+214=6,048` nominal slots. Later source rows **5,836-5,979** exactly repeat originals **4,828-4,971**. The flag excludes only later occurrences, the originals remain eligible, completeness counts unique times, and nothing is filled.

## Tests mapped to outcomes

The original 11 passing tests did not test recovery, clock reset with an outage, channel vocabulary, or independent GPS epoch counts. Their assertions were inspected rather than inferred from the count. Six focused tests were added and existing assertions retained/updated:

| Test | Observable outcome checked |
|---|---|
| `replay_conflict_gap_and_required_schema` | Replay, conflict and gap issues distinguished; conflict does not invent a coverage gap; actual CSV header. |
| `clock_offsets_both_signs_rollover_and_row_preservation` | +2 h/-90 min logger offsets, correct inverse transformation, UTC rollover, source rows retained, input hashes unchanged. |
| `invalid_void_and_missing_gps_do_not_create_location_flag` | Invalid/void/missing position evidence causes no location flag; S/W degrees/minutes conversion. |
| `temperature_flatline_but_zero_rain_and_night_ghi_are_normal` | A multi-hour temperature freeze is excluded; normal rain/GHI zeros are not. |
| `humidity_violation_not_genuine_saturation` | >100% excluded, genuine 100% retained, non-numeric temperature excluded. |
| `shared_pressure_and_wind_event_is_not_local_fault` | Shared synthetic events do not become local pressure/wind failures. |
| `local_pressure_shift_generalizes_to_reordered_ids_and_dates` | Independently introduced shift detected with changed IDs/order/dates. |
| `insufficient_peers_stays_diagnostic` | One-station pressure step does not force a peer-based action. |
| `persistent_wind_scale_change` | Independently introduced sustained local wind fault detected. |
| `rain_blockage_release_and_daylight_temperature_shift` | Strong synthetic blockage/release and daylight-only bias detected. |
| `clean_pack_header_only_deterministic_and_current_directory_output` | Subprocess output in alternate CWD, exact header-only clean result, repeated bytes equal. |
| `temporary_pressure_wind_humidity_faults_end_at_recovery` (new) | Exact synthetic onset/end, no recovered observations excluded, valid channel/action/ordered timestamp contract, input hashes retained. |
| `clock_reset_with_outage_preserves_observed_rows_and_real_gap` (new) | Reset plus six absent intervals reconstructs every actual observation and only the genuine gap. |
| `clock_evidence_without_weather_boundary_remains_unresolved` (new) | GPS change without weather evidence does not force correction. |
| `disputed_location_does_not_exclude_weather_or_support_spatial_peers` (new) | 48 messages/24 epochs counted separately, weather retained, disputed peer cannot authorize another station's flag, replayed single epoch does not satisfy evidence count. |
| `late_initial_gps_offset_does_not_force_whole_file_correction` (new) | Late nonzero GPS offset does not retroactively change earlier weather. |
| `transient_wind_event_does_not_displace_later_persistent_fault` (new) | A 36-hour transient/recovery does not displace a later sustained fault, in default and 48-hour windows. |

Actual full-suite result after the focused fixes: **17 tests passed**, 8.109 seconds. The first temporary-fault test failed because the old strongest-split logic chose recovery; that failure was fixed and the focused test rerun. Early sensitivity passes also exposed transient/recovery misclassification, motivating baseline and daily-confirmation evidence requirements. These failures are part of the authentic review history.

## Validation commands and preservation

```text
python -m unittest discover -s tests -k temporary -v
python -m unittest discover -s tests -k transient -v
python -m unittest discover -s tests -v
python analysis/review_step2b.py "ridgeline_data_pack (2)" > tmp/step2b-evidence.json
python analysis/validate_step2b.py "ridgeline_data_pack (2)" > tmp/step2b-validation.json
git diff --check
```

The validation script runs the supplied pack, a repeat, an absolute-path CLI call from a different working directory, strict CSV contract assertions, 12 heuristic variants and before/after input hashes. It retains only derived summaries under ignored `tmp/`. All **19 supplied files** were also compared with the Step 1 inventory hashes: **zero changes**. Final `flags.csv` and `diagnostics.csv` are byte-identical across the root, repeat and alternate-CWD runs. SHA-256 values:

```text
flags.csv        b4c3fc3817e553c369e63b1e1f382056370ef0d0055ef10bd36373aaa301ba56
diagnostics.csv  5574c1b8e4516ae2f578c7c3b26279669c9a1ea89e20c6d799e07ceba275e071
```

Final outputs contain **15 flags and 22 diagnostics**. The diagnostics include uncertainty and assessment limitations, not 22 additional proven faults.

## Final threshold sensitivity

All comparisons below include station, channel, issue, action, start and end, rather than only flag count. These are final results after the transient/recovery fixes; the earlier sensitivity failures described above are not hidden.

| Variant | Final difference from defaults |
|---|---|
| Pressure residual threshold 2 or 5 hPa (default 3) | No action or interval changes. |
| Wind factor threshold 1.75 (default 2) | No action or interval changes after baseline/persistence confirmation. |
| Wind factor threshold 2.5 | S07 wind flag disappears; default observed metric magnitude is about 2.27. This remains material action sensitivity. |
| Comparison window 48 or 96 hours (default 72) | No action or interval changes after the recovery/baseline fixes. |
| Wind floor 2 km/h (default 3) | No action or interval changes. |
| Wind floor 4 km/h | S07 start moves from March 26 15:40 to 19:50; action/end unchanged. This limits physical onset precision. |
| Rain minimum regional-wet intervals 24 (default 12) | No changes. |
| Rain minimum wet peers 3 (default 2) | S04 suspect start moves 40 minutes, from March 29 03:10 to 03:50; release action and recovery unchanged. |
| Daylight action threshold 3 C (default 4) | Adds an S06 temperature exclusion from March 29 06:00 to coverage end (+3.3 C daylight contrast). It lacks independent physical confirmation and stays diagnostic by default. |
| Daylight action threshold 5 C | No changes. S04 temperature remains diagnostic in all these runs. |

The current defaults were not lowered to force S04 temperature into the flags. The wind evidence rules were strengthened because independent synthetic outcomes and sensitivity exposed actual onset/recovery errors, rather than to preserve a particular flag count.

## Previous versus current flags

| Previous decision | Current decision | Reason |
|---|---|---|
| S01 `pressure_hpa` keep | Same | Station pressure plus independently agreeing elevation remains supported. |
| S02 `pressure_hpa`, Mar 21 17:20 to end | Same scope/action; +6.9 hPa evidence and recovery checked | Disputed S05 reference removed; no recovery established. |
| Five S03 `temp_c` exclusions | Same | Four isolated spikes and exact 481-row freeze reconfirmed. |
| S04 `rain_mm`, Mar 23 06:00-Apr 2 16:30 combined | Suspect interval **Mar 29 03:10-Apr 2 16:00**, separate release **Apr 2 16:10-16:30** | Do not equate a dry-run beginning with affirmative failure; keep release observations distinct. |
| S04 temperature absent from diagnostics | Unresolved temperature diagnostic added; no action | Supported sunny-only pattern, but uncertain cause/scope and below action rule. |
| S05 metadata exclusion | Same action with location-only wording, message/epoch counts; spatial peer use suspended | Weather values must not be silently dropped or disputed coordinates used as trusted geometry. |
| S05 RH episode | Same | Demonstrated recovery already stops exclusion; no recovered tail included. |
| S06 +6 h correction from row 3,411 | Same | Provenance and combined-reset/outage algorithm verified. |
| S07 `wind_kmh` from Mar 26 18:00 | **Mar 26 15:40**, still to end | Coarse scan refined locally, baseline/persistence/recovery assessed; physical onset remains uncertain. |
| S08 gap and later replay copies | Same | Exact reconciliation and occurrence-specific treatment verified. |

No flags were added merely to recover an expected count. Splitting rain is why 14 rows became 15. Broader diagnostic visibility is intentional.

## Limits and report gate

The default flags can inform report drafting with the uncertainty stated here. S04 temperature remains unresolved; S07 statistical onset and threshold sensitivity must not be presented as an exact physical event. S05 spatial identity needs verification. Pressure/wind recovery recognizes the first supported event and its return, not arbitrary recurring cycles. Daylight-temperature action recovery is still a limitation on other packs; supplied S04 is diagnostic. Geographic/elevation selection does not model terrain or certify peers. No report, candidate-owned decisions, manual solar calculation, recording, publication or submission was authored in this step. Preserve the complete conversation, including failed tests and intermediate reasoning, for `ai_logs/`.
