from __future__ import annotations

import csv
import hashlib
import math
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

from quality_checker import run_checker
from quality_checker.core import FLAG_COLUMNS, CHANNELS, input_hashes, nmea_coordinate
from quality_checker.config import DEFAULT_THRESHOLDS


ROOT = Path(__file__).resolve().parents[1]
UTC = timezone.utc


def workspace_tempdir() -> tempfile.TemporaryDirectory[str]:
    parent = ROOT / "tmp" / "tests"
    parent.mkdir(parents=True, exist_ok=True)
    return tempfile.TemporaryDirectory(dir=parent)


def checksum(body: str) -> str:
    value = 0
    for character in body:
        value ^= ord(character)
    return f"${body}*{value:02X}"


def nmea_coord(value: float, latitude: bool) -> tuple[str, str]:
    hemisphere = ("N" if value >= 0 else "S") if latitude else ("E" if value >= 0 else "W")
    absolute = abs(value)
    degrees = int(absolute)
    minutes = (absolute - degrees) * 60
    width = 2 if latitude else 3
    return f"{degrees:0{width}d}{minutes:07.4f}", hemisphere


def rmc(gps_time: datetime, lat: float = 40.0, lon: float = -105.0, status: str = "A", corrupt: bool = False) -> str:
    lat_value, lat_hemi = nmea_coord(lat, True)
    lon_value, lon_hemi = nmea_coord(lon, False)
    body = f"GPRMC,{gps_time:%H%M%S}.00,{status},{lat_value},{lat_hemi},{lon_value},{lon_hemi},0.0,0.0,{gps_time:%d%m%y},,,A"
    sentence = checksum(body)
    return sentence[:-2] + "00" if corrupt else sentence


def gga(gps_time: datetime, lat: float = 40.0, lon: float = -105.0, fix: int = 1, altitude: float = 1600.0) -> str:
    lat_value, lat_hemi = nmea_coord(lat, True)
    lon_value, lon_hemi = nmea_coord(lon, False)
    return checksum(f"GPGGA,{gps_time:%H%M%S}.00,{lat_value},{lat_hemi},{lon_value},{lon_hemi},{fix},8,1.0,{altitude:.1f},M,-17.0,M,,")


def weather_row(timestamp: datetime | str, **overrides: float) -> dict[str, str]:
    values = {
        "temp_c": 12.0,
        "rh_pct": 50.0,
        "pressure_hpa": 840.0,
        "wind_kmh": 10.0,
        "wind_dir_deg": 350.0,
        "rain_mm": 0.0,
        "ghi_wm2": 0.0,
    }
    values.update(overrides)
    raw_time = timestamp if isinstance(timestamp, str) else timestamp.strftime("%Y-%m-%d %H:%M")
    return {"timestamp_utc": raw_time, **{key: f"{value:g}" for key, value in values.items()}}


def regular_rows(start: datetime, count: int, mutate=None) -> list[dict[str, str]]:
    rows = []
    for index in range(count):
        timestamp = start + timedelta(minutes=10 * index)
        hour = timestamp.hour + timestamp.minute / 60
        base = {
            "temp_c": 8 + 5 * math.sin(2 * math.pi * (hour - 6) / 24),
            "rh_pct": 55 - 10 * math.sin(2 * math.pi * (hour - 6) / 24),
            "pressure_hpa": 840 + 1.5 * math.sin(index / 80),
            "wind_kmh": 9 + 3 * math.sin(index / 11),
            "wind_dir_deg": (220 + index * 3) % 360,
            "rain_mm": 0.0,
            "ghi_wm2": max(0.0, 700 * math.sin(math.pi * (hour - 6) / 12)) if 6 <= hour <= 18 else 0.0,
        }
        if mutate:
            base.update(mutate(index, timestamp, dict(base)) or {})
        rows.append(weather_row(timestamp, **base))
    return rows


def write_pack(
    root: Path,
    weather: dict[str, list[dict[str, str]]],
    *,
    metadata: dict[str, dict[str, str]] | None = None,
    gps: dict[str, list[str]] | None = None,
    order: list[str] | None = None,
) -> Path:
    pack = root / "pack"
    (pack / "data").mkdir(parents=True)
    (pack / "gps").mkdir()
    (pack / "README.md").write_text("synthetic pack\n", encoding="utf-8")
    (pack / "maintenance_log.md").write_text("# synthetic\n", encoding="utf-8")
    ids = order or list(weather)
    metadata = metadata or {}
    with (pack / "stations.csv").open("w", encoding="utf-8", newline="") as handle:
        fields = ["station_id", "name", "lat", "lon", "elevation_m", "installed", "logger_interval_min"]
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for index, station_id in enumerate(ids):
            row = {
                "station_id": station_id,
                "name": station_id,
                "lat": str(40.0 + index * 0.02),
                "lon": str(-105.0 + index * 0.02),
                "elevation_m": "1600",
                "installed": "2024-01-01",
                "logger_interval_min": "10",
            }
            row.update(metadata.get(station_id, {}))
            writer.writerow(row)
    for station_id, rows in weather.items():
        with (pack / "data" / f"{station_id}.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["timestamp_utc", "temp_c", "rh_pct", "pressure_hpa", "wind_kmh", "wind_dir_deg", "rain_mm", "ghi_wm2"], lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
        (pack / "gps" / f"{station_id}.nmea").write_text("\n".join((gps or {}).get(station_id, [])) + ("\n" if (gps or {}).get(station_id) else ""), encoding="utf-8")
    return pack


class CheckerTests(unittest.TestCase):
    def test_replay_conflict_gap_and_required_schema(self) -> None:
        with workspace_tempdir() as temporary:
            root = Path(temporary)
            start = datetime(2027, 5, 1, tzinfo=UTC)
            alpha = regular_rows(start, 20)
            alpha.extend([dict(alpha[4]), dict(alpha[5])])
            beta = regular_rows(start, 20)
            conflict = dict(beta[8])
            conflict["temp_c"] = "99"
            beta.append(conflict)
            gamma = regular_rows(start, 20)
            del gamma[7]
            pack = write_pack(root, {"alpha": alpha, "beta": beta, "gamma": gamma})
            result = run_checker(pack, root / "out")
            issues = {(flag.station_id, flag.issue) for flag in result.flags}
            self.assertIn(("alpha", "exact replay copies"), issues)
            self.assertIn(("beta", "conflicting observations"), issues)
            self.assertIn(("gamma", "coverage gap"), issues)
            self.assertFalse(any(f.station_id == "beta" and f.issue == "coverage gap" for f in result.flags))
            with (root / "out" / "flags.csv").open(newline="", encoding="utf-8") as handle:
                self.assertEqual(next(csv.reader(handle)), FLAG_COLUMNS)

    def test_clock_offsets_both_signs_rollover_and_row_preservation(self) -> None:
        with workspace_tempdir() as temporary:
            root = Path(temporary)
            gps_start = datetime(2027, 6, 1, 23, 0, tzinfo=UTC)
            weather = {}
            gps_files = {}
            offsets = {"ahead": timedelta(hours=2), "behind": -timedelta(minutes=90)}
            for station_id, offset in offsets.items():
                weather[station_id] = [weather_row(gps_start + timedelta(minutes=10 * index) + offset) for index in range(18)]
                gps_files[station_id] = []
                for index in range(8):
                    gps_time = gps_start + timedelta(hours=index)
                    logger_time = gps_time + offset
                    gps_files[station_id].append(f"{logger_time:%Y-%m-%d %H:%M:%S},{rmc(gps_time)}")
            pack = write_pack(root, weather, gps=gps_files)
            before = input_hashes(pack)
            result = run_checker(pack, root / "out")
            self.assertEqual(before, input_hashes(pack))
            correction_flags = {flag.station_id: flag for flag in result.flags if flag.issue == "logger clock offset"}
            self.assertIn("-02:00", correction_flags["ahead"].note)
            self.assertIn("+01:30", correction_flags["behind"].note)
            for station in result.stations:
                self.assertEqual(len(station.records), 18)
                self.assertEqual(station.records[0].interpreted_utc, gps_start)
                self.assertEqual([record.source_row for record in station.records], list(range(2, 20)))

    def test_invalid_void_and_missing_gps_do_not_create_location_flag(self) -> None:
        with workspace_tempdir() as temporary:
            root = Path(temporary)
            start = datetime(2027, 1, 1, tzinfo=UTC)
            weather = {name: regular_rows(start, 24) for name in ("invalid", "void", "missing")}
            gps_files = {
                "invalid": [f"{start:%Y-%m-%d %H:%M:%S},{rmc(start, 50, -120, corrupt=True)}" for _ in range(24)],
                "void": [f"{(start + timedelta(hours=i)):%Y-%m-%d %H:%M:%S},{rmc(start + timedelta(hours=i), 50, -120, status='V')}" for i in range(24)],
            }
            pack = write_pack(root, weather, gps=gps_files)
            result = run_checker(pack, root / "out")
            self.assertFalse(any(flag.issue == "GPS/location disagreement" for flag in result.flags))
            candidates = {(item.station_id, item.candidate) for item in result.diagnostics}
            self.assertIn(("invalid", "partial GPS evidence"), candidates)
            self.assertIn(("missing", "GPS timing unavailable"), candidates)
            self.assertAlmostEqual(nmea_coordinate("3953.7000", "S", True), -(39 + 53.7 / 60))
            self.assertAlmostEqual(nmea_coordinate("10533.9000", "W", False), -(105 + 33.9 / 60))

    def test_temperature_flatline_but_zero_rain_and_night_ghi_are_normal(self) -> None:
        with workspace_tempdir() as temporary:
            root = Path(temporary)
            start = datetime(2027, 2, 1, tzinfo=UTC)
            weather = {name: regular_rows(start, 288) for name in ("flat", "peer1", "peer2")}
            for index in range(50, 100):
                weather["flat"][index]["temp_c"] = "7.25"
            pack = write_pack(root, weather)
            result = run_checker(pack, root / "out")
            flat_flags = [flag for flag in result.flags if flag.station_id == "flat"]
            self.assertTrue(any(flag.issue == "implausible persistence" and flag.channel == "temp_c" for flag in flat_flags))
            self.assertFalse(any(flag.channel in {"rain_mm", "ghi_wm2"} for flag in flat_flags))

    def test_humidity_violation_not_genuine_saturation(self) -> None:
        with workspace_tempdir() as temporary:
            root = Path(temporary)
            start = datetime(2027, 3, 1, tzinfo=UTC)
            bad = regular_rows(start, 100)
            saturated = regular_rows(start, 100)
            peer = regular_rows(start, 100)
            for index in range(20, 70):
                bad[index]["rh_pct"] = "103"
                saturated[index]["rh_pct"] = "100"
            bad[5]["temp_c"] = "not-a-number"
            pack = write_pack(root, {"bad": bad, "saturated": saturated, "peer": peer})
            result = run_checker(pack, root / "out")
            self.assertTrue(any(flag.station_id == "bad" and flag.issue == "physical-domain violation" for flag in result.flags))
            self.assertTrue(any(flag.station_id == "bad" and flag.issue == "missing/non-numeric readings" for flag in result.flags))
            self.assertFalse(any(flag.station_id == "saturated" and flag.channel == "rh_pct" for flag in result.flags))

    def test_shared_pressure_and_wind_event_is_not_local_fault(self) -> None:
        with workspace_tempdir() as temporary:
            root = Path(temporary)
            start = datetime(2027, 7, 1, tzinfo=UTC)
            count = 10 * 144
            weather = {}
            for station_id in ("a", "b", "c", "d"):
                def mutate(index, timestamp, base):
                    return {
                        "pressure_hpa": base["pressure_hpa"] + (6 if index >= count // 2 else 0),
                        "wind_kmh": base["wind_kmh"] * (2 if index >= count // 2 else 1),
                    }
                weather[station_id] = regular_rows(start, count, mutate)
            pack = write_pack(root, weather)
            result = run_checker(pack, root / "out")
            self.assertFalse(any(flag.issue in {"sustained pressure shift", "persistent wind-scale change"} for flag in result.flags))

    def test_local_pressure_shift_generalizes_to_reordered_ids_and_dates(self) -> None:
        with workspace_tempdir() as temporary:
            root = Path(temporary)
            start = datetime(2028, 9, 5, tzinfo=UTC)
            count = 10 * 144
            weather = {
                "zeta": regular_rows(start, count, lambda index, timestamp, base: {"pressure_hpa": base["pressure_hpa"] + (7 if index >= count // 2 else 0)}),
                "alpha": regular_rows(start, count),
                "mu": regular_rows(start, count),
            }
            pack = write_pack(root, weather, order=["mu", "zeta", "alpha"])
            result = run_checker(pack, root / "out")
            self.assertTrue(any(flag.station_id == "zeta" and flag.issue == "sustained pressure shift" for flag in result.flags))

    def test_insufficient_peers_stays_diagnostic(self) -> None:
        with workspace_tempdir() as temporary:
            root = Path(temporary)
            start = datetime(2029, 1, 1, tzinfo=UTC)
            rows = regular_rows(start, 600, lambda index, timestamp, base: {"pressure_hpa": base["pressure_hpa"] + (8 if index >= 300 else 0)})
            pack = write_pack(root, {"solo": rows})
            result = run_checker(pack, root / "out")
            self.assertFalse(any(flag.issue == "sustained pressure shift" for flag in result.flags))
            self.assertTrue(any(item.candidate == "pressure shift not assessed" for item in result.diagnostics))

    def test_persistent_wind_scale_change(self) -> None:
        with workspace_tempdir() as temporary:
            root = Path(temporary)
            start = datetime(2027, 10, 1, tzinfo=UTC)
            count = 10 * 144
            target = regular_rows(start, count, lambda index, timestamp, base: {"wind_kmh": base["wind_kmh"] * (0.22 if index >= count // 2 else 1)})
            pack = write_pack(root, {"target": target, "p1": regular_rows(start, count), "p2": regular_rows(start, count), "p3": regular_rows(start, count)})
            result = run_checker(pack, root / "out")
            self.assertTrue(any(flag.station_id == "target" and flag.issue == "persistent wind-scale change" for flag in result.flags))

    def test_rain_blockage_release_and_daylight_temperature_shift(self) -> None:
        with workspace_tempdir() as temporary:
            root = Path(temporary)
            start = datetime(2027, 11, 1, tzinfo=UTC)
            count = 10 * 144
            boundary = count // 2
            def target_mutate(index, timestamp, base):
                changes = {}
                daylight = base["ghi_wm2"] >= 100
                if index >= boundary and daylight:
                    changes["temp_c"] = base["temp_c"] + 5
                if boundary - 500 <= index < boundary:
                    changes["rain_mm"] = 0
                if index in {boundary, boundary + 1}:
                    changes["rain_mm"] = 6
                return changes
            target = regular_rows(start, count, target_mutate)
            peers = {}
            for name in ("p1", "p2", "p3"):
                peers[name] = regular_rows(start, count, lambda index, timestamp, base: {"rain_mm": 0.4 if boundary - 500 <= index < boundary and index % 20 == 0 else 0})
            pack = write_pack(root, {"target": target, **peers})
            result = run_checker(pack, root / "out")
            self.assertTrue(any(flag.station_id == "target" and flag.issue == "suspected rain-gauge blockage" for flag in result.flags))
            self.assertTrue(any(flag.station_id == "target" and flag.issue == "rain-gauge release readings" for flag in result.flags))
            self.assertTrue(any(flag.station_id == "target" and flag.issue == "daylight-dependent temperature shift" for flag in result.flags))

    def test_clean_pack_header_only_deterministic_and_current_directory_output(self) -> None:
        with workspace_tempdir() as temporary:
            root = Path(temporary)
            start = datetime(2027, 12, 1, tzinfo=UTC)
            pack = write_pack(root, {name: regular_rows(start, 60) for name in ("x", "y", "z")})
            work = root / "different-cwd"
            work.mkdir()
            command = [sys.executable, str(ROOT / "checker.py"), str(pack)]
            subprocess.run(command, cwd=work, check=True, capture_output=True, text=True)
            first = (work / "flags.csv").read_bytes()
            subprocess.run(command, cwd=work, check=True, capture_output=True, text=True)
            second = (work / "flags.csv").read_bytes()
            self.assertEqual(first, second)
            self.assertEqual(first.decode("utf-8").splitlines(), [",".join(FLAG_COLUMNS)])
            self.assertFalse((pack / "flags.csv").exists())

    def test_temporary_pressure_wind_humidity_faults_end_at_recovery(self) -> None:
        with workspace_tempdir() as temporary:
            root = Path(temporary)
            start = datetime(2030, 2, 1, tzinfo=UTC)
            count, onset, recovery = 20 * 144, 5 * 144, 12 * 144
            def pressure(index, timestamp, base):
                return {"pressure_hpa": base["pressure_hpa"] + (8 if onset <= index < recovery else 0)}
            def wind(index, timestamp, base):
                return {"wind_kmh": base["wind_kmh"] * (0.12 if onset <= index < recovery else 1)}
            def humidity(index, timestamp, base):
                return {"rh_pct": 104 if onset <= index < recovery else base["rh_pct"]}
            pack = write_pack(root, {"press": regular_rows(start, count, pressure), "wind": regular_rows(start, count, wind),
                                     "humid": regular_rows(start, count, humidity), "a": regular_rows(start, count),
                                     "b": regular_rows(start, count), "c": regular_rows(start, count)})
            before = input_hashes(pack)
            result = run_checker(pack, root / "out")
            self.assertEqual(before, input_hashes(pack))
            expected_end = start + timedelta(minutes=10 * (recovery - 1))
            for station_id, issue in (("press", "sustained pressure shift"), ("wind", "persistent wind-scale change"), ("humid", "physical-domain violation")):
                findings = [f for f in result.flags if f.station_id == station_id and f.issue == issue]
                self.assertEqual(len(findings), 1, (station_id, findings))
                self.assertEqual(findings[0].start_utc, start + timedelta(minutes=10 * onset))
                self.assertEqual(findings[0].end_utc, expected_end)
            for flag in result.flags:
                self.assertIn(flag.channel, {*CHANNELS, "timestamp_utc", "all", "metadata"})
                self.assertIn(flag.action, {"exclude", "correct", "keep"})
                self.assertLessEqual(flag.start_utc, flag.end_utc)
                self.assertRegex(flag.as_row()["start_utc"], r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$")

    def test_clock_reset_with_outage_preserves_observed_rows_and_real_gap(self) -> None:
        with workspace_tempdir() as temporary:
            root = Path(temporary)
            start = datetime(2031, 12, 31, 12, tzinfo=UTC)
            boundary = 144
            rows = []
            expected = []
            for index in range(3 * 144):
                if boundary <= index < boundary + 6:
                    continue  # Real one-hour outage at the reset; six absent observations.
                utc = start + timedelta(minutes=index * 10)
                raw = utc - (timedelta(minutes=90) if index >= boundary else timedelta())
                rows.append(weather_row(raw, temp_c=10 + index / 100, pressure_hpa=840 + index / 100))
                expected.append(utc)
            gps = []
            for hour in range(72):
                utc = start + timedelta(hours=hour)
                logger = utc - (timedelta(minutes=90) if hour >= 24 else timedelta())
                gps.append(f"{logger:%Y-%m-%d %H:%M:%S},{rmc(utc)}")
            pack = write_pack(root, {"reset": rows}, gps={"reset": gps})
            result = run_checker(pack, root / "out")
            records = result.stations[0].records
            self.assertEqual([r.interpreted_utc for r in records], expected)
            self.assertEqual(len(records), len(rows))
            gap = [f for f in result.flags if f.issue == "coverage gap"]
            self.assertEqual(len(gap), 1)
            self.assertEqual(gap[0].start_utc, start + timedelta(days=1))
            self.assertEqual(gap[0].end_utc, start + timedelta(days=1, minutes=50))
            self.assertEqual(records[144].correction_seconds, 5400)

    def test_clock_evidence_without_weather_boundary_remains_unresolved(self) -> None:
        with workspace_tempdir() as temporary:
            root = Path(temporary)
            start = datetime(2032, 1, 1, tzinfo=UTC)
            rows = regular_rows(start, 288)  # No reset in weather source order.
            gps = []
            for hour in range(48):
                utc = start + timedelta(hours=hour)
                logger = utc - (timedelta(hours=2) if hour >= 24 else timedelta())
                gps.append(f"{logger:%Y-%m-%d %H:%M:%S},{rmc(utc)}")
            pack = write_pack(root, {"unknown": rows}, gps={"unknown": gps})
            result = run_checker(pack, root / "out")
            self.assertFalse(any(f.action == "correct" for f in result.flags))
            self.assertTrue(any(d.candidate == "GPS clock-offset change" for d in result.diagnostics))
            self.assertTrue(all(r.correction_seconds == 0 for r in result.stations[0].records))

    def test_disputed_location_does_not_exclude_weather_or_support_spatial_peers(self) -> None:
        with workspace_tempdir() as temporary:
            root = Path(temporary)
            start = datetime(2033, 1, 1, tzinfo=UTC)
            rows = regular_rows(start, 10 * 144)
            gps = []
            for hour in range(24):
                utc = start + timedelta(hours=hour)
                # Two messages at one epoch are one independent timed receiver fix.
                gps.extend([f"{utc:%Y-%m-%d %H:%M:%S},{rmc(utc, 50, -120)}",
                            f"{utc:%Y-%m-%d %H:%M:%S},{gga(utc, 50, -120)}"])
            pack = write_pack(root, {"disputed": rows, "target": regular_rows(start, 10 * 144,
                lambda i, t, b: {"pressure_hpa": b["pressure_hpa"] + (8 if i >= 5 * 144 else 0)}), "one_peer": rows}, gps={"disputed": gps})
            result = run_checker(pack, root / "out")
            location = [f for f in result.flags if f.issue == "GPS/location disagreement"]
            self.assertEqual(len(location), 1)
            self.assertIn("48 valid position messages at 24 distinct", location[0].note)
            self.assertFalse(any(f.station_id == "disputed" and f.channel in {*CHANNELS, "all"} for f in result.flags))
            self.assertFalse(any(f.station_id == "target" and f.issue == "sustained pressure shift" for f in result.flags))
            # Repeated copies of one receiver epoch cannot meet the 20-epoch
            # location-evidence rule or six-epoch timing rule.
            utc = start
            same_epoch = [f"{utc:%Y-%m-%d %H:%M:%S},{rmc(utc, 50, -120)}"] * 30
            (pack / "gps" / "disputed.nmea").write_text("\n".join(same_epoch), encoding="utf-8")
            repeated_result = run_checker(pack, root / "repeated-epoch-out")
            self.assertFalse(any(f.issue == "GPS/location disagreement" for f in repeated_result.flags))

    def test_late_initial_gps_offset_does_not_force_whole_file_correction(self) -> None:
        with workspace_tempdir() as temporary:
            root = Path(temporary)
            start = datetime(2034, 1, 1, tzinfo=UTC)
            gps = []
            for hour in range(24, 48):
                utc = start + timedelta(hours=hour)
                logger = utc - timedelta(hours=2)
                gps.append(f"{logger:%Y-%m-%d %H:%M:%S},{rmc(utc)}")
            pack = write_pack(root, {"late": regular_rows(start, 288)}, gps={"late": gps})
            result = run_checker(pack, root / "out")
            self.assertFalse(any(f.action == "correct" for f in result.flags))
            self.assertTrue(any(d.candidate == "initial clock scope uncertain" for d in result.diagnostics))

    def test_transient_wind_event_does_not_displace_later_persistent_fault(self) -> None:
        with workspace_tempdir() as temporary:
            root = Path(temporary)
            start = datetime(2035, 1, 1, tzinfo=UTC)
            count, onset = 20 * 144, 12 * 144
            def mutate(index, timestamp, base):
                factor = 0.12 if 4 * 144 <= index < int(5.5 * 144) or index >= onset else 1
                return {"wind_kmh": base["wind_kmh"] * factor}
            pack = write_pack(root, {"target": regular_rows(start, count, mutate),
                "a": regular_rows(start, count), "b": regular_rows(start, count), "c": regular_rows(start, count)})
            result = run_checker(pack, root / "out")
            findings = [f for f in result.flags if f.station_id == "target" and f.issue == "persistent wind-scale change"]
            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0].start_utc, start + timedelta(minutes=10 * onset))
            self.assertEqual(findings[0].end_utc, start + timedelta(minutes=10 * (count - 1)))
            shorter = run_checker(pack, root / "shorter-out", replace(DEFAULT_THRESHOLDS, change_window_hours=48))
            findings = [f for f in shorter.flags if f.station_id == "target" and f.issue == "persistent wind-scale change"]
            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0].start_utc, start + timedelta(minutes=10 * onset))


if __name__ == "__main__":
    unittest.main()
