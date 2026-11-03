"""CLI entry point. It deliberately avoids logging private route locations."""
from __future__ import annotations
import argparse
import logging
from datetime import datetime, time, timezone
from .config import ConfigError, load_settings
from .google_routes import GoogleRoutesClient, GoogleRoutesError
from .scheduler import intended_slot, local_now
from .supabase_db import TrafficDatabase

LOG = logging.getLogger("traffic_collector")

def route_for_slot(route, slot: datetime) -> tuple[str, str, str]:
    """Return the direction and endpoints to query for a scheduled local slot."""
    if time(13) <= slot.time() < time(19):
        return "return", route.destination, route.origin
    return "outbound", route.origin, route.destination


def make_record(route_id: str, direction: str, actual: datetime, slot: datetime, estimate=None, error: str | None = None) -> dict:
    duration = estimate.duration_seconds if estimate else None
    static = estimate.static_duration_seconds if estimate else None
    return {"timestamp_utc": actual.astimezone(timezone.utc).isoformat(), "timestamp_local": actual.isoformat(),
            "date_local": actual.date().isoformat(), "day_of_week": actual.strftime("%A"),
            "scheduled_slot": slot.isoformat(), "route_id": route_id, "direction": direction, "duration_seconds": duration,
            "static_duration_seconds": static, "traffic_delay_seconds": (duration - static) if estimate else None,
            "distance_meters": estimate.distance_meters if estimate else None, "api_success": estimate is not None,
            "error_message": error}

def collect(settings, now: datetime | None = None, force: bool = False, dry_run: bool = False) -> int:
    LOG.info("")
    LOG.info("Starting new collect round.")
    LOG.info("Settings.max_monthly_google_requests: " + str(settings.max_monthly_google_requests))
    actual = now or local_now(settings.timezone)
    slot = intended_slot(actual, settings.slot_tolerance_minutes)
    if not slot and not force:
        LOG.info("No sampling slot is active; exiting without requests or writes.")
        return 0
    slot = slot or actual.replace(second=0, microsecond=0)
    LOG.info("Current time=%s slot=%s routes=%d", actual.strftime("%Y-%m-%d %H:%M:%S %Z"), slot.strftime("%Y-%m-%d %H:%M %Z"), len(settings.routes))
    if dry_run:
        LOG.info("Dry run: would query route IDs: %s", ", ".join(r.id for r in settings.routes))
        return 0
    db, google = TrafficDatabase(settings.supabase_url, settings.supabase_service_role_key), GoogleRoutesClient(settings.google_api_key)
    month = actual.strftime("%Y-%m")
    for route in settings.routes:
        try:
            if db.observation_exists(route.id, slot):
                LOG.info("%s: already recorded for slot", route.id)
                if force:
                    LOG.info("%s: force=True, will redo", route.id)
                else:
                    continue
            if not db.reserve_google_request(month, settings.max_monthly_google_requests):
                LOG.warning("Monthly Google request safety limit reached; stopping."); break
            direction, origin, destination = route_for_slot(route, slot)
            try:
                estimate = google.compute(origin, destination)
                db.upsert_observation(make_record(route.id, direction, actual, slot, estimate))
                LOG.info("%s: %.0fm %.0fs", route.id, estimate.duration_seconds // 60, estimate.duration_seconds % 60)
            except GoogleRoutesError as exc:
                db.upsert_observation(make_record(route.id, direction, actual, slot, error=str(exc)))
                LOG.warning("%s: request failed (%s)", route.id, exc)
        except Exception as exc:
            LOG.exception("%s: persistence failed (%s)", route.id, type(exc).__name__)
    return 0

def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--dry-run", action="store_true"); parser.add_argument("--force", action="store_true")
    args = parser.parse_args(); logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s: %(message)s")
    try: return collect(load_settings(require_services=not args.dry_run), force=args.force, dry_run=args.dry_run)
    except ConfigError as exc: LOG.error("Configuration error: %s", exc); return 2

if __name__ == "__main__": raise SystemExit(main())
