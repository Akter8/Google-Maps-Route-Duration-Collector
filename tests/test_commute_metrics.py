from datetime import date

import pandas as pd

from analysis.commute_metrics import (
    coverage_statistics, duration_statistics, expected_slots, filter_observations,
    normalize_observations, threshold_probabilities, traffic_delay_statistics,
)


def observations():
    return normalize_observations(pd.DataFrame([
        {"route_id": "R1", "direction": "outbound", "date_local": "2026-09-21", "scheduled_slot": "2026-09-21T14:30:00+00:00", "duration_seconds": 1800, "static_duration_seconds": 1200, "api_success": True},
        {"route_id": "R1", "direction": "outbound", "date_local": "2026-09-22", "scheduled_slot": "2026-09-22T14:30:00+00:00", "duration_seconds": 2400, "static_duration_seconds": 1200, "api_success": True},
        {"route_id": "R1", "direction": "outbound", "date_local": "2026-09-23", "scheduled_slot": "2026-09-23T14:30:00+00:00", "duration_seconds": 3600, "static_duration_seconds": 1200, "api_success": True},
        {"route_id": "R1", "direction": "outbound", "date_local": "2026-09-24", "scheduled_slot": "2026-09-24T14:30:00+00:00", "duration_seconds": None, "static_duration_seconds": None, "api_success": False},
    ]))


def test_duration_delay_and_threshold_metrics_are_derived_from_observations():
    frame = observations()
    stats = duration_statistics(frame)
    assert stats["observation_count"] == 3
    assert stats["unique_days"] == 3
    assert stats["p50"] == 2400
    assert stats["bad_day_spread"] == stats["p90"] - stats["p50"]
    assert stats["p90_p50_ratio"] == stats["p90"] / stats["p50"]
    delays = traffic_delay_statistics(frame)
    assert delays == {"delay_observation_count": 3, "average_traffic_delay": 1400.0,
                      "median_traffic_delay": 1200.0, "p90_traffic_delay": 2160.0}
    assert threshold_probabilities(frame, (30, 45, 60)) == {30.0: 2 / 3, 45.0: 1 / 3, 60.0: 0.0}


def test_filter_and_coverage_distinguish_missing_from_failed_slots():
    frame = observations()
    selected = filter_observations(frame, "R1", "outbound", date(2026, 9, 21), date(2026, 9, 25), "07:30")
    coverage = coverage_statistics(selected, date(2026, 9, 21), date(2026, 9, 25), "outbound", departure_time="07:30")
    assert coverage == {"expected_observations": 5, "recorded_observations": 4, "successful_observations": 3,
                        "failed_observations": 1, "missing_observations": 1, "coverage_percentage": 80.0,
                        "successful_coverage_percentage": 60.0}


def test_expected_slots_follow_collector_direction_boundaries():
    day = date(2026, 9, 21)
    outbound = expected_slots(day, day, "outbound")
    returning = expected_slots(day, day, "return")
    assert all(slot.hour < 13 or slot.hour >= 19 for slot in outbound)
    assert all(13 <= slot.hour < 19 for slot in returning)
