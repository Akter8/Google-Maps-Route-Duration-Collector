"""Personal, read-only commute reliability dashboard."""
from __future__ import annotations

import os
from datetime import date, timedelta

import altair as alt
import pandas as pd
import streamlit as st

from analysis.commute_metrics import (
    coverage_statistics, departure_time_summary, duration_statistics, filter_observations,
    expected_slots, threshold_probabilities, traffic_delay_statistics,
)
from dashboard.data import fetch_observations

TIMEZONE = os.getenv("TRAFFIC_TIMEZONE", "America/Los_Angeles")


@st.cache_data(ttl=300, show_spinner=False)
def load_data(start_date: date, end_date: date, timezone: str) -> pd.DataFrame:
    return fetch_observations(start_date, end_date, timezone)


def minutes(value: float | None) -> str:
    return "—" if value is None or pd.isna(value) else f"{value / 60:.1f} min"


def percentage(value: float | None) -> str:
    return "—" if value is None or pd.isna(value) else f"{value:.0%}"


def parse_thresholds(raw: str) -> tuple[int, ...]:
    values = tuple(sorted({int(item.strip()) for item in raw.split(",") if item.strip()}))
    if not values or any(value <= 0 for value in values):
        raise ValueError
    return values


def formatted_summary(summary: pd.DataFrame, thresholds: tuple[int, ...]) -> pd.DataFrame:
    if summary.empty:
        return summary
    result = summary[["departure_time", "observation_count", "unique_days", "p50", "p90", "p95",
                      "bad_day_spread", "p90_p50_ratio"]].copy()
    result = result.rename(columns={"departure_time": "Departure", "observation_count": "Successful observations",
                                    "unique_days": "Unique days", "p50": "P50", "p90": "P90", "p95": "P95",
                                    "bad_day_spread": "Bad-day spread", "p90_p50_ratio": "P90/P50 ratio"})
    for column in ("P50", "P90", "P95", "Bad-day spread"):
        result[column] = result[column].map(minutes)
    result["P90/P50 ratio"] = result["P90/P50 ratio"].map(lambda value: "—" if pd.isna(value) else f"{value:.2f}×")
    for threshold in thresholds:
        source = f"over_{threshold}_minutes"
        if source in summary:
            result[f"> {threshold} min"] = summary[source].map(percentage)
    return result


def render_direction(frame: pd.DataFrame, route_id: str, direction: str, start_date: date,
                     end_date: date, thresholds: tuple[int, ...]) -> None:
    direction_data = filter_observations(frame, route_id, direction, start_date, end_date)
    slots = sorted(direction_data["departure_time"].dropna().unique())
    if not slots:
        st.info(f"No {direction} observations for {route_id} in this date range.")
        return

    summary = departure_time_summary(direction_data, thresholds)
    st.subheader("Departure-time comparison")
    st.caption("Percentiles use successful observations only. Counts and unique days are shown for every slot.")
    st.dataframe(formatted_summary(summary, thresholds), hide_index=True, use_container_width=True)

    selected_slot = st.selectbox("Departure slot", slots, key=f"{direction}-slot")
    selected = filter_observations(frame, route_id, direction, start_date, end_date, selected_slot)
    stats = duration_statistics(selected)
    coverage = coverage_statistics(selected, start_date, end_date, direction, TIMEZONE, selected_slot)
    delays = traffic_delay_statistics(selected)

    st.subheader(f"{selected_slot} detail")
    if stats["observation_count"] < 20:
        st.warning(f"Small sample: percentile metrics below are based on {stats['observation_count']} successful observations across {stats['unique_days']} days.")
    metric_columns = st.columns(4)
    metric_columns[0].metric("P50", minutes(stats["p50"]), f"n={stats['observation_count']}, {stats['unique_days']} days")
    metric_columns[1].metric("P90", minutes(stats["p90"]), "Always read with sample size")
    metric_columns[2].metric("Bad-day spread", minutes(stats["bad_day_spread"]), "P90 − P50")
    metric_columns[3].metric("P90/P50 ratio", "—" if stats["p90_p50_ratio"] is None else f"{stats['p90_p50_ratio']:.2f}×")

    st.markdown("**Distribution and reliability**")
    statistics_table = pd.DataFrame({"Metric": ["Mean", "Median / P50", "P25", "P75", "P90", "P95", "Minimum", "Maximum", "Standard deviation", "IQR", "P95 − P50"],
                                     "Duration": [minutes(stats[key]) for key in ("mean", "p50", "p25", "p75", "p90", "p95", "minimum", "maximum", "standard_deviation", "interquartile_range", "p95_p50_spread")]})
    st.dataframe(statistics_table, hide_index=True, use_container_width=True)

    st.markdown("**Traffic delay**")
    st.caption(f"Calculated from traffic-aware minus static duration; n={delays['delay_observation_count']}.")
    delay_columns = st.columns(3)
    delay_columns[0].metric("Median traffic delay", minutes(delays["median_traffic_delay"]))
    delay_columns[1].metric("P90 traffic delay", minutes(delays["p90_traffic_delay"]))
    delay_columns[2].metric("Average traffic delay", minutes(delays["average_traffic_delay"]))

    st.markdown("**Chance of exceeding your thresholds**")
    probabilities = threshold_probabilities(selected, thresholds)
    probability_rows = pd.DataFrame({"Threshold": [f"> {threshold:g} min" for threshold in probabilities],
                                     "Probability": [percentage(value) for value in probabilities.values()],
                                     "Basis": [f"{stats['observation_count']} successful observations" for _ in probabilities]})
    st.dataframe(probability_rows, hide_index=True, use_container_width=True)

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
        st.altair_chart(histogram, use_container_width=True)

    box_data = direction_data[direction_data["api_success"] & direction_data["duration_seconds"].notna()].copy()
    if not box_data.empty:
        box_data["Duration (minutes)"] = box_data["duration_seconds"] / 60
        box_plot = alt.Chart(box_data).mark_boxplot(size=16).encode(
            x=alt.X("departure_time:N", title="Departure slot", sort=slots),
            y=alt.Y("Duration (minutes):Q", title="Commute duration (minutes)"),
            tooltip=[alt.Tooltip("departure_time:N", title="Departure"), alt.Tooltip("Duration (minutes):Q", format=".1f")],
        ).properties(title="Duration distribution by departure slot")
        st.altair_chart(box_plot, use_container_width=True)


def render_route_comparison(frame: pd.DataFrame, route_ids: list[str], start_date: date,
                            end_date: date, thresholds: tuple[int, ...]) -> None:
    """Compare every configured candidate route at one direction and time."""
    st.subheader("Route comparison")
    st.caption("Compare candidate routes at one departure slot. This table intentionally shows the separate reliability measures instead of producing a commute score.")
    direction = st.radio("Direction", ("outbound", "return"), horizontal=True, key="comparison-direction")
    slots = sorted({slot.strftime("%H:%M") for slot in expected_slots(start_date, end_date, direction, TIMEZONE)})
    if not slots:
        st.info("There are no scheduled collection slots for that direction in this date range.")
        return
    departure_slot = st.selectbox("Departure slot", slots, key="comparison-slot")
    rows: list[dict[str, str | float | int]] = []
    for route_id in route_ids:
        selected = filter_observations(frame, route_id, direction, start_date, end_date, departure_slot)
        stats = duration_statistics(selected)
        delay = traffic_delay_statistics(selected)
        coverage = coverage_statistics(selected, start_date, end_date, direction, TIMEZONE, departure_slot)
        row: dict[str, str | float | int] = {
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
            "Recorded / expected": f"{coverage['recorded_observations']} / {coverage['expected_observations']}",
            "Coverage": f"{coverage['coverage_percentage']:.0f}%",
            "Missing": coverage["missing_observations"],
            "Failed": coverage["failed_observations"],
        }
        for threshold, probability in threshold_probabilities(selected, thresholds).items():
            row[f"> {threshold:g} min"] = percentage(probability)
        rows.append(row)
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
    st.caption("Percentile and threshold metrics use successful observations only. Treat routes with small sample sizes or low coverage as less certain.")


def main() -> None:
    st.set_page_config(page_title="Commute reliability", layout="wide")
    st.title("Commute reliability")
    st.caption("Read-only analysis of collected traffic observations. Distribution and sample size matter more than a single score.")

    with st.sidebar:
        st.header("Filters")
        default_end = date.today()
        date_range = st.date_input("Observation date range", value=(default_end - timedelta(days=30), default_end), max_value=default_end)
        threshold_text = st.text_input("Thresholds in minutes", "30, 45, 60, 75", help="Comma-separated positive whole minutes.")
    if not isinstance(date_range, tuple) or len(date_range) != 2:
        st.info("Choose a start and end date to load observations.")
        return
    start_date, end_date = date_range
    try:
        thresholds = parse_thresholds(threshold_text)
    except ValueError:
        st.sidebar.error("Use comma-separated positive whole minutes, for example: 30, 45, 60, 75.")
        return
    try:
        frame = load_data(start_date, end_date, TIMEZONE)
    except Exception as exc:
        st.error(f"Could not load observations: {exc}")
        return
    observed_routes = set(frame["route_id"].dropna().unique()) if not frame.empty else set()
    available_routes = sorted({*(f"R{i}" for i in range(1, 6)), *observed_routes})
    with st.sidebar:
        route_id = st.selectbox("Route", available_routes)
        if st.button("Refresh data"):
            load_data.clear()
            st.rerun()
    outbound, returning, comparison = st.tabs(["Outbound", "Return", "Route comparison"])
    with outbound:
        render_direction(frame, route_id, "outbound", start_date, end_date, thresholds)
    with returning:
        render_direction(frame, route_id, "return", start_date, end_date, thresholds)
    with comparison:
        render_route_comparison(frame, available_routes, start_date, end_date, thresholds)


if __name__ == "__main__":
    main()
