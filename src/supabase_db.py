"""Supabase Data API persistence; no route addresses are ever sent here."""
from __future__ import annotations
from dataclasses import asdict
from datetime import datetime
from typing import Any
from supabase import Client, create_client

class DatabaseError(RuntimeError): pass

class TrafficDatabase:
    def __init__(self, url: str, service_role_key: str) -> None:
        self.client: Client = create_client(url, service_role_key)

    @staticmethod
    def _data(response: Any) -> Any:
        if getattr(response, "data", None) is None: raise DatabaseError("Supabase returned no data")
        return response.data

    def observation_exists(self, route_id: str, slot: datetime) -> bool:
        response = self.client.table("traffic_observations").select("id").eq("route_id", route_id).eq("scheduled_slot", slot.isoformat()).limit(1).execute()
        return bool(self._data(response))

    def reserve_google_request(self, month: str, limit: int) -> bool:
        """Atomically increment only when below cap (requires schema RPC)."""
        result = self.client.rpc("reserve_google_request", {"p_month": month, "p_limit": limit}).execute()
        return bool(self._data(result))

    def upsert_observation(self, record: dict[str, Any]) -> None:
        self.client.table("traffic_observations").upsert(record, on_conflict="route_id,scheduled_slot").execute()

    def fetch_observations(
        self,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch all matching observations, handling Supabase pagination."""
        page_size = 1000
        offset = 0
        all_rows: list[dict[str, Any]] = []

        while True:
            query = (
                self.client.table("traffic_observations")
                .select("*")
                .order("scheduled_slot")
                .order("id")
                .range(offset, offset + page_size - 1)
            )

            for key, value in (filters or {}).items():
                if value is not None:
                    query = query.eq(key, value)

            rows = self._data(query.execute())
            all_rows.extend(rows)

            if len(rows) < page_size:
                break

            offset += page_size

        return all_rows

