"""Read-only PostgreSQL access for the Streamlit dashboard.

This module deliberately does not share the collector's Supabase Data API
client: the dashboard authenticates as the narrowly scoped ``dashboard_reader``
database role instead.
"""
from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd
import psycopg
import streamlit as st
from psycopg.rows import dict_row

from analysis.commute_metrics import normalize_observations

READ_COLUMNS = ("route_id, direction, date_local, scheduled_slot, duration_seconds, "
                "static_duration_seconds, api_success, error_message")
READ_OBSERVATIONS_SQL = f"""
SELECT {READ_COLUMNS}
FROM public.traffic_observations
WHERE date_local >= %s AND date_local <= %s
ORDER BY scheduled_slot ASC
"""


class DashboardConfigurationError(RuntimeError):
    """Raised without revealing credentials when Streamlit secrets are absent."""


def database_url(secrets: Any | None = None) -> str:
    """Read the dashboard-only connection URL from Streamlit secrets."""
    source = st.secrets if secrets is None else secrets
    try:
        url = source["database"]["url"]
    except (KeyError, TypeError) as exc:
        raise DashboardConfigurationError(
            "Dashboard database credentials are not configured. Add [database] url "
            "to Streamlit Secrets (or .streamlit/secrets.toml locally); never use "
            "the collector's SUPABASE_SERVICE_ROLE_KEY here."
        ) from exc
    if not isinstance(url, str) or not url.strip():
        raise DashboardConfigurationError(
            "Dashboard database credentials are not configured. Set database.url in "
            "Streamlit Secrets to the dashboard_reader PostgreSQL connection URL."
        )
    return url


def query_observations(connection: Any, start_date: date, end_date: date) -> list[dict[str, Any]]:
    """Execute the dashboard's single parameterized, SELECT-only query."""
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(READ_OBSERVATIONS_SQL, (start_date, end_date))
        return list(cursor.fetchall())


def fetch_observations(start_date: date, end_date: date, timezone: str = "America/Los_Angeles") -> pd.DataFrame:
    """Fetch the selected range once; all dashboard analysis happens locally."""
    if start_date > end_date:
        raise ValueError("The observation start date must not be after the end date.")
    with psycopg.connect(database_url(), autocommit=True) as connection:
        rows = query_observations(connection, start_date, end_date)
    return normalize_observations(pd.DataFrame(rows), timezone)
