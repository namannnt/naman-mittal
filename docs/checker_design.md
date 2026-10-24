# Checker design

## Command and outputs

Run from the directory where outputs should be written:

```text
python checker.py <pack-directory>
```

The checker uses only Python 3.11+ standard-library modules. It always writes `flags.csv` and `diagnostics.csv` into the current working directory. `flags.csv` contains exactly the assignment columns, in this order: `station_id, channel, start_utc, end_utc, issue, action, note`. A successful pack with no justified flags produces only that header. `diagnostics.csv` is deliberately separate and contains unresolved candidates or evidence limitations; it is not part of the assignment's flag schema.

## Provenance and processing order

Every in-memory weather record retains station ID, source path, one-based CSV source row (header is row 1), raw timestamp text, parsed logger time, interpreted UTC, applied correction seconds, correction evidence, raw fields, and parsed numeric values. Clock interpretation creates new immutable records and never overwrites input files.

Processing order is intentional:

1. Validate the pack paths/schema and load records in original file order.
2. Parse GPS without assuming station identity or message validity.
3. Estimate supported logger-minus-GPS offset segments.
4. Match offset changes to source-order weather discontinuities and construct interpreted UTC.
5. Identify exact replay occurrences, conflicting observations, and coverage gaps.
6. Run physical, persistence, spike, location, and peer-based checks.
7. Write deterministically sorted flags and diagnostics.

Temporal alignment and peer comparisons therefore use corrected UTC, not raw logger timestamps. Exact replay copies and unresolved same-time conflicts do not enter peer reference series.

## GPS validity and clock reconstruction

- NMEA checksum syntax and XOR values are validated before evidence is used.
- RMC dates and times are parsed together, so UTC midnight/date rollover is preserved.
- RMC status `A` plus a valid checksum and coordinates is required for trusted RMC position evidence. GGA position requires a valid checksum and positive fix quality.
- Timing evidence is separate: checksum-valid, parseable RMC date/time plus a parseable logger timestamp can estimate clock offset even when RMC navigation status is `V`. A void position does not automatically make its clock text wrong, and it never validates a position.
- GGA fix quality and altitude are parsed, but GGA lacks a date and is not used alone to establish absolute time.
- Coordinates convert NMEA degrees/minutes to signed decimal degrees with explicit N/S/E/W handling.

For each valid RMC message:

```text
offset = logger timestamp - GPS UTC timestamp
corrected UTC = logger timestamp - offset
```

Offsets are rounded to one minute to absorb ordinary 0-2 second logging latency. At least six consecutive coherent observations are required. A meaningful change is at least five minutes. For a changed segment, the checker searches original weather order for the discontinuity predicted by:

```text
expected raw step = nominal interval + new offset - old offset
```

Only a match within two minutes authorizes a weather-row correction. If GPS shows a changed offset but the first affected weather row is not established, the candidate remains diagnostic. A non-zero offset consistently supported from the start may correct the entire file. The flag states the sign, magnitude, source-row range, and GPS evidence count; corrected times are verified by construction against GPS.

Location disagreement requires at least 20 trustworthy positions and a median separation of at least 5 km. The flag says only that GPS and metadata disagree; it does not decide whether metadata, GPS identity, relocation, or labelling is responsible.

## Timeline semantics

- **Exact replay:** a later raw row has exactly the same timestamp and fields as an earlier row. Only the later occurrence is flagged. The note names replay and original source-row ranges so the valid original is not excluded.
- **Conflict:** multiple non-replay rows map to the same interpreted UTC but have different readings. All conflicting occurrences are excluded because no version is preferred.
- **Gap:** after clock reconstruction and replay/conflict handling, consecutive unique observations are more than one nominal interval apart. The flag covers only the absent interval slots; no interpolation is performed.

`start_utc` and `end_utc` are inclusive. They refer to reconstructed UTC where a supported correction exists. Weather timestamps are interval-end labels. For replay flags, the period identifies the timestamps involved, while the note limits exclusion to named replay source rows.

## Physical and sensor checks

All adjustable values live in `quality_checker/config.py`. The defaults separate hard measurement constraints from heuristic evidence:

| Check | Default evidence for an action |
|---|---|
| Physical domain | RH outside 0-100%; negative wind/rain/GHI; direction outside 0-360. Dense episodes may bridge at most 12 intervening intervals only when at least 50% of the full span violates the domain; the note reports violating count and total span. |
| Missing/non-numeric | A timestamped channel value cannot be parsed; exclude only consecutive affected values and do not impute. |
| Persistence | Exact temperature or pressure value for at least 6 hours; wind direction for 12 hours only when median wind is at least 3 km/h. Zero rain and nighttime zero GHI have no persistence rule; 100% RH alone has no fault rule. |
| Isolated temperature spike | At least 20 C from a 12-neighbour median, at least 12 robust MAD units, and adjacent values return within 4 C. |
| Peer eligibility | At most 100 km away and 500 m elevation difference; pressure uses 250 m. At least two eligible peers at a timestamp and at least 48 overlapping points are expected. Already excluded channel/time intervals cannot serve as peer evidence. |
| Pressure shift | Raw adjacent step at least 3 hPa plus a station-minus-peer median change at least 3 hPa, with at least 144 observations on each side in 72-hour windows. Absolute station pressure is never checked against sea-level limits. |
| Wind scale | Compare smoothed station/peer ratios only when peer median wind is at least 3 km/h; require a factor-of-two relationship change and at least 144 observations per 72-hour side. Boundaries are scanned every six hours and are explicitly approximate. |
| Daylight temperature | Station-minus-peer daylight residual changes at least 4 C while night residual changes no more than 1.5 C; each daylight/night side needs at least 24 matched observations. GHI defines daylight, not clock hour. |
| Rain blockage/release | At least 72 continuous zero-rain hours, at least two peers wet in 12 intervals, then within three intervals a station-only reading of at least 5 mm while peer median is at most 0.2 mm. Without release/service evidence it remains diagnostic. |
| High-elevation pressure keep | Metadata elevation at least 2,000 m, median station pressure at most 800 hPa, trustworthy GPS altitude within 150 m, and no pressure/metadata exclusion. This is affirmative evidence that low station pressure is real. |

Wind direction differences, where used, are circular; 360 degrees is north. Wind ratios avoid calm references. Shared pressure/wind changes cancel in station-to-peer relationships and are tested synthetically. Peers are contextual references, never assumed ground truth.

Maintenance notes can corroborate a detected event within one calendar day. They never create a detector boundary, and output states that their timezone is unspecified.

## Action policy

- `exclude`: observations or metadata are unreliable for the climate summary and no defensible recovery is available.
- `correct`: a reproducible transformation is supported by repeated independent evidence, with sign, magnitude, and source-row scope stated in the note.
- `keep`: an odd-looking value has affirmative physical/metadata/GPS support.

Unresolved suspicion is never labelled `keep`. Candidates lacking peers, an exact clock boundary, a release signature, or a defensible calibration go to `diagnostics.csv`. The checker never clamps RH, interpolates gaps, redistributes rain, guesses a wind multiplier, adjusts pressure to match neighbours, or silently produces a modified dataset.

## Determinism and known limitations

Outputs are sorted by station, reconstructed start, channel, issue, action, and end. CSV uses UTF-8 and LF line endings. No random sampling is used.

The checker is deliberately conservative. A pressure/wind/daylight shift is flagged from its supported boundary through available coverage; automatic recovery detection is not yet implemented. Peer rules can miss faults at isolated stations or in sparse networks. Geographic thresholds do not model mountain barriers. Rain detection needs an unusually strong blockage-plus-release signature. Maintenance text is corroboration only. These limitations are preferable to unsupported confident flags and are recorded in diagnostics where applicable.
