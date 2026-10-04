"""Pure, reusable commute analysis for traffic observations.

All duration values returned by this module are seconds. Presentation code is
responsible for converting them to minutes, keeping calculations precise and
independent of the dashboard.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Iterable
from zoneinfo import ZoneInfo

import pandas as pd

from src.scheduler import scheduled_slots

DEFAULT_THRESHOLDS_MINUTES = (30, 45, 60, 75)
RETURN_START = time(13)
RETURN_END = time(19)


def normalize_observations(frame: pd.DataFrame, timezone: str = "America/Los_Angeles") -> pd.DataFrame:
    """Return a copy with dependable local dates, slots, and numeric columns."""
    result = frame.copy()
    if result.empty:
        for column in ("route_id", "direction", "api_success", "scheduled_slot", "date_local",
                       "duration_seconds", "static_duration_seconds"):
            if column not in result:
                result[column] = pd.Series(dtype="object")
        result["departure_time"] = pd.Series(dtype="object")
        return result
    result["scheduled_slot"] = pd.to_datetime(result["scheduled_slot"], utc=True).dt.tz_convert(timezone)
    result["date_local"] = pd.to_datetime(result["date_local"]).dt.date
    result["departure_time"] = result["scheduled_slot"].dt.strftime("%H:%M")
    for column in ("duration_seconds", "static_duration_seconds"):
        result[column] = pd.to_numeric(result.get(column), errors="coerce")
    result["api_success"] = result.get("api_success", False).fillna(False).astype(bool)
    return result


def filter_observations(frame: pd.DataFrame, route_id: str, direction: str, start_date: date,
                        end_date: date, departure_time: str | None = None) -> pd.DataFrame:
    """Filter normalized data to one route, direction, date range, and optional slot."""
    result = frame[(frame["route_id"] == route_id) & (frame["direction"] == direction)
                   & (frame["date_local"] >= start_date) & (frame["date_local"] <= end_date)]
    if departure_time:
        result = result[result["departure_time"] == departure_time]
    return result.copy()


def successful_observations(frame: pd.DataFrame) -> pd.DataFrame:
    """Keep only completed observations with a usable traffic-aware duration."""
    return frame[frame["api_success"] & frame["duration_seconds"].notna()].copy()


def _quantile(series: pd.Series, value: float) -> float | None:
    return float(series.quantile(value)) if len(series) else None


def duration_statistics(frame: pd.DataFrame) -> dict[str, float | int | None]:
    """Calculate descriptive and reliability metrics for successful observations."""
    successful = successful_observations(frame)
    durations = successful["duration_seconds"].dropna()
    count = int(len(durations))
    if not count:
        return {"observation_count": 0, "unique_days": 0, "mean": None, "p25": None,
                "p50": None, "p75": None, "p90": None, "p95": None, "minimum": None,
                "maximum": None, "standard_deviation": None, "interquartile_range": None,
                "bad_day_spread": None, "p95_p50_spread": None, "p90_p50_ratio": None}
    p25, p50, p75, p90, p95 = (_quantile(durations, q) for q in (.25, .50, .75, .90, .95))
    return {"observation_count": count, "unique_days": int(successful["date_local"].nunique()),
            "mean": float(durations.mean()), "p25": p25, "p50": p50, "p75": p75,
            "p90": p90, "p95": p95, "minimum": float(durations.min()), "maximum": float(durations.max()),
            "standard_deviation": float(durations.std(ddof=1)) if count > 1 else None,
            "interquartile_range": p75 - p25, "bad_day_spread": p90 - p50,
            "p95_p50_spread": p95 - p50, "p90_p50_ratio": p90 / p50 if p50 else None}


def traffic_delay_statistics(frame: pd.DataFrame) -> dict[str, float | int | None]:
    """Derive traffic delay from the source durations when both are present."""
    successful = successful_observations(frame)
    delay = (successful["duration_seconds"] - successful["static_duration_seconds"]).dropna()
    if delay.empty:
        return {"delay_observation_count": 0, "average_traffic_delay": None,
                "median_traffic_delay": None, "p90_traffic_delay": None}
    return {"delay_observation_count": int(len(delay)), "average_traffic_delay": float(delay.mean()),
            "median_traffic_delay": _quantile(delay, .5), "p90_traffic_delay": _quantile(delay, .9)}


def threshold_probabilities(frame: pd.DataFrame,
                            thresholds_minutes: Iterable[int | float] = DEFAULT_THRESHOLDS_MINUTES) -> dict[float, float | None]:
    """Return P(duration > threshold) for each threshold, as a fraction from 0 to 1."""
    durations = successful_observations(frame)["duration_seconds"].dropna()
    return {float(minutes): (float((durations > float(minutes) * 60).mean()) if len(durations) else None)
            for minutes in thresholds_minutes}


def direction_for_slot(slot: datetime) -> str:
    """Mirror the collector's established 13:00--before-19:00 return rule."""
    return "return" if RETURN_START <= slot.time() < RETURN_END else "outbound"


def expected_slots(start_date: date, end_date: date, direction: str, timezone: str = "America/Los_Angeles",
                   departure_time: str | None = None) -> set[datetime]:
    """Return collection slots expected for the selected direction and optional time."""
    tz = ZoneInfo(timezone)
    expected: set[datetime] = set()
    current = start_date
    while current <= end_date:
        for slot in scheduled_slots(datetime.combine(current, time.min, tzinfo=tz)):
            if direction_for_slot(slot) != direction:
                continue
            if departure_time and slot.strftime("%H:%M") != departure_time:
                continue
            expected.add(slot)
        current += timedelta(days=1)
    return expected


def coverage_statistics(frame: pd.DataFrame, start_date: date, end_date: date, direction: str,
                        timezone: str = "America/Los_Angeles", departure_time: str | None = None) -> dict[str, float | int]:
    """Report expected, present, failed, and successful collection coverage."""
    expected = expected_slots(start_date, end_date, direction, timezone, departure_time)
    recorded = set(frame["scheduled_slot"].dropna())
    successful_slots = set(successful_observations(frame)["scheduled_slot"].dropna())
    expected_count = len(expected)
    recorded_count = len(recorded & expected)
    successful_count = len(successful_slots & expected)
    return {"expected_observations": expected_count, "recorded_observations": recorded_count,
            "successful_observations": successful_count, "failed_observations": max(recorded_count - successful_count, 0),
            "missing_observations": max(expected_count - recorded_count, 0),
            "coverage_percentage": (recorded_count / expected_count * 100) if expected_count else 0.0,
            "successful_coverage_percentage": (successful_count / expected_count * 100) if expected_count else 0.0}


def departure_time_summary(frame: pd.DataFrame,
                           thresholds_minutes: Iterable[int | float] = DEFAULT_THRESHOLDS_MINUTES) -> pd.DataFrame:
    """Summarize each available departure time, preserving sample sizes."""
    rows: list[dict[str, float | int | str | None]] = []
    for departure_time, group in frame.groupby("departure_time", sort=True):
        row: dict[str, float | int | str | None] = {"departure_time": departure_time}
        row.update(duration_statistics(group))
        for threshold, probability in threshold_probabilities(group, thresholds_minutes).items():
            row[f"over_{threshold:g}_minutes"] = probability
        rows.append(row)
    return pd.DataFrame(rows)
