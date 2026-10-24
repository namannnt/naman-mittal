"""Reproduce derived Step 2B evidence; no supplied observations are written."""
from __future__ import annotations

import argparse
import json
import statistics as st
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import quality_checker.core as q
from quality_checker.config import DEFAULT_THRESHOLDS as config


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("pack", type=Path)
    args = parser.parse_args()
    stations, _ = q._load_pack(args.pack, config)
    flags = []
    series = {}
    for station in stations:
        clock, _ = q._apply_clock_evidence(station, config)
        timeline, _, excluded = q._timeline_checks(station, config)
        gps, _, _ = q._gps_checks(station, config)
        flags.extend(clock + timeline + gps + q._domain_checks(station, excluded, config)
                     + q._persistence_checks(station, excluded, config)
                     + q._temperature_spikes(station, excluded, config))
        series[station.station_id] = q._unique_series(station, excluded)
    output = {}
    target = next(s for s in stations if s.station_id == "S04")
    peers = [p for p in q._peer_ids(target, stations, "temp_c", series, config)
             if not any(f.station_id == p and f.channel == "metadata" for f in flags)]
    # The note date is used only for this hypothesis review, never detection.
    split = datetime(2025, 3, 15, tzinfo=timezone.utc)
    potential_samples = defaultdict(list)
    for record in series["S04"].values():
        t = record.interpreted_utc
        potential_samples[(t.hour, t.minute)].append(record.value("ghi_wm2"))
    potential = {k: sorted(v)[int((len(v) - 1) * 0.95)] for k, v in potential_samples.items()}
    phase_values = defaultdict(list)
    weekly = defaultdict(list)
    per_peer = defaultdict(list)
    for timestamp, record in sorted(series[target.station_id].items()):
        if timestamp.date() == split.date():
            continue
        side = "before" if timestamp < split else "after"
        ghi, wind = record.value("ghi_wm2"), record.value("wind_kmh")
        phase = "sunny>=500" if ghi >= 500 else "cloudy/low sun 10..200" if 10 < ghi <= 200 else "night<=10" if ghi <= 10 else "intermediate"
        wind_bin = "<5" if wind < 5 else "5..15" if wind < 15 else ">=15"
        reference = q._peer_value(timestamp, "temp_c", peers, series, flags, 2)
        if reference is None:
            continue
        residual = record.value("temp_c") - reference
        phase_values[(side, phase, "all")].append(residual)
        phase_values[(side, phase, wind_bin)].append(residual)
        expected = potential[(timestamp.hour, timestamp.minute)]
        if expected >= 500 and ghi <= expected * 0.35:
            phase_values[(side, "cloudy at high-sun clock bins", "all")].append(residual)
        week = (timestamp - min(series[target.station_id])).days // 7
        weekly[(week, phase)].append(residual)
        for peer in peers:
            peer_record = series[peer].get(timestamp)
            if peer_record and not q._is_unreliable(flags, peer, "temp_c", timestamp):
                per_peer[(peer, side, phase)].append(record.value("temp_c") - peer_record.value("temp_c"))
    summarize = lambda groups: [{"group": list(k), "n": len(v), "median_c": round(st.median(v), 3)} for k, v in sorted(groups.items())]
    output["S04_temperature"] = {"peers": peers, "phase_wind": summarize(phase_values), "weekly": summarize(weekly), "pairwise": summarize(per_peer)}
    post_release = datetime(2025, 4, 2, 16, 40, tzinfo=timezone.utc)
    output["rain_post_release"] = {}
    for station in stations:
        values = [r.value("rain_mm") for t, r in series[station.station_id].items() if t >= post_release]
        output["rain_post_release"][station.station_id] = {"n": len(values), "wet": sum(v > 0 for v in values), "total_mm": round(sum(values), 3), "max_mm": max(values)}
    for station_id, channel in [("S02", "pressure_hpa"), ("S07", "wind_kmh")]:
        target = next(s for s in stations if s.station_id == station_id)
        peers = [p for p in q._peer_ids(target, stations, channel, series, config) if not any(f.station_id == p and f.channel == "metadata" for f in flags)]
        daily = defaultdict(list)
        for t, r in sorted(series[station_id].items()):
            peer = q._peer_value(t, channel, peers, series, flags, 2)
            if peer is None or (channel == "wind_kmh" and peer < config.wind_ratio_floor_kmh):
                continue
            value = r.value(channel) - peer if channel == "pressure_hpa" else (r.value(channel) + config.wind_ratio_floor_kmh) / (peer + config.wind_ratio_floor_kmh)
            daily[t.strftime("%Y-%m-%d")].append(value)
        output[station_id] = {"peers": peers, "daily": [{"date": d, "n": len(v), "median": round(st.median(v), 3)} for d, v in sorted(daily.items())]}
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
