"""Documented thresholds for candidate generation and action evidence.

Physical constraints are separate from heuristic thresholds. Values are based
on measurement semantics and conservative evidence requirements, not station
IDs, supplied-pack dates, or expected row counts.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Thresholds:
    # GPS/timeline evidence.
    gps_offset_round_seconds: int = 60
    gps_min_segment_observations: int = 6
    gps_offset_change_seconds: int = 5 * 60
    gps_boundary_tolerance_seconds: int = 2 * 60
    gps_min_position_observations: int = 20
    gps_location_disagreement_m: float = 5_000.0

    # Replay and gap handling.
    gap_min_missing_intervals: int = 1

    # Physical-domain episode grouping. Intervening in-domain readings may be
    # included only when the episode is dense and short gaps support one fault.
    domain_cluster_gap_intervals: int = 12
    domain_cluster_min_fraction: float = 0.50

    # Persistence and isolated temperature spikes.
    temp_flatline_min_hours: float = 6.0
    pressure_flatline_min_hours: float = 6.0
    wind_direction_flatline_min_hours: float = 12.0
    wind_active_min_kmh: float = 3.0
    spike_window_intervals: int = 6
    temp_spike_min_abs_c: float = 20.0
    temp_spike_mad_multiplier: float = 12.0
    temp_spike_return_tolerance_c: float = 4.0

    # Peer eligibility and change evidence.
    peer_max_distance_km: float = 100.0
    peer_max_elevation_difference_m: float = 500.0
    pressure_peer_max_elevation_difference_m: float = 250.0
    peer_min_overlap: int = 48
    peer_min_count_per_timestamp: int = 2
    change_window_hours: float = 72.0
    change_min_observations_each_side: int = 144
    pressure_raw_step_min_hpa: float = 3.0
    pressure_residual_shift_min_hpa: float = 3.0
    wind_ratio_floor_kmh: float = 3.0
    wind_scale_factor_min: float = 2.0
    wind_confirmation_days: int = 3
    wind_confirmation_min_daily_observations: int = 48
    wind_baseline_consistency_fraction: float = 0.5
    daylight_ghi_min_wm2: float = 100.0
    night_ghi_max_wm2: float = 10.0
    daylight_temp_shift_min_c: float = 4.0
    daylight_night_shift_max_c: float = 1.5
    daylight_diagnostic_min_c: float = 1.0
    recovery_confirmation_hours: float = 24.0
    recovery_baseline_fraction: float = 0.25
    local_boundary_hours: float = 72.0

    # Rain blockage requires a long zero run, regional wet evidence, and a
    # station-only release immediately afterwards.
    rain_zero_min_hours: float = 72.0
    rain_peer_wet_min_stations: int = 2
    rain_peer_wet_min_intervals: int = 12
    rain_release_min_mm: float = 5.0
    rain_release_max_intervals_after: int = 3
    rain_release_peer_median_max_mm: float = 0.2

    # Explicit keep evidence for station pressure at high elevation.
    high_elevation_min_m: float = 2_000.0
    high_elevation_pressure_max_hpa: float = 800.0
    gps_altitude_agreement_m: float = 150.0


DEFAULT_THRESHOLDS = Thresholds()
