"""Outbound and return commute analysis view."""
from __future__ import annotations

from datetime import date

import altair as alt
import pandas as pd
import streamlit as st

from analysis.commute_metrics import (
    coverage_statistics,
    departure_time_summary,
    duration_statistics,
    filter_observations,
    threshold_probabilities,
    traffic_delay_statistics,
)
from .common import minutes, percentage, styled_dataframe


def _formatted_summary(summary: pd.DataFrame, thresholds: tuple[int, ...]) -> pd.DataFrame:
    if summary.empty:
        return summary
    columns = [
        "departure_time", "observation_count", "unique_days", "p50", "p90",
        "p95", "bad_day_spread", "p90_p50_ratio",
    ]
    result = summary[columns].copy().rename(columns={
        "departure_time": "Departure",
        "observation_count": "Successful observations",
        "unique_days": "Unique days",
        "p50": "P50", "p90": "P90", "p95": "P95",
        "bad_day_spread": "Bad-day spread",
        "p90_p50_ratio": "P90/P50 ratio",
    })
    for column in ("P50", "P90", "P95", "Bad-day spread"):
        result[column] = result[column].map(minutes)
    result["P90/P50 ratio"] = result["P90/P50 ratio"].map(
        lambda value: "—" if pd.isna(value) else f"{value:.2f}×"
    )
    for threshold in thresholds:
        source = f"over_{threshold}_minutes"
        if source in summary:
            result[f"> {threshold} min"] = summary[source].map(percentage)
    return result


def render_direction(
    frame: pd.DataFrame,
    route_id: str,
    direction: str,
    start_date: date,
    end_date: date,
    thresholds: tuple[int, ...],
    timezone: str = "America/Los_Angeles",
    default_time: str | None = None,
) -> None:
    """Render departure-slot summaries, reliability metrics, and distributions."""
    direction_data = filter_observations(frame, route_id, direction, start_date, end_date)
    slots = sorted(direction_data["departure_time"].dropna().unique())
    if not slots:
        st.info(f"No {direction} observations for {route_id} in this date range.")
        return

    summary = departure_time_summary(direction_data, thresholds)
    st.subheader("Departure-time comparison")
    st.caption("Percentiles use successful observations only. Counts and unique days are shown for every slot.")
    st.dataframe(styled_dataframe(_formatted_summary(summary, thresholds)), hide_index=True, width="stretch")

    default_index = slots.index(default_time) if default_time in slots else 0
    selected_slot = st.selectbox("Departure slot", slots, key=f"{direction}-slot", index=default_index)
    selected = filter_observations(frame, route_id, direction, start_date, end_date, selected_slot)
    stats = duration_statistics(selected)
    coverage = coverage_statistics(selected, start_date, end_date, direction, timezone, selected_slot)
    delays = traffic_delay_statistics(selected)

    st.subheader(f"{selected_slot} detail")
    if stats["observation_count"] < 20:
        st.warning(
            f"Small sample: percentile metrics below are based on {stats['observation_count']} "
            f"successful observations across {stats['unique_days']} days."
        )
    columns = st.columns(4)
    columns[0].metric("P50", minutes(stats["p50"]), f"n={stats['observation_count']}, {stats['unique_days']} days")
    columns[1].metric("P90", minutes(stats["p90"]), "Always read with sample size")
    columns[2].metric("Bad-day spread", minutes(stats["bad_day_spread"]), "P90 − P50")
    columns[3].metric("P90/P50 ratio", "—" if stats["p90_p50_ratio"] is None else f"{stats['p90_p50_ratio']:.2f}×")

    st.markdown("**Distribution and reliability**")
    metric_keys = (
        "mean", "p50", "p25", "p75", "p90", "p95", "minimum", "maximum",
        "standard_deviation", "interquartile_range", "p95_p50_spread",
    )
    metric_labels = (
        "Mean", "Median / P50", "P25", "P75", "P90", "P95", "Minimum",
        "Maximum", "Standard deviation", "IQR", "P95 − P50",
    )
    statistics = pd.DataFrame({
        "Metric": metric_labels,
        "Duration": [minutes(stats[key]) for key in metric_keys],
    })
    st.dataframe(styled_dataframe(statistics), hide_index=True, width="stretch")

    st.markdown("**Traffic delay**")
    st.caption(f"Calculated from traffic-aware minus static duration; n={delays['delay_observation_count']}.")
    delay_columns = st.columns(3)
    delay_columns[0].metric("Median traffic delay", minutes(delays["median_traffic_delay"]))
    delay_columns[1].metric("P90 traffic delay", minutes(delays["p90_traffic_delay"]))
    delay_columns[2].metric("Average traffic delay", minutes(delays["average_traffic_delay"]))

    st.markdown("**Chance of exceeding your thresholds**")
    probabilities = threshold_probabilities(selected, thresholds)
    probability_rows = pd.DataFrame({
        "Threshold": [f"> {threshold:g} min" for threshold in probabilities],
        "Probability": [percentage(value) for value in probabilities.values()],
        "Basis": [f"{stats['observation_count']} successful observations" for _ in probabilities],
    })
    st.dataframe(styled_dataframe(probability_rows), hide_index=True, width="stretch")

    st.markdown("**Data coverage**")
    coverage_columns = st.columns(4)
    coverage_columns[0].metric("Expected", coverage["expected_observations"])
    coverage_columns[1].metric("Recorded", coverage["recorded_observations"], f"{coverage['coverage_percentage']:.0f}% coverage")
    coverage_columns[2].metric("Missing", coverage["missing_observations"])
    coverage_columns[3].metric("Failed", coverage["failed_observations"], f"{coverage['successful_coverage_percentage']:.0f}% successful")

    successful = selected[selected["api_success"] & selected["duration_seconds"].notna()].copy()
    if not successful.empty:
        successful["Duration (minutes)"] = successful["duration_seconds"] / 60
        histogram = alt.Chart(successful).mark_bar().encode(
            alt.X("Duration (minutes):Q", bin=alt.Bin(maxbins=16), title="Commute duration (minutes)"),
            alt.Y("count():Q", title="Observations"),
            tooltip=[alt.Tooltip("count():Q", title="Observations")],
        ).properties(title=f"Observed duration distribution — {selected_slot}")
        st.altair_chart(histogram, width="stretch")

    box_data = direction_data[
        direction_data["api_success"] & direction_data["duration_seconds"].notna()
    ].copy()
    if not box_data.empty:
        box_data["Duration (minutes)"] = box_data["duration_seconds"] / 60
        box_plot = alt.Chart(box_data).mark_boxplot(size=16).encode(
            x=alt.X("departure_time:N", title="Departure slot", sort=slots),
            y=alt.Y("Duration (minutes):Q", title="Commute duration (minutes)"),
            tooltip=[
                alt.Tooltip("departure_time:N", title="Departure"),
                alt.Tooltip("Duration (minutes):Q", format=".1f"),
            ],
        ).properties(title="Duration distribution by departure slot")
        st.altair_chart(box_plot, width="stretch")
