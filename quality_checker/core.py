"""General-purpose Ridgeline data quality checker.

The module never modifies source files. Weather records remain in source order
and carry both raw logger time and a separately reconstructed UTC view.
"""

from __future__ import annotations

import csv
import hashlib
import math
import re
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

from .config import DEFAULT_THRESHOLDS, Thresholds


FLAG_COLUMNS = ["station_id", "channel", "start_utc", "end_utc", "issue", "action", "note"]
DIAGNOSTIC_COLUMNS = [
    "station_id",
    "channel",
    "start_utc",
    "end_utc",
    "candidate",
    "evidence",
    "missing_evidence",
]
WEATHER_TIMESTAMP = "%Y-%m-%d %H:%M"
LOGGER_TIMESTAMP = "%Y-%m-%d %H:%M:%S"
CHANNELS = (
    "temp_c",
    "rh_pct",
    "pressure_hpa",
    "wind_kmh",
    "wind_dir_deg",
    "rain_mm",
    "ghi_wm2",
)


@dataclass(frozen=True)
class WeatherRecord:
    station_id: str
    source_file: str
    source_row: int
    raw_timestamp: str
    logger_time: datetime | None
    interpreted_utc: datetime | None
    correction_seconds: int
    correction_evidence: str
    raw_fields: tuple[tuple[str, str], ...]
    numeric_values: tuple[tuple[str, float | None], ...]

    def value(self, channel: str) -> float | None:
        return dict(self.numeric_values).get(channel)

    def signature(self) -> tuple[str, ...]:
        return tuple(value for _, value in self.raw_fields)


@dataclass(frozen=True)
class GPSObservation:
    station_id: str
    source_file: str
    source_row: int
    raw_logger_timestamp: str
    logger_time: datetime | None
    sentence_type: str
    checksum_valid: bool
    gps_time: datetime | None
    rmc_status: str | None
    gga_fix_quality: int | None
    latitude: float | None
    longitude: float | None
    altitude_m: float | None

    @property
    def trustworthy_time(self) -> bool:
        # RMC status describes navigation/position validity. A checksum-valid,
        # parseable RMC date/time remains timing evidence even when status is V.
        return self.sentence_type == "RMC" and self.checksum_valid and self.gps_time is not None and self.logger_time is not None

    @property
    def trustworthy_position(self) -> bool:
        if not self.checksum_valid or self.latitude is None or self.longitude is None:
            return False
        if self.sentence_type == "RMC":
            return self.rmc_status == "A"
        if self.sentence_type == "GGA":
            return self.gga_fix_quality is not None and self.gga_fix_quality > 0
        return False


@dataclass(frozen=True)
class OffsetSegment:
    offset_seconds: int
    observations: int
    first_source_row: int
    last_source_row: int
    first_logger_time: datetime
    last_logger_time: datetime
    first_gps_time: datetime
    last_gps_time: datetime


@dataclass(frozen=True)
class Flag:
    station_id: str
    channel: str
    start_utc: datetime
    end_utc: datetime
    issue: str
    action: str
    note: str

    def __post_init__(self) -> None:
        if self.action not in {"exclude", "correct", "keep"}:
            raise ValueError(f"unsupported action: {self.action}")

    def as_row(self) -> dict[str, str]:
        return {
            "station_id": self.station_id,
            "channel": self.channel,
            "start_utc": self.start_utc.strftime(WEATHER_TIMESTAMP),
            "end_utc": self.end_utc.strftime(WEATHER_TIMESTAMP),
            "issue": self.issue,
            "action": self.action,
            "note": self.note,
        }


@dataclass(frozen=True)
class Diagnostic:
    station_id: str
    channel: str
    start_utc: datetime | None
    end_utc: datetime | None
    candidate: str
    evidence: str
    missing_evidence: str

    def as_row(self) -> dict[str, str]:
        return {
            "station_id": self.station_id,
            "channel": self.channel,
            "start_utc": self.start_utc.strftime(WEATHER_TIMESTAMP) if self.start_utc else "",
            "end_utc": self.end_utc.strftime(WEATHER_TIMESTAMP) if self.end_utc else "",
            "candidate": self.candidate,
            "evidence": self.evidence,
            "missing_evidence": self.missing_evidence,
        }


@dataclass
class StationData:
    station_id: str
    metadata: dict[str, str]
    interval_minutes: int
    records: list[WeatherRecord]
    gps: list[GPSObservation]
    offsets: list[OffsetSegment]


@dataclass(frozen=True)
class CheckResult:
    flags: tuple[Flag, ...]
    diagnostics: tuple[Diagnostic, ...]
    stations: tuple[StationData, ...]


def _parse_datetime(value: str, fmt: str) -> datetime | None:
    try:
        return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def _median(values: Iterable[float]) -> float | None:
    materialized = list(values)
    return statistics.median(materialized) if materialized else None


def _mad(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    center = statistics.median(values)
    return statistics.median(abs(value - center) for value in values)


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6_371_008.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def input_hashes(pack: Path) -> dict[str, str]:
    return {
        path.relative_to(pack).as_posix(): _sha256(path)
        for path in sorted(candidate for candidate in pack.rglob("*") if candidate.is_file())
    }


def _nmea_checksum(sentence: str) -> bool:
    if not sentence.startswith("$") or "*" not in sentence:
        return False
    body, supplied = sentence[1:].rsplit("*", 1)
    if not re.fullmatch(r"[0-9A-Fa-f]{2}", supplied):
        return False
    checksum = 0
    for character in body:
        checksum ^= ord(character)
    return checksum == int(supplied, 16)


def nmea_coordinate(value: str, hemisphere: str, latitude: bool) -> float | None:
    try:
        degree_digits = 2 if latitude else 3
        degrees = int(value[:degree_digits])
        minutes = float(value[degree_digits:])
        result = degrees + minutes / 60.0
        if hemisphere in {"S", "W"}:
            result *= -1
        elif hemisphere not in {"N", "E"}:
            return None
        if (latitude and not -90 <= result <= 90) or (not latitude and not -180 <= result <= 180):
            return None
        return result
    except (TypeError, ValueError):
        return None


def _rmc_datetime(time_text: str, date_text: str) -> datetime | None:
    try:
        whole_seconds = time_text.split(".", 1)[0]
        return datetime.strptime(date_text + whole_seconds, "%d%m%y%H%M%S").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def _parse_gps_file(path: Path, station_id: str) -> list[GPSObservation]:
    observations: list[GPSObservation] = []
    with path.open("r", encoding="utf-8-sig", errors="replace") as handle:
        for source_row, raw_line in enumerate(handle, 1):
            line = raw_line.rstrip("\r\n")
            if "," not in line:
                observations.append(
                    GPSObservation(station_id, path.as_posix(), source_row, "", None, "UNKNOWN", False, None, None, None, None, None, None)
                )
                continue
            logger_raw, sentence = line.split(",", 1)
            logger_time = _parse_datetime(logger_raw, LOGGER_TIMESTAMP)
            checksum_valid = _nmea_checksum(sentence)
            content = sentence[1:].split("*", 1)[0] if sentence.startswith("$") else sentence
            fields = content.split(",")
            kind = fields[0][-3:] if fields and len(fields[0]) >= 3 else "UNKNOWN"
            gps_time = None
            status = None
            fix_quality = None
            latitude = longitude = altitude = None
            try:
                if kind == "RMC":
                    gps_time = _rmc_datetime(fields[1], fields[9])
                    status = fields[2]
                    latitude = nmea_coordinate(fields[3], fields[4], True)
                    longitude = nmea_coordinate(fields[5], fields[6], False)
                elif kind == "GGA":
                    fix_quality = int(fields[6]) if fields[6] else None
                    latitude = nmea_coordinate(fields[2], fields[3], True)
                    longitude = nmea_coordinate(fields[4], fields[5], False)
                    altitude = float(fields[9]) if fields[9] else None
            except (IndexError, TypeError, ValueError):
                pass
            observations.append(
                GPSObservation(
                    station_id,
                    path.as_posix(),
                    source_row,
                    logger_raw,
                    logger_time,
                    kind,
                    checksum_valid,
                    gps_time,
                    status,
                    fix_quality,
                    latitude,
                    longitude,
                    altitude,
                )
            )
    return observations


def _offset_segments(observations: Sequence[GPSObservation], config: Thresholds) -> list[OffsetSegment]:
    points: list[tuple[GPSObservation, int]] = []
    unit = config.gps_offset_round_seconds
    for observation in observations:
        if not observation.trustworthy_time:
            continue
        raw_offset = (observation.logger_time - observation.gps_time).total_seconds()  # type: ignore[operator]
        rounded = int(round(raw_offset / unit) * unit)
        points.append((observation, rounded))
    if not points:
        return []
    raw_segments: list[list[tuple[GPSObservation, int]]] = []
    current = [points[0]]
    for point in points[1:]:
        if point[1] == current[-1][1]:
            current.append(point)
        else:
            raw_segments.append(current)
            current = [point]
    raw_segments.append(current)
    segments = []
    for segment in raw_segments:
        if len(segment) < config.gps_min_segment_observations:
            continue
        first, last = segment[0][0], segment[-1][0]
        assert first.logger_time and last.logger_time and first.gps_time and last.gps_time
        segments.append(
            OffsetSegment(
                offset_seconds=segment[0][1],
                observations=len(segment),
                first_source_row=first.source_row,
                last_source_row=last.source_row,
                first_logger_time=first.logger_time,
                last_logger_time=last.logger_time,
                first_gps_time=first.gps_time,
                last_gps_time=last.gps_time,
            )
        )
    return segments


def _load_weather(path: Path, station_id: str) -> list[WeatherRecord]:
    records = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = list(reader.fieldnames or [])
        missing_fields = {"timestamp_utc", *CHANNELS} - set(fields)
        if missing_fields:
            raise ValueError(f"{path} is missing required columns: {sorted(missing_fields)}")
        for source_row, row in enumerate(reader, 2):
            raw_timestamp = row.get("timestamp_utc", "")
            logger_time = _parse_datetime(raw_timestamp, WEATHER_TIMESTAMP)
            numeric = []
            for channel in CHANNELS:
                raw = row.get(channel, "")
                try:
                    value = float(raw) if raw is not None and raw.strip() else None
                    if value is not None and not math.isfinite(value):
                        value = None
                except ValueError:
                    value = None
                numeric.append((channel, value))
            records.append(
                WeatherRecord(
                    station_id=station_id,
                    source_file=path.as_posix(),
                    source_row=source_row,
                    raw_timestamp=raw_timestamp,
                    logger_time=logger_time,
                    interpreted_utc=logger_time,
                    correction_seconds=0,
                    correction_evidence="uncorrected logger time",
                    raw_fields=tuple((field, row.get(field, "")) for field in fields),
                    numeric_values=tuple(numeric),
                )
            )
    return records


def _load_pack(pack: Path, config: Thresholds) -> tuple[list[StationData], list[dict[str, str]]]:
    required = [pack / "stations.csv", pack / "data", pack / "gps"]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise ValueError("pack is missing required paths: " + ", ".join(missing))
    with (pack / "stations.csv").open("r", encoding="utf-8-sig", newline="") as handle:
        metadata_rows = list(csv.DictReader(handle))
    stations = []
    for metadata in metadata_rows:
        station_id = metadata.get("station_id", "").strip()
        if not station_id:
            continue
        weather_path = pack / "data" / f"{station_id}.csv"
        gps_path = pack / "gps" / f"{station_id}.nmea"
        if not weather_path.exists():
            raise ValueError(f"missing weather file for {station_id}: {weather_path}")
        records = _load_weather(weather_path, station_id)
        gps = _parse_gps_file(gps_path, station_id) if gps_path.exists() else []
        try:
            interval = int(metadata.get("logger_interval_min", "10"))
        except ValueError:
            interval = 10
        stations.append(StationData(station_id, dict(metadata), interval, records, gps, _offset_segments(gps, config)))
    return stations, metadata_rows


def _find_clock_boundary(
    records: Sequence[WeatherRecord], old_offset: int, new_offset: int, interval_seconds: int, config: Thresholds
) -> int | None:
    expected_raw_delta = interval_seconds + (new_offset - old_offset)
    candidates = []
    for index in range(1, len(records)):
        previous, current = records[index - 1].logger_time, records[index].logger_time
        if previous is None or current is None:
            continue
        raw_delta = int((current - previous).total_seconds())
        error = abs(raw_delta - expected_raw_delta)
        if error <= config.gps_boundary_tolerance_seconds:
            candidates.append((error, index))
    return min(candidates)[1] if candidates else None


def _apply_clock_evidence(station: StationData, config: Thresholds) -> tuple[list[Flag], list[Diagnostic]]:
    flags: list[Flag] = []
    diagnostics: list[Diagnostic] = []
    segments = station.offsets
    if not station.records or not segments:
        if not segments:
            diagnostics.append(
                Diagnostic(station.station_id, "all", None, None, "GPS timing unavailable", "No supported checksum-valid RMC offset segment.", "Repeated valid RMC date/time evidence is required for clock correction.")
            )
        return flags, diagnostics

    corrections: list[tuple[int, int, OffsetSegment]] = []
    first = segments[0]
    if abs(first.offset_seconds) >= config.gps_offset_change_seconds:
        corrections.append((0, -first.offset_seconds, first))
    for previous, current in zip(segments, segments[1:]):
        if abs(current.offset_seconds - previous.offset_seconds) < config.gps_offset_change_seconds:
            continue
        boundary = _find_clock_boundary(
            station.records,
            previous.offset_seconds,
            current.offset_seconds,
            station.interval_minutes * 60,
            config,
        )
        if boundary is None:
            diagnostics.append(
                Diagnostic(
                    station.station_id,
                    "all",
                    current.first_gps_time,
                    current.last_gps_time,
                    "GPS clock-offset change",
                    f"Offset changed from {previous.offset_seconds}s to {current.offset_seconds}s using {current.observations} valid RMC observations.",
                    "No matching source-order weather discontinuity established the first affected weather row.",
                )
            )
            continue
        corrections.append((boundary, -current.offset_seconds, current))

    if not corrections:
        return flags, diagnostics
    corrections.sort(key=lambda item: item[0])
    corrected = list(station.records)
    for position, (start_index, correction_seconds, segment) in enumerate(corrections):
        end_index = corrections[position + 1][0] if position + 1 < len(corrections) else len(corrected)
        evidence = (
            f"{segment.observations} checksum-valid RMC observations show logger-minus-GPS "
            f"{segment.offset_seconds}s; source rows {start_index + 2}-{end_index + 1}."
        )
        for index in range(start_index, end_index):
            record = corrected[index]
            interpreted = record.logger_time + timedelta(seconds=correction_seconds) if record.logger_time else None
            corrected[index] = replace(
                record,
                interpreted_utc=interpreted,
                correction_seconds=correction_seconds,
                correction_evidence=evidence,
            )
        affected = [record for record in corrected[start_index:end_index] if record.interpreted_utc]
        if affected:
            sign = "+" if correction_seconds >= 0 else "-"
            flags.append(
                Flag(
                    station.station_id,
                    "all",
                    affected[0].interpreted_utc,  # type: ignore[arg-type]
                    affected[-1].interpreted_utc,  # type: ignore[arg-type]
                    "logger clock offset",
                    "correct",
                    f"Apply {sign}{abs(correction_seconds) // 3600:02d}:{(abs(correction_seconds) % 3600) // 60:02d} to source rows {affected[0].source_row}-{affected[-1].source_row}; {segment.observations} valid RMC offsets align corrected logger time to GPS.",
                )
            )
    station.records = corrected
    return flags, diagnostics


def _group_consecutive(indices: Sequence[int], max_gap: int = 1) -> list[list[int]]:
    if not indices:
        return []
    groups = [[indices[0]]]
    for index in indices[1:]:
        if index - groups[-1][-1] <= max_gap:
            groups[-1].append(index)
        else:
            groups.append([index])
    return groups


def _timeline_checks(station: StationData, config: Thresholds) -> tuple[list[Flag], list[Diagnostic], set[int]]:
    flags: list[Flag] = []
    diagnostics: list[Diagnostic] = []
    duplicate_indices: set[int] = set()
    first_signature: dict[tuple[str, ...], int] = {}
    duplicate_to_original: dict[int, int] = {}
    for index, record in enumerate(station.records):
        signature = record.signature()
        if signature in first_signature:
            duplicate_indices.add(index)
            duplicate_to_original[index] = first_signature[signature]
        else:
            first_signature[signature] = index
    for group in _group_consecutive(sorted(duplicate_indices)):
        records = [station.records[index] for index in group if station.records[index].interpreted_utc]
        if not records:
            continue
        originals = [station.records[duplicate_to_original[index]].source_row for index in group]
        flags.append(
            Flag(
                station.station_id,
                "all",
                records[0].interpreted_utc,  # type: ignore[arg-type]
                records[-1].interpreted_utc,  # type: ignore[arg-type]
                "exact replay copies",
                "exclude",
                f"Exclude only replay source rows {records[0].source_row}-{records[-1].source_row}; retain original rows {min(originals)}-{max(originals)} with identical raw timestamps and readings.",
            )
        )

    by_time: dict[datetime, list[int]] = defaultdict(list)
    for index, record in enumerate(station.records):
        if index not in duplicate_indices and record.interpreted_utc is not None:
            by_time[record.interpreted_utc].append(index)
    conflicted_indices: set[int] = set()
    for timestamp, indices in sorted(by_time.items()):
        signatures = {station.records[index].signature()[1:] for index in indices}
        if len(signatures) > 1:
            conflicted_indices.update(indices)
            rows = [station.records[index].source_row for index in indices]
            flags.append(
                Flag(station.station_id, "all", timestamp, timestamp, "conflicting observations", "exclude", f"Different readings share reconstructed UTC at source rows {min(rows)}-{max(rows)}; no version is preferred.")
            )

    excluded = duplicate_indices | conflicted_indices
    usable = [record for index, record in enumerate(station.records) if index not in excluded and record.interpreted_utc]
    usable.sort(key=lambda record: (record.interpreted_utc, record.source_row))
    interval = timedelta(minutes=station.interval_minutes)
    for previous, current in zip(usable, usable[1:]):
        assert previous.interpreted_utc and current.interpreted_utc
        delta = current.interpreted_utc - previous.interpreted_utc
        missing = int(delta / interval) - 1
        if missing >= config.gap_min_missing_intervals:
            start = previous.interpreted_utc + interval
            end = current.interpreted_utc - interval
            flags.append(
                Flag(station.station_id, "all", start, end, "coverage gap", "exclude", f"{missing} nominal {station.interval_minutes}-minute observations are absent between source rows {previous.source_row} and {current.source_row}; no interpolation is applied.")
            )
    return flags, diagnostics, excluded


def _coverage(station: StationData, excluded: set[int] | None = None) -> tuple[datetime, datetime] | None:
    excluded = excluded or set()
    times = [record.interpreted_utc for index, record in enumerate(station.records) if index not in excluded and record.interpreted_utc]
    return (min(times), max(times)) if times else None


def _gps_checks(station: StationData, config: Thresholds) -> tuple[list[Flag], list[Diagnostic], dict[str, Any]]:
    flags: list[Flag] = []
    diagnostics: list[Diagnostic] = []
    positions = [observation for observation in station.gps if observation.trustworthy_position]
    invalid_checksums = sum(not observation.checksum_valid for observation in station.gps)
    void_rmc = sum(observation.sentence_type == "RMC" and observation.rmc_status == "V" for observation in station.gps)
    if invalid_checksums or void_rmc:
        diagnostics.append(
            Diagnostic(station.station_id, "metadata", None, None, "partial GPS evidence", f"{invalid_checksums} checksum-invalid sentences and {void_rmc} void RMC positions were ignored.", "This does not invalidate weather measurements; only valid messages may support timing/location conclusions.")
        )
    summary: dict[str, Any] = {"valid_positions": len(positions), "median_altitude_m": None, "median_distance_m": None}
    altitudes = [observation.altitude_m for observation in positions if observation.altitude_m is not None]
    if altitudes:
        summary["median_altitude_m"] = statistics.median(altitudes)
    try:
        metadata_lat = float(station.metadata["lat"])
        metadata_lon = float(station.metadata["lon"])
    except (KeyError, TypeError, ValueError):
        metadata_lat = metadata_lon = None
    distances = []
    if metadata_lat is not None and metadata_lon is not None:
        distances = [_haversine_m(metadata_lat, metadata_lon, observation.latitude, observation.longitude) for observation in positions if observation.latitude is not None and observation.longitude is not None]
    if distances:
        summary["median_distance_m"] = statistics.median(distances)
    if len(distances) >= config.gps_min_position_observations and summary["median_distance_m"] >= config.gps_location_disagreement_m:
        coverage = _coverage(station)
        if coverage:
            flags.append(
                Flag(station.station_id, "metadata", coverage[0], coverage[1], "GPS/location disagreement", "exclude", f"{len(distances)} trustworthy GPS positions are a median {summary['median_distance_m'] / 1000:.2f} km from station metadata; which source is wrong is unresolved.")
            )
    return flags, diagnostics, summary


def _physical_violation(channel: str, value: float | None) -> bool:
    if value is None:
        return False
    if channel == "rh_pct":
        return not 0 <= value <= 100
    if channel == "wind_kmh":
        return value < 0
    if channel == "wind_dir_deg":
        return not 0 <= value <= 360
    if channel in {"rain_mm", "ghi_wm2"}:
        return value < 0
    return False


def _parse_and_missing_checks(station: StationData, excluded: set[int]) -> tuple[list[Flag], list[Diagnostic]]:
    flags: list[Flag] = []
    diagnostics: list[Diagnostic] = []
    invalid_timestamp_rows = [record.source_row for record in station.records if record.logger_time is None]
    if invalid_timestamp_rows:
        diagnostics.append(
            Diagnostic(
                station.station_id,
                "all",
                None,
                None,
                "unparseable weather timestamp",
                f"Source rows {min(invalid_timestamp_rows)}-{max(invalid_timestamp_rows)} include {len(invalid_timestamp_rows)} unparseable timestamps.",
                "No UTC interval can be emitted until the raw timestamps are interpreted.",
            )
        )
    for channel in CHANNELS:
        missing = [
            index
            for index, record in enumerate(station.records)
            if index not in excluded and record.interpreted_utc is not None and record.value(channel) is None
        ]
        for group in _group_consecutive(missing):
            first, last = station.records[group[0]], station.records[group[-1]]
            assert first.interpreted_utc and last.interpreted_utc
            flags.append(
                Flag(
                    station.station_id,
                    channel,
                    first.interpreted_utc,
                    last.interpreted_utc,
                    "missing/non-numeric readings",
                    "exclude",
                    f"{len(group)} consecutive values cannot be parsed at source rows {first.source_row}-{last.source_row} and no value is imputed.",
                )
            )
    return flags, diagnostics


def _domain_checks(station: StationData, excluded: set[int], config: Thresholds) -> list[Flag]:
    flags = []
    for channel in CHANNELS:
        violations = [index for index, record in enumerate(station.records) if index not in excluded and record.interpreted_utc and _physical_violation(channel, record.value(channel))]
        for candidate in _group_consecutive(violations, config.domain_cluster_gap_intervals + 1):
            span = candidate[-1] - candidate[0] + 1
            if len(candidate) / span < config.domain_cluster_min_fraction:
                groups = _group_consecutive(candidate)
            else:
                groups = [candidate]
            for group in groups:
                first, last = station.records[group[0]], station.records[group[-1]]
                assert first.interpreted_utc and last.interpreted_utc
                values = [station.records[index].value(channel) for index in group]
                span = group[-1] - group[0] + 1
                flags.append(
                    Flag(station.station_id, channel, first.interpreted_utc, last.interpreted_utc, "physical-domain violation", "exclude", f"{len(group)} of {span} readings violate the documented {channel} domain within source rows {first.source_row}-{last.source_row}; observed violating range {min(values):g}-{max(values):g}.")  # type: ignore[type-var]
                )
    return flags


def _persistence_checks(station: StationData, excluded: set[int], config: Thresholds) -> list[Flag]:
    flags = []
    interval_hours = station.interval_minutes / 60.0
    rules = {
        "temp_c": config.temp_flatline_min_hours,
        "pressure_hpa": config.pressure_flatline_min_hours,
        "wind_dir_deg": config.wind_direction_flatline_min_hours,
    }
    for channel, minimum_hours in rules.items():
        minimum_rows = max(2, math.ceil(minimum_hours / interval_hours))
        start = 0
        while start < len(station.records):
            if start in excluded or station.records[start].interpreted_utc is None:
                start += 1
                continue
            value = station.records[start].value(channel)
            end = start + 1
            while end < len(station.records) and end not in excluded and station.records[end].value(channel) == value:
                end += 1
            length = end - start
            active_direction = True
            if channel == "wind_dir_deg":
                speeds = [station.records[index].value("wind_kmh") or 0.0 for index in range(start, end)]
                active_direction = bool(speeds) and statistics.median(speeds) >= config.wind_active_min_kmh
            if value is not None and length >= minimum_rows and active_direction:
                first, last = station.records[start], station.records[end - 1]
                assert first.interpreted_utc and last.interpreted_utc
                flags.append(
                    Flag(station.station_id, channel, first.interpreted_utc, last.interpreted_utc, "implausible persistence", "exclude", f"Value {value:g} repeats for {length} consecutive source rows {first.source_row}-{last.source_row} ({length * interval_hours:.1f} hours) while the logger continues recording.")
                )
            start = end
    return flags


def _temperature_spikes(station: StationData, excluded: set[int], config: Thresholds) -> list[Flag]:
    flags = []
    values = [record.value("temp_c") for record in station.records]
    window = config.spike_window_intervals
    for index in range(window, len(values) - window):
        if index in excluded or values[index] is None or station.records[index].interpreted_utc is None:
            continue
        neighbours = [value for offset, value in enumerate(values[index - window:index] + values[index + 1:index + window + 1]) if value is not None]
        if len(neighbours) < window:
            continue
        center = statistics.median(neighbours)
        threshold = max(config.temp_spike_min_abs_c, config.temp_spike_mad_multiplier * max(_mad(neighbours), 0.5))
        previous, following = values[index - 1], values[index + 1]
        if previous is None or following is None:
            continue
        if abs(values[index] - center) >= threshold and abs(previous - following) <= config.temp_spike_return_tolerance_c:
            record = station.records[index]
            flags.append(
                Flag(station.station_id, "temp_c", record.interpreted_utc, record.interpreted_utc, "isolated temperature spike", "exclude", f"Source row {record.source_row} is {values[index]:g} C versus surrounding median {center:.1f} C and returns on the next interval.")
            )
    return flags


def _is_unreliable(flags: Sequence[Flag], station_id: str, channel: str, timestamp: datetime) -> bool:
    return any(
        flag.station_id == station_id
        and flag.action == "exclude"
        and flag.channel in {"all", channel}
        and flag.start_utc <= timestamp <= flag.end_utc
        for flag in flags
    )


def _unique_series(station: StationData, excluded_indices: set[int]) -> dict[datetime, WeatherRecord]:
    groups: dict[datetime, list[WeatherRecord]] = defaultdict(list)
    for index, record in enumerate(station.records):
        if index not in excluded_indices and record.interpreted_utc is not None:
            groups[record.interpreted_utc].append(record)
    result = {}
    for timestamp, records in groups.items():
        if len({record.signature()[1:] for record in records}) == 1:
            result[timestamp] = records[0]
    return result


def _metadata_number(station: StationData, key: str) -> float | None:
    try:
        return float(station.metadata[key])
    except (KeyError, TypeError, ValueError):
        return None


def _peer_ids(
    station: StationData,
    stations: Sequence[StationData],
    channel: str,
    series: dict[str, dict[datetime, WeatherRecord]],
    config: Thresholds,
) -> list[str]:
    lat, lon, elevation = (_metadata_number(station, key) for key in ("lat", "lon", "elevation_m"))
    if lat is None or lon is None or elevation is None:
        return []
    maximum_elevation = config.pressure_peer_max_elevation_difference_m if channel == "pressure_hpa" else config.peer_max_elevation_difference_m
    candidates = []
    for peer in stations:
        if peer.station_id == station.station_id:
            continue
        peer_lat, peer_lon, peer_elevation = (_metadata_number(peer, key) for key in ("lat", "lon", "elevation_m"))
        if peer_lat is None or peer_lon is None or peer_elevation is None:
            continue
        distance = _haversine_m(lat, lon, peer_lat, peer_lon) / 1000.0
        elevation_difference = abs(elevation - peer_elevation)
        if distance > config.peer_max_distance_km or elevation_difference > maximum_elevation:
            continue
        overlap = set(series.get(station.station_id, {})) & set(series.get(peer.station_id, {}))
        usable_overlap = sum(
            series[station.station_id][timestamp].value(channel) is not None
            and series[peer.station_id][timestamp].value(channel) is not None
            for timestamp in overlap
        )
        if usable_overlap >= config.peer_min_overlap:
            candidates.append((distance, elevation_difference, peer.station_id))
    return [station_id for _, _, station_id in sorted(candidates)]


def _peer_value(
    timestamp: datetime,
    channel: str,
    peer_ids: Sequence[str],
    series: dict[str, dict[datetime, WeatherRecord]],
    unreliable_flags: Sequence[Flag],
    minimum_peers: int,
) -> float | None:
    values = []
    for peer_id in peer_ids:
        record = series.get(peer_id, {}).get(timestamp)
        if record is None or _is_unreliable(unreliable_flags, peer_id, channel, timestamp):
            continue
        value = record.value(channel)
        if value is not None:
            values.append(value)
    return statistics.median(values) if len(values) >= minimum_peers else None


def _nearest_note(notes: Sequence[dict[str, str]], station_id: str, timestamp: datetime) -> str:
    nearest: tuple[int, dict[str, str]] | None = None
    for note in notes:
        if note.get("station_id") != station_id:
            continue
        try:
            note_date = datetime.strptime(note["date_raw"], "%Y-%m-%d").date()
        except (KeyError, ValueError):
            continue
        distance = abs((timestamp.date() - note_date).days)
        if distance <= 1 and (nearest is None or distance < nearest[0]):
            nearest = (distance, note)
    if nearest is None:
        return ""
    sanitized = re.sub(r"[.!?]+", ",", nearest[1]["note"]).strip(" ,")
    return f"; maintenance note dated {nearest[1]['date_raw']} says '{sanitized}' (timezone unspecified)"


def _pressure_shift_checks(
    station: StationData,
    stations: Sequence[StationData],
    series: dict[str, dict[datetime, WeatherRecord]],
    unreliable_flags: Sequence[Flag],
    notes: Sequence[dict[str, str]],
    config: Thresholds,
) -> tuple[list[Flag], list[Diagnostic]]:
    flags: list[Flag] = []
    diagnostics: list[Diagnostic] = []
    peers = _peer_ids(station, stations, "pressure_hpa", series, config)
    if len(peers) < config.peer_min_count_per_timestamp:
        diagnostics.append(Diagnostic(station.station_id, "pressure_hpa", None, None, "pressure shift not assessed", f"Only {len(peers)} metadata-eligible peers.", f"At least {config.peer_min_count_per_timestamp} trustworthy peers are required."))
        return flags, diagnostics
    records = sorted(series[station.station_id].values(), key=lambda record: record.interpreted_utc or datetime.min.replace(tzinfo=timezone.utc))
    candidates = []
    for index in range(1, len(records)):
        before, after = records[index - 1], records[index]
        if before.interpreted_utc is None or after.interpreted_utc is None:
            continue
        first, second = before.value("pressure_hpa"), after.value("pressure_hpa")
        if first is None or second is None or abs(second - first) < config.pressure_raw_step_min_hpa:
            continue
        candidates.append((abs(second - first), index, after.interpreted_utc))
    if not candidates:
        return flags, diagnostics
    window = timedelta(hours=config.change_window_hours)
    for _, _, boundary in sorted(candidates, reverse=True):
        residual_before: list[float] = []
        residual_after: list[float] = []
        for record in records:
            timestamp = record.interpreted_utc
            value = record.value("pressure_hpa")
            if timestamp is None or value is None or _is_unreliable(unreliable_flags, station.station_id, "pressure_hpa", timestamp):
                continue
            peer = _peer_value(timestamp, "pressure_hpa", peers, series, unreliable_flags, config.peer_min_count_per_timestamp)
            if peer is None:
                continue
            if boundary - window <= timestamp < boundary:
                residual_before.append(value - peer)
            elif boundary <= timestamp < boundary + window:
                residual_after.append(value - peer)
        if len(residual_before) < config.change_min_observations_each_side or len(residual_after) < config.change_min_observations_each_side:
            diagnostics.append(Diagnostic(station.station_id, "pressure_hpa", boundary, boundary, "possible pressure shift", f"Abrupt station step at {boundary.strftime(WEATHER_TIMESTAMP)} but peer residual windows contain {len(residual_before)}/{len(residual_after)} observations.", "More trustworthy overlapping peer coverage is required."))
            continue
        shift = statistics.median(residual_after) - statistics.median(residual_before)
        if abs(shift) < config.pressure_residual_shift_min_hpa:
            continue
        coverage = _coverage(station)
        if not coverage:
            continue
        note = _nearest_note(notes, station.station_id, boundary)
        flags.append(Flag(station.station_id, "pressure_hpa", boundary, coverage[1], "sustained pressure shift", "exclude", f"Station-minus-peer median changed by {shift:+.1f} hPa across {len(residual_before)}/{len(residual_after)} observations around an abrupt step and calibration is unknown{note}."))
        break
    return flags, diagnostics


def _windowed_change_candidates(timestamps: Sequence[datetime], window: timedelta) -> list[datetime]:
    if not timestamps:
        return []
    # Evaluate every six hours to avoid selecting a boundary from minute noise.
    candidates = []
    last_bucket = None
    for timestamp in sorted(timestamps):
        bucket = int(timestamp.timestamp()) // (6 * 3600)
        if bucket != last_bucket and timestamp - timestamps[0] >= window and timestamps[-1] - timestamp >= window:
            candidates.append(timestamp)
            last_bucket = bucket
    return candidates


def _wind_scale_checks(
    station: StationData,
    stations: Sequence[StationData],
    series: dict[str, dict[datetime, WeatherRecord]],
    unreliable_flags: Sequence[Flag],
    notes: Sequence[dict[str, str]],
    config: Thresholds,
) -> tuple[list[Flag], list[Diagnostic]]:
    flags: list[Flag] = []
    diagnostics: list[Diagnostic] = []
    peers = _peer_ids(station, stations, "wind_kmh", series, config)
    ratios: list[tuple[datetime, float]] = []
    for timestamp, record in sorted(series[station.station_id].items()):
        value = record.value("wind_kmh")
        peer = _peer_value(timestamp, "wind_kmh", peers, series, unreliable_flags, config.peer_min_count_per_timestamp)
        if value is None or peer is None or peer < config.wind_ratio_floor_kmh or value < 0:
            continue
        if _is_unreliable(unreliable_flags, station.station_id, "wind_kmh", timestamp):
            continue
        ratios.append((timestamp, (value + config.wind_ratio_floor_kmh) / (peer + config.wind_ratio_floor_kmh)))
    if len(ratios) < config.change_min_observations_each_side * 2:
        diagnostics.append(Diagnostic(station.station_id, "wind_kmh", None, None, "wind scale not assessed", f"Only {len(ratios)} stable-ratio observations from {len(peers)} eligible peers.", "More non-calm overlap with at least two trustworthy peers is required."))
        return flags, diagnostics
    window = timedelta(hours=config.change_window_hours)
    best = None
    timestamps = [item[0] for item in ratios]
    for boundary in _windowed_change_candidates(timestamps, window):
        before = [math.log(value) for timestamp, value in ratios if boundary - window <= timestamp < boundary]
        after = [math.log(value) for timestamp, value in ratios if boundary <= timestamp < boundary + window]
        if len(before) < config.change_min_observations_each_side or len(after) < config.change_min_observations_each_side:
            continue
        factor = math.exp(statistics.median(after) - statistics.median(before))
        magnitude = max(factor, 1.0 / factor)
        if best is None or magnitude > best[0]:
            best = (magnitude, factor, boundary, len(before), len(after))
    if best and best[0] >= config.wind_scale_factor_min:
        coverage = _coverage(station)
        assert coverage
        _, factor, boundary, before_n, after_n = best
        note = _nearest_note(notes, station.station_id, boundary)
        flags.append(Flag(station.station_id, "wind_kmh", boundary, coverage[1], "persistent wind-scale change", "exclude", f"Station/peer wind relationship changed by factor {factor:.2f} across {before_n}/{after_n} non-calm observations, the six-hour scan boundary is approximate, and no calibration multiplier is inferred{note}."))
    return flags, diagnostics


def _daylight_temperature_checks(
    station: StationData,
    stations: Sequence[StationData],
    series: dict[str, dict[datetime, WeatherRecord]],
    unreliable_flags: Sequence[Flag],
    notes: Sequence[dict[str, str]],
    config: Thresholds,
) -> tuple[list[Flag], list[Diagnostic]]:
    flags: list[Flag] = []
    diagnostics: list[Diagnostic] = []
    peers = _peer_ids(station, stations, "temp_c", series, config)
    observations: list[tuple[datetime, str, float]] = []
    for timestamp, record in sorted(series[station.station_id].items()):
        if _is_unreliable(unreliable_flags, station.station_id, "temp_c", timestamp):
            continue
        temp, ghi = record.value("temp_c"), record.value("ghi_wm2")
        peer_temp = _peer_value(timestamp, "temp_c", peers, series, unreliable_flags, config.peer_min_count_per_timestamp)
        if temp is None or ghi is None or peer_temp is None:
            continue
        phase = "day" if ghi >= config.daylight_ghi_min_wm2 else "night" if ghi <= config.night_ghi_max_wm2 else "transition"
        if phase != "transition":
            observations.append((timestamp, phase, temp - peer_temp))
    window = timedelta(hours=config.change_window_hours)
    best = None
    timestamps = [item[0] for item in observations]
    for boundary in _windowed_change_candidates(timestamps, window):
        values: dict[tuple[str, str], list[float]] = defaultdict(list)
        for timestamp, phase, residual in observations:
            side = "before" if boundary - window <= timestamp < boundary else "after" if boundary <= timestamp < boundary + window else None
            if side:
                values[(side, phase)].append(residual)
        if min((len(values[key]) for key in (("before", "day"), ("after", "day"), ("before", "night"), ("after", "night"))), default=0) < 24:
            continue
        day_shift = statistics.median(values[("after", "day")]) - statistics.median(values[("before", "day")])
        night_shift = statistics.median(values[("after", "night")]) - statistics.median(values[("before", "night")])
        score = abs(day_shift) - abs(night_shift)
        if best is None or score > best[0]:
            best = (score, boundary, day_shift, night_shift)
    if best and abs(best[2]) >= config.daylight_temp_shift_min_c and abs(best[3]) <= config.daylight_night_shift_max_c:
        coverage = _coverage(station)
        assert coverage
        flags.append(Flag(station.station_id, "temp_c", best[1], coverage[1], "daylight-dependent temperature shift", "exclude", f"Daylight station-minus-peer median changed {best[2]:+.1f} C while night changed {best[3]:+.1f} C across matched observations; radiation-related bias is supported."))
    return flags, diagnostics


def _rain_checks(
    station: StationData,
    stations: Sequence[StationData],
    series: dict[str, dict[datetime, WeatherRecord]],
    unreliable_flags: Sequence[Flag],
    notes: Sequence[dict[str, str]],
    config: Thresholds,
) -> tuple[list[Flag], list[Diagnostic]]:
    flags: list[Flag] = []
    diagnostics: list[Diagnostic] = []
    peers = _peer_ids(station, stations, "rain_mm", series, config)
    records = sorted(series[station.station_id].values(), key=lambda record: record.interpreted_utc or datetime.min.replace(tzinfo=timezone.utc))
    minimum_rows = math.ceil(config.rain_zero_min_hours * 60 / station.interval_minutes)
    start = 0
    while start < len(records):
        if records[start].value("rain_mm") != 0.0:
            start += 1
            continue
        end = start + 1
        while end < len(records) and records[end].value("rain_mm") == 0.0 and records[end].interpreted_utc - records[end - 1].interpreted_utc == timedelta(minutes=station.interval_minutes):  # type: ignore[operator]
            end += 1
        if end - start >= minimum_rows:
            regional_wet = 0
            for record in records[start:end]:
                timestamp = record.interpreted_utc
                if timestamp is None:
                    continue
                wet_peers = 0
                for peer_id in peers:
                    peer_record = series.get(peer_id, {}).get(timestamp)
                    if peer_record and not _is_unreliable(unreliable_flags, peer_id, "rain_mm", timestamp) and (peer_record.value("rain_mm") or 0.0) > 0:
                        wet_peers += 1
                if wet_peers >= config.rain_peer_wet_min_stations:
                    regional_wet += 1
            releases = []
            for offset in range(end, min(len(records), end + config.rain_release_max_intervals_after)):
                record = records[offset]
                timestamp = record.interpreted_utc
                value = record.value("rain_mm")
                if timestamp is None or value is None or value < config.rain_release_min_mm:
                    continue
                peer_values = [series[peer_id][timestamp].value("rain_mm") for peer_id in peers if timestamp in series.get(peer_id, {}) and not _is_unreliable(unreliable_flags, peer_id, "rain_mm", timestamp)]
                peer_values = [value for value in peer_values if value is not None]
                if peer_values and statistics.median(peer_values) <= config.rain_release_peer_median_max_mm:
                    releases.append(record)
            first, last = records[start], records[end - 1]
            if regional_wet >= config.rain_peer_wet_min_intervals and releases:
                last = releases[-1]
                note = _nearest_note(notes, station.station_id, last.interpreted_utc)  # type: ignore[arg-type]
                flags.append(Flag(station.station_id, "rain_mm", first.interpreted_utc, last.interpreted_utc, "blocked/released rain gauge", "exclude", f"Zero rain persisted for {end - start} rows while >=2 peers were wet in {regional_wet} intervals, followed by {len(releases)} station-only readings >= {config.rain_release_min_mm:g} mm, and no redistribution is attempted{note}."))  # type: ignore[arg-type]
            elif regional_wet >= config.rain_peer_wet_min_intervals:
                diagnostics.append(Diagnostic(station.station_id, "rain_mm", first.interpreted_utc, last.interpreted_utc, "possible rain under-catch", f"Zero run spans {end - start} rows while regional peers were wet in {regional_wet} intervals.", "No independent release/service evidence makes blockage distinguishable from local rainfall differences."))
        start = end
    return flags, diagnostics


def _high_elevation_keep(station: StationData, gps_summary: dict[str, Any], unreliable_flags: Sequence[Flag], config: Thresholds) -> list[Flag]:
    elevation = _metadata_number(station, "elevation_m")
    pressure_values = [record.value("pressure_hpa") for record in station.records if record.value("pressure_hpa") is not None and record.interpreted_utc]
    gps_altitude = gps_summary.get("median_altitude_m")
    coverage = _coverage(station)
    if elevation is None or not pressure_values or gps_altitude is None or coverage is None:
        return []
    if any(flag.station_id == station.station_id and flag.channel in {"all", "pressure_hpa", "metadata"} and flag.action == "exclude" for flag in unreliable_flags):
        return []
    median_pressure = statistics.median(pressure_values)
    if elevation >= config.high_elevation_min_m and median_pressure <= config.high_elevation_pressure_max_hpa and abs(gps_altitude - elevation) <= config.gps_altitude_agreement_m:
        return [Flag(station.station_id, "pressure_hpa", coverage[0], coverage[1], "low high-elevation pressure", "keep", f"Median station pressure {median_pressure:.1f} hPa is supported by {elevation:.0f} m metadata elevation and GPS median altitude {gps_altitude:.0f} m; it is not sea-level pressure.")]
    return []


def _read_notes(pack: Path) -> list[dict[str, str]]:
    path = pack / "maintenance_log.md"
    if not path.exists():
        return []
    pattern = re.compile(r"^(\d{4}-\d{2}-\d{2})\s+(\S+)\s+(.*)$")
    notes = []
    for source_row, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        match = pattern.match(line)
        if match:
            notes.append({"source_row": str(source_row), "date_raw": match.group(1), "station_id": match.group(2), "note": match.group(3)})
    return notes


def _deduplicate_flags(flags: Iterable[Flag]) -> list[Flag]:
    seen = set()
    result = []
    for flag in flags:
        key = (flag.station_id, flag.channel, flag.start_utc, flag.end_utc, flag.issue, flag.action, flag.note)
        if key not in seen:
            seen.add(key)
            result.append(flag)
    return sorted(result, key=lambda flag: (flag.station_id, flag.start_utc, flag.channel, flag.issue, flag.action, flag.end_utc))


def _write_rows(path: Path, columns: Sequence[str], rows: Iterable[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(columns), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def run_checker(pack_dir: Path | str, output_dir: Path | str = ".", config: Thresholds = DEFAULT_THRESHOLDS) -> CheckResult:
    pack = Path(pack_dir).resolve()
    output = Path(output_dir).resolve()
    stations, _ = _load_pack(pack, config)
    notes = _read_notes(pack)
    flags: list[Flag] = []
    diagnostics: list[Diagnostic] = []
    excluded_indices: dict[str, set[int]] = {}
    gps_summaries: dict[str, dict[str, Any]] = {}

    # Timeline corrections precede alignment and coverage checks.
    for station in stations:
        new_flags, new_diagnostics = _apply_clock_evidence(station, config)
        flags.extend(new_flags)
        diagnostics.extend(new_diagnostics)
        new_flags, new_diagnostics, excluded = _timeline_checks(station, config)
        flags.extend(new_flags)
        diagnostics.extend(new_diagnostics)
        excluded_indices[station.station_id] = excluded
        new_flags, new_diagnostics, summary = _gps_checks(station, config)
        flags.extend(new_flags)
        diagnostics.extend(new_diagnostics)
        gps_summaries[station.station_id] = summary
        new_flags, new_diagnostics = _parse_and_missing_checks(station, excluded)
        flags.extend(new_flags)
        diagnostics.extend(new_diagnostics)
        flags.extend(_domain_checks(station, excluded, config))
        flags.extend(_persistence_checks(station, excluded, config))
        flags.extend(_temperature_spikes(station, excluded, config))

    base_flags = _deduplicate_flags(flags)
    series = {station.station_id: _unique_series(station, excluded_indices[station.station_id]) for station in stations}

    # Peer-based checks consume corrected, unique records and avoid already
    # excluded station/channel intervals as references.
    for station in stations:
        for detector in (_pressure_shift_checks, _wind_scale_checks, _daylight_temperature_checks, _rain_checks):
            new_flags, new_diagnostics = detector(station, stations, series, base_flags + flags, notes, config)
            flags.extend(new_flags)
            diagnostics.extend(new_diagnostics)
        flags.extend(_high_elevation_keep(station, gps_summaries[station.station_id], flags, config))

    final_flags = _deduplicate_flags(flags)
    final_diagnostics = sorted(diagnostics, key=lambda item: (item.station_id, item.channel, item.start_utc or datetime.min.replace(tzinfo=timezone.utc), item.candidate))
    output.mkdir(parents=True, exist_ok=True)
    _write_rows(output / "flags.csv", FLAG_COLUMNS, (flag.as_row() for flag in final_flags))
    _write_rows(output / "diagnostics.csv", DIAGNOSTIC_COLUMNS, (item.as_row() for item in final_diagnostics))
    return CheckResult(tuple(final_flags), tuple(final_diagnostics), tuple(stations))
