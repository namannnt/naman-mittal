"""Reproduce Step 2B output, provenance, sensitivity and preservation checks."""
from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
from dataclasses import replace
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from quality_checker import run_checker
from quality_checker.config import DEFAULT_THRESHOLDS as DEFAULT
from quality_checker.core import CHANNELS, FLAG_COLUMNS, input_hashes


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def key(flag):
    return (flag.station_id, flag.channel, flag.issue, flag.action,
            flag.start_utc.strftime("%Y-%m-%d %H:%M"), flag.end_utc.strftime("%Y-%m-%d %H:%M"))


def main():
    pack = Path(sys.argv[1]).resolve()
    before = input_hashes(pack)
    output = ROOT / "tmp" / "step2b-validation"
    result = run_checker(pack, ROOT)
    repeat = run_checker(pack, output / "repeat")
    alternate = output / "alternate-cwd"
    alternate.mkdir(parents=True, exist_ok=True)
    subprocess.run([sys.executable, str(ROOT / "checker.py"), str(pack)], cwd=alternate,
                   capture_output=True, text=True, check=True)
    with (ROOT / "flags.csv").open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        assert reader.fieldnames == FLAG_COLUMNS
        for row in reader:
            assert row["channel"] in {*CHANNELS, "timestamp_utc", "all", "metadata"}
            assert row["action"] in {"exclude", "correct", "keep"}
            start = datetime.strptime(row["start_utc"], "%Y-%m-%d %H:%M")
            end = datetime.strptime(row["end_utc"], "%Y-%m-%d %H:%M")
            assert start <= end
    matches = {name: len({digest(folder / name) for folder in (ROOT, output / "repeat", alternate)}) == 1
               for name in ("flags.csv", "diagnostics.csv")}
    assert all(matches.values())
    baseline = {key(flag) for flag in result.flags}
    sensitivity = {}
    variants = {
        "pressure_2": {"pressure_residual_shift_min_hpa": 2.0},
        "pressure_5": {"pressure_residual_shift_min_hpa": 5.0},
        "wind_1.75": {"wind_scale_factor_min": 1.75},
        "wind_2.5": {"wind_scale_factor_min": 2.5},
        "window_48h": {"change_window_hours": 48.0},
        "window_96h": {"change_window_hours": 96.0},
        "wind_floor_2": {"wind_ratio_floor_kmh": 2.0},
        "wind_floor_4": {"wind_ratio_floor_kmh": 4.0},
        "rain_24": {"rain_peer_wet_min_intervals": 24},
        "rain_3_peers": {"rain_peer_wet_min_stations": 3},
        "daylight_3": {"daylight_temp_shift_min_c": 3.0},
        "daylight_5": {"daylight_temp_shift_min_c": 5.0},
    }
    for name, values in variants.items():
        changed = run_checker(pack, output / name, replace(DEFAULT, **values))
        keys = {key(flag) for flag in changed.flags}
        sensitivity[name] = {"count": len(keys), "removed": sorted(baseline - keys), "added": sorted(keys - baseline)}
    reset = next(s for s in result.stations if s.station_id == "S06")
    reset_times = [r.interpreted_utc for r in reset.records]
    replay = next(s for s in result.stations if s.station_id == "S08")
    unique_replay = len({r.signature() for r in replay.records})
    replay_times = sorted({r.interpreted_utc for r in replay.records if r.interpreted_utc is not None})
    missing_replay = sum(int((b - a).total_seconds() // (replay.interval_minutes * 60)) - 1
                         for a, b in zip(replay_times, replay_times[1:]))
    assert input_hashes(pack) == before
    report = {
        "flags": len(result.flags), "diagnostics": len(result.diagnostics),
        "output_schema_valid": True, "matching_repeat_and_alternate_cwd": matches,
        "input_files": len(before), "input_files_changed": 0,
        "sha256": {name: digest(ROOT / name) for name in ("flags.csv", "diagnostics.csv")},
        "S06": {"records": len(reset.records), "unique_utc": len(set(reset_times)),
                "strictly_increasing": all(a < b for a, b in zip(reset_times, reset_times[1:])),
                "mapping": [{"source_row_header_is_1": r.source_row, "raw": r.raw_timestamp,
                             "utc": r.interpreted_utc.isoformat(), "correction_seconds": r.correction_seconds}
                            for r in reset.records[3407:3413]]},
        "S08": {"raw": len(replay.records), "unique": unique_replay,
                "replay_extras": len(replay.records) - unique_replay,
                "missing": missing_replay, "nominal_slots": unique_replay + missing_replay},
        "sensitivity": sensitivity,
    }
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
