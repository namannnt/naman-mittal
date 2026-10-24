"""Build the offline coordinator report and derived usability assessment.

Run: python analysis/build_report.py <pack-dir> [--data-only]
The narrative policy is specific to this reviewed snapshot; checker logic is
unchanged. All report counts and flag periods are derived on every build.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
import statistics
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from quality_checker import run_checker
from quality_checker.core import CHANNELS, input_hashes
import quality_checker.core as checker_core
from quality_checker.config import DEFAULT_THRESHOLDS

LABELS = {
    "temp_c": "temperature", "rh_pct": "humidity", "pressure_hpa": "station pressure",
    "wind_kmh": "wind speed", "wind_dir_deg": "wind direction", "rain_mm": "rain", "ghi_wm2": "sunlight",
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_csv(path: Path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def parse_time(text: str) -> datetime:
    return datetime.strptime(text, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)


def build_assessment(pack: Path) -> dict:
    before = input_hashes(pack)
    flags = read_csv(ROOT / "flags.csv")
    diagnostics = read_csv(ROOT / "diagnostics.csv")
    result = run_checker(pack, ROOT / "tmp" / "report-checker")
    if [f.as_row() for f in result.flags] != flags:
        raise ValueError("Reviewed flags.csv differs from the current checker; review before reporting.")
    if [d.as_row() for d in result.diagnostics] != diagnostics:
        raise ValueError("Reviewed diagnostics.csv differs from the current checker.")
    # Deduplicate by complete raw row signature, retaining first occurrence and
    # provenance. The replay flag's calendar interval must not remove originals.
    genuine = {}
    raw_counts, replay_counts = {}, {}
    for station in result.stations:
        seen, retained = set(), []
        for record in station.records:
            signature = record.signature()
            if signature not in seen:
                seen.add(signature)
                retained.append(record)
        genuine[station.station_id] = retained
        raw_counts[station.station_id] = len(station.records)
        replay_counts[station.station_id] = len(station.records) - len(retained)
    times = [r.interpreted_utc for records in genuine.values() for r in records if r.interpreted_utc]
    start, end = min(times), max(times)
    assessments = {}
    for station in result.stations:
        station_id = station.station_id
        step = timedelta(minutes=station.interval_minutes)
        expected = {start + i * step for i in range(int((end - start) / step) + 1)}
        groups = defaultdict(list)
        for record in genuine[station_id]:
            if record.interpreted_utc:
                groups[record.interpreted_utc].append(record)
        observed = set(groups)
        if observed - expected:
            raise ValueError(f"{station_id} has off-grid timestamps; denominator requires review.")
        station_flags = [f for f in flags if f["station_id"] == station_id]
        channel_assessments = {}
        for channel in CHANNELS:
            absent = expected - observed
            excluded = set()
            present_missing_value = set()
            corrected = set()
            for timestamp, records in groups.items():
                values = {r.value(channel) for r in records}
                if len(values) != 1:
                    excluded.add(timestamp)
                elif None in values:
                    present_missing_value.add(timestamp)
                if any(r.correction_seconds for r in records):
                    corrected.add(timestamp)
            for flag in station_flags:
                if (flag["action"] != "exclude" or flag["channel"] not in {channel, "all"}
                        or flag["issue"] in {"exact replay copies", "coverage gap"}):
                    continue
                begin, finish = parse_time(flag["start_utc"]), parse_time(flag["end_utc"])
                excluded.update(t for t in observed if begin <= t <= finish)
            # Sets union overlapping exclusions once. Metadata and keep flags
            # cannot erase channel observations; missing is separate.
            excluded.update(present_missing_value)
            usable = observed - excluded
            after_correction = usable & corrected
            concerns = [d for d in diagnostics if d["station_id"] == station_id and d["channel"] == channel]
            policy = "Use retained observations provisionally; no detected exclusion is proof of accuracy."
            if station_id == "S04" and channel == "temp_c":
                policy = ("Reporting recommendation, not a new checker flag: withhold daytime maxima and unqualified full-period temperature means for S04 pending a shield/reference check; labelled night-only summaries may be used provisionally.")
            elif station_id == "S05":
                policy = "Retained values may support a labelled station series, but suspend mapping, spatial comparison and location attribution until identity is checked."
            elif channel == "rain_mm" and (absent or excluded):
                policy = "Use retained intervals only; no complete six-week rain total or reconstructed missing rain."
            elif concerns:
                policy = "Retained readings remain provisional; inspect unresolved peer warnings before unqualified extremes or rain-total claims."
            channel_assessments[channel] = {
                "expected_slots": len(expected), "missing_slots": len(absent),
                "excluded_observed_slots": len(excluded),
                "retained_as_observed": len(usable - corrected),
                "retained_after_supported_correction": len(after_correction),
                "retained_slots": len(usable),
                "retained_percent": round(100 * len(usable) / len(expected), 1),
                "unresolved_candidates": [{"candidate": d["candidate"], "start_utc": d["start_utc"], "end_utc": d["end_utc"]} for d in concerns],
                "report_policy": policy,
            }
            assert len(expected) == len(absent) + len(excluded) + len(usable)
        assessments[station_id] = {
            "name": station.metadata["name"], "interval_minutes": station.interval_minutes,
            "raw_rows": raw_counts[station_id], "replay_copies_removed": replay_counts[station_id],
            "genuine_rows": len(genuine[station_id]), "unique_observed_slots": len(observed),
            "expected_slots": len(expected), "missing_slots": len(expected - observed),
            "metadata_disputed": any(f["channel"] == "metadata" and f["action"] == "exclude" for f in station_flags),
            "clock_corrections_seconds": sorted({r.correction_seconds for r in genuine[station_id] if r.correction_seconds}),
            "channels": channel_assessments,
        }
    assert input_hashes(pack) == before, "Input contents changed during report calculation."
    # Recompute the reviewed S04 sunny/night contrast rather than baking the
    # rounded figure into report copy. A note date partitions a hypothesis
    # comparison only; it never becomes a checker boundary or assumed UTC event.
    series = {s.station_id: checker_core._unique_series(s, set()) for s in result.stations}
    target = next(s for s in result.stations if s.station_id == "S04")
    peers = checker_core._peer_ids(target, result.stations, "temp_c", series, DEFAULT_THRESHOLDS, result.flags)
    painting = next(n for n in checker_core._read_notes(pack) if n["station_id"] == "S04" and "paint" in n["note"].lower())
    note_date = datetime.strptime(painting["date_raw"], "%Y-%m-%d").date()
    comparison = defaultdict(list)
    for timestamp, record in series["S04"].items():
        if timestamp.date() == note_date:
            continue
        reference = checker_core._peer_value(timestamp, "temp_c", peers, series, result.flags, 2)
        if reference is None:
            continue
        irradiance = record.value("ghi_wm2")
        phase = "sunny" if irradiance >= 500 else "night" if irradiance <= 10 else None
        side = "before" if timestamp.date() < note_date else "after"
        if phase:
            comparison[(phase, side)].append(record.value("temp_c") - reference)
    temperature_evidence = {}
    for phase in ("sunny", "night"):
        before_values, after_values = comparison[(phase, "before")], comparison[(phase, "after")]
        temperature_evidence[phase] = {"before_median_c": statistics.median(before_values),
            "after_median_c": statistics.median(after_values), "before_n": len(before_values), "after_n": len(after_values),
            "shift_c": statistics.median(after_values) - statistics.median(before_values)}
    return {
        "coverage_start_utc": start.strftime("%Y-%m-%d %H:%M"),
        "coverage_end_utc": end.strftime("%Y-%m-%d %H:%M"),
        "input_files_verified_unchanged": len(before),
        "source_sha256": {name: digest(ROOT / name) for name in ("flags.csv", "diagnostics.csv")},
        "flags": flags, "stations": assessments,
        "S04_temperature_evidence": temperature_evidence,
    }


def render_html(data: dict) -> str:
    stations = data["stations"]
    flags = data["flags"]

    def issue(station_id, name):
        return next(f for f in flags if f["station_id"] == station_id and f["issue"] == name)

    def short_date(text):
        value = parse_time(text)
        return f"{value.day} {value.strftime('%b')}"

    pressure = issue("S02", "sustained pressure shift")
    freeze = issue("S03", "implausible persistence")
    blockage = issue("S04", "suspected rain-gauge blockage")
    release = issue("S04", "rain-gauge release readings")
    rh = issue("S05", "physical-domain violation")
    wind = issue("S07", "persistent wind-scale change")
    gap = issue("S08", "coverage gap")
    corrected = stations["S06"]["channels"]["temp_c"]["retained_after_supported_correction"]
    clock_hours = stations["S06"]["clock_corrections_seconds"]
    if len(clock_hours) != 1 or clock_hours[0] <= 0:
        raise ValueError("S06 report wording needs review for this clock correction.")
    clock_hours = clock_hours[0] / 3600
    removed_replay = stations["S08"]["replay_copies_removed"]
    retained8 = stations["S08"]["unique_observed_slots"]
    missing8 = stations["S08"]["missing_slots"]
    expected = stations["S08"]["expected_slots"]
    sunny_shift = data["S04_temperature_evidence"]["sunny"]["shift_c"]
    spike_count = sum(f["station_id"] == "S03" and f["issue"] == "isolated temperature spike" for f in flags)
    full_range = f"{short_date(data['coverage_start_utc'])}–{short_date(data['coverage_end_utc'])} {parse_time(data['coverage_end_utc']).year}"
    descriptions = {
        "S01": ("All seven channels.", "Keep the low <b>P</b>: high elevation explains it; it is not sea-level pressure."),
        "S02": ("<b>T† H W D R L</b>; earlier <b>P</b>.", f"Exclude <b>P</b> from {short_date(pressure['start_utc'])} onward; no recovery shown after the board change."),
        "S03": ("<b>H P W D R L</b>; retained <b>T</b>.", f"Remove {spike_count} isolated <b>T</b> spikes and the {short_date(freeze['start_utc'])}–{short_date(freeze['end_utc'])} stuck readings; qualify <b>R</b> dry-spell results."),
        "S04": ("<b>H P W D L</b>; retained <b>R</b>; night-only <b>T</b> provisionally.", f"Exclude suspect <b>R</b> {short_date(blockage['start_utc'])}–{short_date(release['end_utc'])}, including release readings; no complete rain total. <b>T</b>: hold daytime highs and unqualified means.*"),
        "S05": ("Retained <b>T H P W D R L</b> as a labelled station series.", f"Exclude <b>H</b> {short_date(rh['start_utc'])}–{short_date(rh['end_utc'])}; suspend mapping and spatial attribution until the location dispute is resolved."),
        "S06": ("All channels after the supported clock repair; <b>T†</b> remains provisional.", f"Add {clock_hours:g} hours to the affected {short_date(issue('S06', 'logger clock offset')['start_utc'])} onward records: {corrected:,} timestamps repaired, no readings lost."),
        "S07": ("<b>T† H P D R L</b>; earlier <b>W</b>.", f"Exclude <b>W</b> from about {short_date(wind['start_utc'])} onward; no recovery shown and no calibrated multiplier established."),
        "S08": ("Available observations in every channel; <b>T†</b> provisional.", f"{retained8:,}/{expected:,} unique times; {short_date(gap['start_utc'])}–{short_date(gap['end_utc'])} gap. Remove {removed_replay} later replay copies, retain originals; rain total is partial."),
    }
    rows = []
    for station_id in stations:
        use, caveat = descriptions[station_id]
        rows.append(f"<tr><th scope='row'>{station_id}</th><td>{use}</td><td>{caveat}</td></tr>")
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light">
<title>Ridgeline network health — {full_range}</title>
<style>
@page {{ size: A4 portrait; margin: 11mm 12mm; }}
* {{ box-sizing: border-box; }}
html {{ background: #e9ebe9; color: #202524; }}
body {{ margin: 0; font: 10pt/1.32 Arial, Helvetica, sans-serif; }}
main {{ width: 186mm; margin: 20px auto; padding: 11mm 0; background: #fff; }}
header {{ border-top: 3px solid #234b47; padding-top: 9px; }}
.eyebrow {{ margin: 0 0 5px; font-size: 8.4pt; font-weight: 700; letter-spacing: 1.4px; text-transform: uppercase; }}
h1 {{ font-size: 25pt; line-height: 1.05; letter-spacing: -.6px; margin: 0 0 6px; font-weight: 700; }}
.meta {{ margin: 0; font-size: 9pt; color: #424b48; }}
.lead {{ margin: 10px 0 11px; padding: 9px 0 9px 12px; border-left: 3px solid #234b47; }}
.lead strong {{ display: block; font-size: 13pt; margin-bottom: 4px; }}
.lead p {{ margin: 0; }}
h2 {{ margin: 0 0 5px; font-size: 11pt; line-height: 1.2; }}
.legend {{ margin: 0 0 8px; font-size: 8.5pt; color: #343b38; }}
table {{ width: 100%; border-collapse: collapse; table-layout: fixed; font-size: 9.3pt; line-height: 1.27; }}
col.station {{ width: 9%; }} col.use {{ width: 33%; }} col.exception {{ width: 58%; }}
thead {{ display: table-header-group; }}
thead th {{ padding: 6px 7px; text-align: left; background: #edf1ef; border-top: 1px solid #56605b; border-bottom: 1px solid #56605b; font-size: 8.5pt; }}
tbody th, tbody td {{ padding: 5px 7px; vertical-align: top; border-bottom: 1px solid #c5cbc7; overflow-wrap: break-word; }}
tbody th {{ text-align: left; font-weight: 700; }}
tr {{ break-inside: avoid; page-break-inside: avoid; }}
.table-note {{ font-size: 8.3pt; margin: 7px 0 9px; line-height: 1.3; }}
.visit {{ border: 1px solid #5b6560; border-left: 3px solid #234b47; padding: 10px 12px; break-inside: avoid; page-break-inside: avoid; }}
.visit h2 {{ font-size: 13pt; margin-bottom: 5px; }}
.visit .first {{ margin: 0 0 7px; }}
.visit-grid {{ display: grid; grid-template-columns: 1.1fr 1fr; gap: 14px; }}
ol {{ list-style: none; padding: 0; margin: 0; }}
li {{ margin: 0 0 4px; padding-left: 48px; position: relative; }}
li time {{ position: absolute; left: 0; font-weight: 700; font-size: 8.5pt; padding-top: 1px; }}
.visit p {{ margin: 0 0 6px; font-size: 9pt; }}
.visit .runner {{ border-top: 1px solid #c5cbc7; margin: 6px 0 0; padding-top: 7px; }}
.limits {{ margin-top: 8px; font-size: 8.4pt; line-height: 1.32; }}
.limits p {{ margin: 0 0 5px; }}
footer {{ border-top: 1px solid #8d9791; margin-top: 8px; padding-top: 5px; font-size: 8pt; color: #424b48; }}
@media print {{
 html, body {{ background: #fff; }}
 main {{ width: auto; margin: 0; padding: 0; }}
 header, .visit, thead th {{ print-color-adjust: exact; -webkit-print-color-adjust: exact; }}
}}
@media screen and (max-width: 760px) {{
 main {{ width: auto; margin: 0; padding: 18px; }}
 h1 {{ font-size: 23pt; }}
 .visit-grid {{ grid-template-columns: 1fr; gap: 3px; }}
 table {{ font-size: 9pt; }}
}}
</style>
</head>
<body><main>
<header>
<p class="eyebrow">Ridgeline schools weather network · Decision note</p>
<h1>Network health &amp; the next visit</h1>
<p class="meta">Supplied record: <strong>{full_range}</strong> · UTC · Eight stations · Six-week snapshot</p>
</header>
<section class="lead" aria-label="Recommended decisions">
<strong>Use the records selectively. Send the technician to S07.</strong>
<p>Apply the channel exclusions and clock repair before summarising. Hold S04 daytime temperature highs and unqualified means; avoid complete rain totals for S04/S08. Confirm that S07’s wind issue persists before dispatch: this recommendation uses the 2025 record, not live status.</p>
</section>
<section aria-labelledby="usability-title">
<h2 id="usability-title">What can support the requested summary?</h2>
<p class="legend"><b>T</b> temperature · <b>H</b> humidity · <b>P</b> station pressure · <b>W</b> wind speed · <b>D</b> wind direction · <b>R</b> rain · <b>L</b> sunlight</p>
<table aria-describedby="coverage-note">
<colgroup><col class="station"><col class="use"><col class="exception"></colgroup>
<thead><tr><th scope="col">Station</th><th scope="col">Use provisionally</th><th scope="col">Exceptions and reporting instructions</th></tr></thead>
<tbody>{''.join(rows)}</tbody>
</table>
<p class="table-note" id="coverage-note">Coverage counts unique 10-minute times after clock repair: {expected:,} expected per station; S08 has {missing8} missing. Replay originals count once. Complete timestamps do not prove accurate measurements; use retained intervals only, with explicit coverage.</p>
</section>
<section class="visit" aria-labelledby="visit-title">
<h2 id="visit-title">One hour at S07 · Riverbend Farm</h2>
<p class="first"><b>First check:</b> identify the replacement anemometer and compare its documented output with the logger’s configured input.</p>
<div class="visit-grid">
<ol aria-label="One-hour visit sequence">
<li><time>0–10</time>Record model/serial labels and current settings.</li>
<li><time>10–25</time>Inspect cups, mounting and visible damage safely; compare both manuals.</li>
<li><time>25–45</time>Check compatibility and document a short comparison beside a portable wind reference.</li>
<li><time>45–60</time>Save evidence; agree the next repair or manufacturer-supported setup step.</li>
</ol>
<div>
<p><b>Bring:</b> old/new sensor model details, logger manual and settings access, camera, and a portable wind reference if available.</p>
<p><b>Useful outcome:</b> establish compatibility or a specific unresolved mismatch, and define the repair needed; a short field comparison is not certified calibration.</p>
</div>
</div>
<p class="runner"><b>Runner-up: S04.</b> Its sunny-temperature concern matters, but the cause remains unresolved and the rain gauge resumes small readings after cleaning. S07’s wind relationship remains shifted to record end after a different-brand replacement; a compatibility visit can prevent more unusable data.</p>
</section>
<section class="limits" aria-label="Limits of this recommendation">
<p><b>* Reporting precaution, not a new flag:</b> S04’s sunny temperature difference increased about {sunny_shift:.1f}°C relative to peers; night/cloudy changes are much smaller. Withhold its daytime highs and unqualified mean pending a shield/reference check. <b>†</b> Other daylight-temperature warnings remain unresolved; qualify daytime extremes. S03/S08 dry-spell rain warnings also need qualification.</p>
<p>S05’s location sources disagree; which is wrong is unknown. S07’s start is estimated and setting-sensitive, not a known failure instant. Volunteer-note times have no timezone; peers support evidence but are not certified references.</p>
</section>
<footer>Six-week snapshot only; no long-term climate trend claim. Dates above are overviews: apply precise channel intervals in flags.csv.</footer>
</main></body></html>
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pack_dir", type=Path)
    parser.add_argument("--data-only", action="store_true")
    args = parser.parse_args()
    data = build_assessment(args.pack_dir.resolve())
    output = ROOT / "tmp" / "report-data.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if args.data_only:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        report_path = ROOT / "report.html"
        report_path.write_text(render_html(data), encoding="utf-8", newline="\n")
        print(f"Wrote {report_path}; derived assessment: {output}")


if __name__ == "__main__":
    main()
