"""Personal, read-only commute reliability dashboard entry point."""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import pandas as pd
import streamlit as st

from dashboard.data import fetch_observations
from dashboard.views.common import parse_thresholds
from dashboard.views.comparison import render_route_comparison
from dashboard.views.direction import render_direction

TIMEZONE = "America/Los_Angeles"


@st.cache_data(ttl=300, show_spinner=False)
def load_data(start_date: date, end_date: date, timezone: str) -> pd.DataFrame:
    """Load observations once and cache them briefly for interactive filtering."""
    return fetch_observations(start_date, end_date, timezone)


def main() -> None:
    st.set_page_config(page_title="Commute reliability", layout="wide")
    st.title("Commute reliability")
    st.caption(
        "Read-only analysis of collected traffic observations. "
        "Distribution and sample size matter more than a single score."
    )

    with st.sidebar:
        st.header("Navigation")
        view = st.radio("View", ["Route Comparison", "Outbound", "Return"], index=0)

        st.header("Filters")
        default_end = date.today()
        date_range = st.date_input(
            "Observation date range",
            value=(default_end - timedelta(days=30), default_end),
            max_value=default_end,
        )
        threshold_text = st.text_input(
            "Thresholds in minutes",
            "30, 45, 60, 75",
            help="Comma-separated positive whole minutes.",
        )

    if not isinstance(date_range, tuple) or len(date_range) != 2:
        st.info("Choose a start and end date to load observations.")
        return
    start_date, end_date = date_range
    if start_date > end_date:
        st.sidebar.error("The start date must be on or before the end date.")
        return

    st.sidebar.caption(
        f"{start_date:%b %-d, %Y} - {end_date:%b %-d, %Y} · "
        f"{(end_date - start_date).days + 1} days"
    )
    try:
        thresholds = parse_thresholds(threshold_text)
    except ValueError:
        st.sidebar.error(
            "Use comma-separated positive whole minutes, for example: 30, 45, 60, 75."
        )
        return

    try:
        frame = load_data(start_date, end_date, TIMEZONE)
    except Exception as exc:
        st.error(
            "Could not load observations. Check the dashboard_reader database "
            "connection in Streamlit Secrets and try again."
        )
        st.error(f"Details: {exc}")
        return

    observed_routes = set(frame["route_id"].dropna().unique()) if not frame.empty else set()
    available_routes = sorted({*(f"R{i}" for i in range(1, 7)), *observed_routes})

    with st.sidebar:
        if view != "Route Comparison":
            route_id = st.selectbox("Route", available_routes)
        if st.button("Refresh data", width="stretch"):
            load_data.clear()
            st.rerun()

    if view == "Outbound":
        render_direction(
            frame, route_id, "outbound", start_date, end_date, thresholds,
            timezone=TIMEZONE, default_time="09:30",
        )
    elif view == "Return":
        render_direction(
            frame, route_id, "return", start_date, end_date, thresholds,
            timezone=TIMEZONE, default_time="16:00",
        )
    else:
        render_route_comparison(
            frame, available_routes, start_date, end_date, thresholds,
            timezone=TIMEZONE,
        )


if __name__ == "__main__":
    main()
