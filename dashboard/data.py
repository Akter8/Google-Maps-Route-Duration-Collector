"""Read-only Supabase access for the dashboard."""
from __future__ import annotations

import os
from datetime import date

import pandas as pd
from supabase import create_client

from analysis.commute_metrics import normalize_observations

READ_COLUMNS = ("route_id,direction,date_local,scheduled_slot,duration_seconds,"
                "static_duration_seconds,api_success,error_message")


def dashboard_client():
    """Create a server-only client from the collector's private environment."""
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required for the dashboard")
    return create_client(url, key)


def fetch_observations(start_date: date, end_date: date, timezone: str = "America/Los_Angeles") -> pd.DataFrame:
    """Fetch every row in a date range using bounded pagination."""
    client = dashboard_client()
    rows: list[dict] = []
    page_size, offset = 1000, 0
    while True:
        response = (client.table("traffic_observations").select(READ_COLUMNS)
                    .gte("date_local", start_date.isoformat()).lte("date_local", end_date.isoformat())
                    .order("scheduled_slot").range(offset, offset + page_size - 1).execute())
        page = response.data or []
        rows.extend(page)
        if len(page) < page_size:
            break
        offset += page_size
    return normalize_observations(pd.DataFrame(rows), timezone)
