"""Weekday-filtered route comparison view."""
from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from analysis.commute_metrics import (
    duration_statistics,
    expected_slots,
    filter_observations,
    threshold_probabilities,
    traffic_delay_statistics,
)
from .common import minutes, percentage, styled_comparison_dataframe

WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday")


def render_route_comparison(
    frame: pd.DataFrame,
    route_ids: list[str],
    start_date: date,
    end_date: date,
    thresholds: tuple[int, ...],
    timezone: str = "America/Los_Angeles",
) -> None:
    """Compare route reliability for a selected direction, slot, and weekdays."""
    st.subheader("Route comparison")
    st.caption("Compare routes at one departure slot. All metrics are recalculated using only the selected weekdays.")
    direction = st.radio("Direction", ("Outbound", "Return"), horizontal=True, key="comparison-direction").lower()
    slots = sorted({
        slot.strftime("%H:%M")
        for slot in expected_slots(start_date, end_date, direction, timezone)
    })
    if not slots:
        st.info("There are no scheduled collection slots for that direction in this date range.")
        return

    default_time = "09:30" if direction == "outbound" else "16:00"
    default_index = slots.index(default_time) if default_time in slots else 0
    departure_slot = st.selectbox("Departure slot", slots, key="comparison-slot", index=default_index)
    st.caption(f"{direction.title()} · {departure_slot} · {start_date:%b %-d} – {end_date:%b %-d, %Y}")

    st.markdown("**Include weekdays**")
    weekday_columns = st.columns(len(WEEKDAYS))
    selected_weekdays: list[str] = []
    for index, weekday in enumerate(WEEKDAYS):
        with weekday_columns[index]:
            if st.checkbox(weekday[:3], value=True, key=f"comparison-weekday-{weekday}"):
                selected_weekdays.append(weekday)
    if not selected_weekdays:
        st.info("Select at least one weekday to compare routes.")
        return

    expected = {
        slot for slot in expected_slots(start_date, end_date, direction, timezone, departure_slot)
        if slot.strftime("%A") in selected_weekdays
    }
    rows: list[dict[str, str | int]] = []
    matching_rows = 0
    for route_id in route_ids:
        selected = filter_observations(frame, route_id, direction, start_date, end_date, departure_slot)
        matching_rows += len(selected)
        selected = selected[
            pd.to_datetime(selected["date_local"]).dt.day_name().isin(selected_weekdays)
        ].copy()
        stats = duration_statistics(selected)
        delay = traffic_delay_statistics(selected)
        recorded_slots = set(selected["scheduled_slot"].dropna())
        successful = selected[selected["api_success"] & selected["duration_seconds"].notna()]
        successful_slots = set(successful["scheduled_slot"].dropna())

        expected_count = len(expected)
        recorded_count = len(recorded_slots & expected)
        successful_count = len(successful_slots & expected)
        coverage = recorded_count / expected_count * 100 if expected_count else 0.0
        row: dict[str, str | int] = {
            "Route": route_id,
            "Successful observations": stats["observation_count"],
            "Unique days": stats["unique_days"],
            "P50": minutes(stats["p50"]),
            "P90": minutes(stats["p90"]),
            "P95": minutes(stats["p95"]),
            "Bad-day spread": minutes(stats["bad_day_spread"]),
            "P90/P50 ratio": "—" if stats["p90_p50_ratio"] is None else f"{stats['p90_p50_ratio']:.2f}×",
            "Median traffic delay": minutes(delay["median_traffic_delay"]),
            "P90 traffic delay": minutes(delay["p90_traffic_delay"]),
            "Recorded / expected": f"{recorded_count} / {expected_count}",
            "Coverage": f"{coverage:.0f}%",
            "Missing": max(expected_count - recorded_count, 0),
            "Failed": max(recorded_count - successful_count, 0),
        }
        for threshold, probability in threshold_probabilities(selected, thresholds).items():
            row[f"> {threshold:g} min"] = percentage(probability)
        rows.append(row)

    if not rows:
        st.info("No routes are available for comparison.")
        return
    st.dataframe(
        styled_comparison_dataframe(pd.DataFrame(rows)),
        hide_index=True,
        width="stretch",
    )
    st.caption(f"Found {matching_rows} rows from the database matching the route, date, direction, and slot criteria.")
    st.caption(
        "Percentiles and threshold probabilities use successful observations only. "
        "Coverage is calculated against expected collection slots on the selected weekdays. "
        "Check sample size and unique days when comparing routes."
    )
