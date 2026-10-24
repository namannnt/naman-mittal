#!/usr/bin/env python3
"""Read-only exploratory audit for a Ridgeline-format weather data pack.

The script preserves file order and raw timestamp strings. It writes no files and
prints a JSON summary to stdout so results can be reproduced or redirected to a
temporary, ignored file.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


WEATHER_TIMESTAMP = "%Y-%m-%d %H:%M"
LOGGER_TIMESTAMP = "%Y-%m-%d %H:%M:%S"
ID_COLUMNS = {"timestamp_utc"}
WEATHER_UNITS = {
    "timestamp_utc": "YYYY-MM-DD HH:MM (logger clock, meant to be UTC; interval end)",
    "temp_c": "degrees C",
    "rh_pct": "%",
    "pressure_hpa": "hPa (station pressure, not sea-level pressure)",
    "wind_kmh": "km/h (10-minute mean)",
    "wind_dir_deg": "degrees (direction wind blows from)",
    "rain_mm": "mm in interval",
    "ghi_wm2": "W/m^2 global horizontal irradiance",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pack_dir", type=Path, help="extracted data-pack directory")
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def file_inventory(pack: Path) -> list[dict[str, Any]]:
    result = []
    for path in sorted(p for p in pack.rglob("*") if p.is_file()):
        stat = path.stat()
        result.append(
            {
                "path": path.relative_to(pack).as_posix(),
                "bytes": stat.st_size,
                "sha256": sha256(path),
            }
        )
    return result


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = list(reader.fieldnames or [])
        return fields, [dict(row) for row in reader]


def parse_dt(text: str, fmt: str) -> datetime | None:
    try:
        return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def quantile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] * (upper - position) + ordered[upper] * (position - lower)


def numeric_summary(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"min": None, "q1": None, "median": None, "q3": None, "max": None}
    return {
        "min": min(values),
        "q1": quantile(values, 0.25),
        "median": statistics.median(values),
        "q3": quantile(values, 0.75),
        "max": max(values),
    }


def circular_delta(a: float, b: float) -> float:
    return abs((b - a + 180.0) % 360.0 - 180.0)


def longest_equal_run(
    rows: list[dict[str, str]], channel: str
) -> dict[str, Any] | None:
    best: tuple[int, int, int, str] | None = None
    start = 0
    while start < len(rows):
        value = rows[start].get(channel, "")
        end = start + 1
        while end < len(rows) and rows[end].get(channel, "") == value:
            end += 1
        candidate = (end - start, start, end - 1, value)
        if best is None or candidate[0] > best[0]:
            best = candidate
        start = end
    if best is None:
        return None
    length, first, last, value = best
    return {
        "rows": length,
        "value": value,
        "start_row": first + 2,
        "end_row": last + 2,
        "start_timestamp_raw": rows[first].get("timestamp_utc"),
        "end_timestamp_raw": rows[last].get("timestamp_utc"),
    }


def robust_abrupt_changes(
    rows: list[dict[str, str]], channel: str, parsed: list[float | None]
) -> dict[str, Any]:
    changes: list[tuple[float, int, float, float]] = []
    for idx in range(1, len(parsed)):
        before, after = parsed[idx - 1], parsed[idx]
        if before is None or after is None:
            continue
        magnitude = circular_delta(before, after) if channel == "wind_dir_deg" else abs(after - before)
        changes.append((magnitude, idx, before, after))
    magnitudes = [item[0] for item in changes]
    median_delta = statistics.median(magnitudes) if magnitudes else None
    mad = (
        statistics.median(abs(value - median_delta) for value in magnitudes)
        if magnitudes and median_delta is not None
        else None
    )
    ranked = sorted(changes, key=lambda item: item[0], reverse=True)[:5]
    return {
        "median_abs_adjacent_delta": median_delta,
        "mad_abs_adjacent_delta": mad,
        "largest": [
            {
                "magnitude": magnitude,
                "from_row": idx + 1,
                "to_row": idx + 2,
                "from_timestamp_raw": rows[idx - 1].get("timestamp_utc"),
                "to_timestamp_raw": rows[idx].get("timestamp_utc"),
                "from_value": before,
                "to_value": after,
            }
            for magnitude, idx, before, after in ranked
        ],
    }


def audit_weather(path: Path, nominal_interval: int | None) -> tuple[dict[str, Any], dict[str, dict[datetime, dict[str, float]]]]:
    fields, rows = read_csv(path)
    station_id = path.stem
    timestamp_entries = [
        (index + 2, row.get("timestamp_utc", ""), parse_dt(row.get("timestamp_utc", ""), WEATHER_TIMESTAMP))
        for index, row in enumerate(rows)
    ]
    parsed_timestamps = [item[2] for item in timestamp_entries]
    valid_times = [value for value in parsed_timestamps if value is not None]

    exact_groups: dict[tuple[str, ...], list[int]] = defaultdict(list)
    time_groups: dict[str, list[tuple[int, tuple[str, ...]]]] = defaultdict(list)
    for idx, row in enumerate(rows):
        signature = tuple(row.get(field, "") for field in fields)
        exact_groups[signature].append(idx + 2)
        time_groups[row.get("timestamp_utc", "")].append((idx + 2, signature))

    exact_duplicates = [positions for positions in exact_groups.values() if len(positions) > 1]
    collisions = []
    conflicted_timestamps: set[str] = set()
    for raw_time, entries in time_groups.items():
        distinct = {signature for _, signature in entries}
        if len(distinct) > 1:
            conflicted_timestamps.add(raw_time)
            collisions.append(
                {
                    "timestamp_raw": raw_time,
                    "rows": [position for position, _ in entries],
                    "distinct_readings": len(distinct),
                }
            )

    backwards = []
    gaps = []
    positive_steps = Counter()
    interval_seconds = nominal_interval * 60 if nominal_interval else None
    for idx in range(1, len(rows)):
        previous, current = parsed_timestamps[idx - 1], parsed_timestamps[idx]
        if previous is None or current is None:
            continue
        delta = int((current - previous).total_seconds())
        evidence = {
            "from_row": idx + 1,
            "to_row": idx + 2,
            "from_timestamp_raw": rows[idx - 1].get("timestamp_utc"),
            "to_timestamp_raw": rows[idx].get("timestamp_utc"),
            "delta_seconds": delta,
        }
        if delta < 0:
            backwards.append(evidence)
        elif delta > 0:
            positive_steps[delta] += 1
            if interval_seconds is not None and delta > interval_seconds:
                gaps.append({**evidence, "apparent_missing_intervals": max(0, delta // interval_seconds - 1)})

    channel_summaries: dict[str, Any] = {}
    parsed_channels: dict[str, list[float | None]] = {}
    for field in fields:
        if field in ID_COLUMNS:
            continue
        parsed: list[float | None] = []
        missing_rows: list[int] = []
        non_numeric: list[dict[str, Any]] = []
        for index, row in enumerate(rows):
            raw = row.get(field, "")
            if raw is None or not raw.strip():
                parsed.append(None)
                missing_rows.append(index + 2)
                continue
            try:
                parsed.append(float(raw))
            except ValueError:
                parsed.append(None)
                non_numeric.append({"row": index + 2, "value": raw})
        parsed_channels[field] = parsed
        values = [value for value in parsed if value is not None]
        physical_domain_violation_rows: list[int] = []
        for index, value in enumerate(parsed):
            if value is None:
                continue
            violation = (
                (field == "rh_pct" and not 0 <= value <= 100)
                or (field == "wind_kmh" and value < 0)
                or (field == "wind_dir_deg" and not 0 <= value <= 360)
                or (field in {"rain_mm", "ghi_wm2"} and value < 0)
            )
            if violation:
                physical_domain_violation_rows.append(index + 2)
        channel_summaries[field] = {
            "numeric_count": len(values),
            "missing_count": len(missing_rows),
            "missing_rows_first_20": missing_rows[:20],
            "non_numeric_count": len(non_numeric),
            "non_numeric_first_20": non_numeric[:20],
            "range": numeric_summary(values),
            "basic_physical_domain_violation_count": len(physical_domain_violation_rows),
            "basic_physical_domain_violation_rows_first_20": physical_domain_violation_rows[:20],
            "longest_identical_run": longest_equal_run(rows, field),
            "abrupt_changes": robust_abrupt_changes(rows, field, parsed),
        }

    # Peer eligibility view: keep one copy of identical repeated timestamps, but
    # exclude timestamps containing different readings. This never mutates rows.
    eligible: dict[datetime, dict[str, float]] = {}
    for raw_time, entries in time_groups.items():
        if raw_time in conflicted_timestamps:
            continue
        parsed_time = parse_dt(raw_time, WEATHER_TIMESTAMP)
        if parsed_time is None:
            continue
        row_index = entries[0][0] - 2
        values: dict[str, float] = {}
        for channel, parsed in parsed_channels.items():
            value = parsed[row_index]
            if value is not None:
                values[channel] = value
        eligible[parsed_time] = values

    result = {
        "station_id": station_id,
        "path": path.as_posix(),
        "columns": fields,
        "row_count": len(rows),
        "date_coverage": {
            "first_row_raw": rows[0].get("timestamp_utc") if rows else None,
            "last_row_raw": rows[-1].get("timestamp_utc") if rows else None,
            "minimum_parsed": min(valid_times).strftime(WEATHER_TIMESTAMP) if valid_times else None,
            "maximum_parsed": max(valid_times).strftime(WEATHER_TIMESTAMP) if valid_times else None,
            "invalid_timestamp_count": sum(value is None for value in parsed_timestamps),
        },
        "order_and_duplicates": {
            "backward_timestamp_count": len(backwards),
            "backward_timestamps": backwards,
            "exact_repeated_row_group_count": len(exact_duplicates),
            "exact_repeated_row_extra_count": sum(len(group) - 1 for group in exact_duplicates),
            "exact_repeated_row_groups_first_20": exact_duplicates[:20],
            "conflicting_timestamp_count": len(collisions),
            "conflicting_timestamps": collisions,
            "apparent_gap_count": len(gaps),
            "apparent_gaps": gaps,
            "positive_adjacent_step_seconds_counts": {
                str(seconds): count for seconds, count in positive_steps.most_common()
            },
        },
        "peer_eligible_unique_timestamp_count": len(eligible),
        "channels": channel_summaries,
    }
    return result, {station_id: eligible}


def nmea_checksum(sentence: str) -> tuple[bool, str | None]:
    if not sentence.startswith("$") or "*" not in sentence:
        return False, "missing '$' prefix or checksum separator"
    body, supplied = sentence[1:].rsplit("*", 1)
    if not re.fullmatch(r"[0-9A-Fa-f]{2}", supplied):
        return False, "checksum is not two hexadecimal digits"
    checksum = 0
    for char in body:
        checksum ^= ord(char)
    return checksum == int(supplied, 16), None


def nmea_coordinate(value: str, hemisphere: str, latitude: bool) -> float | None:
    try:
        degree_digits = 2 if latitude else 3
        degrees = int(value[:degree_digits])
        minutes = float(value[degree_digits:])
        coordinate = degrees + minutes / 60.0
        if hemisphere in {"S", "W"}:
            coordinate *= -1
        if hemisphere not in {"N", "S", "E", "W"}:
            return None
        return coordinate
    except (TypeError, ValueError):
        return None


def parse_rmc_datetime(time_text: str, date_text: str) -> datetime | None:
    base_time = time_text.split(".", 1)[0]
    try:
        return datetime.strptime(date_text + base_time, "%d%m%y%H%M%S").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def compress_offset_runs(items: list[tuple[int, float, str]]) -> list[dict[str, Any]]:
    if not items:
        return []
    runs: list[dict[str, Any]] = []
    start = 0
    rounded = [round(item[1] / 60.0) for item in items]
    for idx in range(1, len(items) + 1):
        if idx < len(items) and rounded[idx] == rounded[start]:
            continue
        section = items[start:idx]
        runs.append(
            {
                "offset_minutes_rounded": rounded[start],
                "count": len(section),
                "first_source_row": section[0][0],
                "last_source_row": section[-1][0],
                "first_logger_timestamp_raw": section[0][2],
                "last_logger_timestamp_raw": section[-1][2],
            }
        )
        start = idx
    return runs


def audit_gps(path: Path, metadata: dict[str, str] | None) -> dict[str, Any]:
    counts = Counter()
    errors: list[dict[str, Any]] = []
    offsets: list[tuple[int, float, str]] = []
    positions: list[tuple[float, float]] = []
    gga_fix_quality = Counter()
    gga_satellites: list[int] = []
    gga_altitudes: list[float] = []
    rmc_status = Counter()

    with path.open("r", encoding="utf-8-sig", errors="replace") as handle:
        lines = list(handle)
    for line_number, raw_line in enumerate(lines, 1):
        line = raw_line.rstrip("\r\n")
        counts["lines"] += 1
        if "," not in line:
            counts["malformed"] += 1
            errors.append({"row": line_number, "reason": "missing logger/sentence separator"})
            continue
        logger_raw, sentence = line.split(",", 1)
        logger_time = parse_dt(logger_raw, LOGGER_TIMESTAMP)
        if logger_time is None:
            counts["invalid_logger_timestamp"] += 1
        checksum_ok, checksum_error = nmea_checksum(sentence)
        if checksum_ok:
            counts["checksum_valid"] += 1
        else:
            counts["checksum_invalid"] += 1
            errors.append({"row": line_number, "reason": checksum_error or "checksum mismatch", "type": sentence[1:6] if sentence.startswith("$") else None})

        content = sentence[1:].split("*", 1)[0] if sentence.startswith("$") else sentence
        fields = content.split(",")
        kind = fields[0][-3:] if fields and len(fields[0]) >= 3 else "UNKNOWN"
        counts[f"type_{kind}"] += 1
        if not checksum_ok:
            counts[f"checksum_invalid_type_{kind}"] += 1
        try:
            if kind == "RMC":
                status = fields[2]
                rmc_status[status or "blank"] += 1
                gps_time = parse_rmc_datetime(fields[1], fields[9])
                if gps_time is None:
                    counts["rmc_invalid_datetime"] += 1
                if logger_time is not None and gps_time is not None and checksum_ok:
                    offsets.append((line_number, (logger_time - gps_time).total_seconds(), logger_raw))
                lat = nmea_coordinate(fields[3], fields[4], True)
                lon = nmea_coordinate(fields[5], fields[6], False)
                if checksum_ok and status == "A" and lat is not None and lon is not None:
                    positions.append((lat, lon))
                elif status != "A":
                    counts["rmc_untrustworthy_status"] += 1
            elif kind == "GGA":
                quality = fields[6] or "blank"
                gga_fix_quality[quality] += 1
                if fields[7]:
                    gga_satellites.append(int(fields[7]))
                if fields[9]:
                    gga_altitudes.append(float(fields[9]))
                lat = nmea_coordinate(fields[2], fields[3], True)
                lon = nmea_coordinate(fields[4], fields[5], False)
                if checksum_ok and quality not in {"", "0"} and lat is not None and lon is not None:
                    positions.append((lat, lon))
                elif quality in {"", "0"}:
                    counts["gga_no_fix"] += 1
            else:
                counts["unsupported_type"] += 1
        except (IndexError, TypeError, ValueError) as exc:
            counts["malformed"] += 1
            errors.append({"row": line_number, "reason": f"{kind} parse error: {exc}"})

    position_summary: dict[str, Any] = {"trustworthy_position_count": len(positions)}
    if positions:
        median_lat = statistics.median(point[0] for point in positions)
        median_lon = statistics.median(point[1] for point in positions)
        position_summary.update({"median_lat": median_lat, "median_lon": median_lon})
        if metadata:
            try:
                reference_lat = float(metadata["lat"])
                reference_lon = float(metadata["lon"])
                distances = [haversine_km(reference_lat, reference_lon, lat, lon) for lat, lon in positions]
                position_summary.update(
                    {
                        "distance_to_station_metadata_m": {
                            "median": statistics.median(distances) * 1000,
                            "max": max(distances) * 1000,
                        }
                    }
                )
            except (KeyError, TypeError, ValueError):
                position_summary["metadata_comparison_error"] = "missing or non-numeric metadata coordinates"

    offset_values = [item[1] for item in offsets]
    return {
        "station_id": path.stem,
        "path": path.as_posix(),
        "counts": dict(sorted(counts.items())),
        "rmc_status": dict(sorted(rmc_status.items())),
        "gga_fix_quality": dict(sorted(gga_fix_quality.items())),
        "gga_satellites": numeric_summary([float(value) for value in gga_satellites]),
        "gga_altitude_m": numeric_summary(gga_altitudes),
        "logger_minus_gps_seconds": numeric_summary(offset_values),
        "logger_minus_gps_offset_runs": compress_offset_runs(offsets),
        "position_agreement": position_summary,
        "errors_first_50": errors[:50],
    }


def load_metadata(pack: Path) -> tuple[list[str], list[dict[str, str]], dict[str, dict[str, str]]]:
    fields, rows = read_csv(pack / "stations.csv")
    by_station = {row.get("station_id", ""): row for row in rows}
    return fields, rows, by_station


def maintenance_notes(pack: Path) -> list[dict[str, Any]]:
    path = pack / "maintenance_log.md"
    if not path.exists():
        return []
    pattern = re.compile(r"^(\d{4}-\d{2}-\d{2})\s+(\S+)\s+(.*)$")
    notes = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        match = pattern.match(line)
        if match:
            notes.append(
                {
                    "source_row": line_number,
                    "date_raw": match.group(1),
                    "station_id": match.group(2),
                    "note": match.group(3),
                    "timezone_explicit": False,
                }
            )
    return notes


def maintenance_event_context(
    notes: list[dict[str, Any]], eligible: dict[str, dict[datetime, dict[str, float]]]
) -> list[dict[str, Any]]:
    """Compare three full logger-clock days before/after each note date.

    The note date is excluded because most notes omit a time and all omit a
    timezone. These summaries expose possible relationships, not causation.
    """
    results = []
    for note in notes:
        try:
            event_date = datetime.strptime(note["date_raw"], "%Y-%m-%d").date()
        except (KeyError, TypeError, ValueError):
            continue
        station_id = note.get("station_id", "")
        observations = eligible.get(station_id, {})
        before: dict[str, list[float]] = defaultdict(list)
        after: dict[str, list[float]] = defaultdict(list)
        for stamp, channels in observations.items():
            day_delta = (stamp.date() - event_date).days
            target = before if -3 <= day_delta <= -1 else after if 1 <= day_delta <= 3 else None
            if target is not None:
                for channel, value in channels.items():
                    target[channel].append(value)
        channel_context = {}
        for channel in sorted(set(before) | set(after)):
            before_values = before.get(channel, [])
            after_values = after.get(channel, [])
            before_median = statistics.median(before_values) if before_values else None
            after_median = statistics.median(after_values) if after_values else None
            channel_context[channel] = {
                "before_count": len(before_values),
                "before_median": before_median,
                "after_count": len(after_values),
                "after_median": after_median,
                "after_minus_before_median": (
                    circular_delta(before_median, after_median)
                    if channel == "wind_dir_deg" and before_median is not None and after_median is not None
                    else after_median - before_median
                    if before_median is not None and after_median is not None
                    else None
                ),
            }
        results.append(
            {
                **note,
                "window_definition": (
                    "Three full logger-clock calendar days before versus after; note date excluded. "
                    "Maintenance timezone is unknown."
                ),
                "channels": channel_context,
            }
        )
    return results


def peer_comparisons(
    metadata: dict[str, dict[str, str]], eligible: dict[str, dict[datetime, dict[str, float]]]
) -> list[dict[str, Any]]:
    results = []
    station_ids = sorted(eligible)
    for left_index, left_id in enumerate(station_ids):
        for right_id in station_ids[left_index + 1 :]:
            left_meta, right_meta = metadata.get(left_id, {}), metadata.get(right_id, {})
            try:
                distance = haversine_km(
                    float(left_meta["lat"]), float(left_meta["lon"]),
                    float(right_meta["lat"]), float(right_meta["lon"]),
                )
                elevation_difference = abs(float(left_meta["elevation_m"]) - float(right_meta["elevation_m"]))
            except (KeyError, TypeError, ValueError):
                distance, elevation_difference = None, None
            overlap = sorted(set(eligible[left_id]) & set(eligible[right_id]))
            channel_differences: dict[str, Any] = {}
            channels = sorted(
                set().union(*(set(eligible[left_id][stamp]) for stamp in overlap))
                & set().union(*(set(eligible[right_id][stamp]) for stamp in overlap))
            ) if overlap else []
            for channel in channels:
                differences = []
                for stamp in overlap:
                    if channel not in eligible[left_id][stamp] or channel not in eligible[right_id][stamp]:
                        continue
                    first = eligible[left_id][stamp][channel]
                    second = eligible[right_id][stamp][channel]
                    delta = circular_delta(first, second) if channel == "wind_dir_deg" else abs(first - second)
                    differences.append(delta)
                if differences:
                    channel_differences[channel] = {
                        "count": len(differences),
                        "median_absolute_difference": statistics.median(differences),
                        "q95_absolute_difference": quantile(differences, 0.95),
                    }
            results.append(
                {
                    "station_a": left_id,
                    "station_b": right_id,
                    "distance_km": distance,
                    "elevation_difference_m": elevation_difference,
                    "overlapping_eligible_timestamps": len(overlap),
                    "channel_differences": channel_differences,
                }
            )
    return results


def main() -> int:
    args = parse_args()
    pack = args.pack_dir.resolve()
    required = [pack / "README.md", pack / "stations.csv", pack / "maintenance_log.md", pack / "data", pack / "gps"]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise SystemExit("Pack is missing required paths: " + ", ".join(missing))

    metadata_fields, metadata_rows, metadata = load_metadata(pack)
    intervals = {}
    for station_id, row in metadata.items():
        try:
            intervals[station_id] = int(row.get("logger_interval_min", ""))
        except ValueError:
            intervals[station_id] = None

    weather_results = []
    all_eligible: dict[str, dict[datetime, dict[str, float]]] = {}
    for path in sorted((pack / "data").glob("*.csv")):
        result, eligible = audit_weather(path, intervals.get(path.stem))
        weather_results.append(result)
        all_eligible.update(eligible)

    gps_results = [audit_gps(path, metadata.get(path.stem)) for path in sorted((pack / "gps").glob("*.nmea"))]
    notes = maintenance_notes(pack)
    output = {
        "audit_version": 1,
        "pack_path": str(pack),
        "read_only": True,
        "inventory": file_inventory(pack),
        "metadata": {
            "columns": metadata_fields,
            "station_count": len(metadata_rows),
            "rows": metadata_rows,
        },
        "weather_schema_units_from_pack_readme": WEATHER_UNITS,
        "weather": weather_results,
        "gps": gps_results,
        "maintenance_notes": notes,
        "maintenance_event_context": maintenance_event_context(notes, all_eligible),
        "peer_comparison_policy": (
            "Compare only parseable timestamps after excluding timestamps with conflicting readings; "
            "collapse exact timestamp repeats to one observation; report geography/elevation and do not "
            "assume any peer is a clean reference. Wind direction uses circular distance."
        ),
        "peer_comparisons": peer_comparisons(metadata, all_eligible),
    }
    json.dump(output, fp=__import__("sys").stdout, indent=2, sort_keys=True, allow_nan=False)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
