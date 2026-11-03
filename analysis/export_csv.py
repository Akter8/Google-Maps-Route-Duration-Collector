"""Export observation data, with local filters, without exposing route locations."""
from __future__ import annotations
import argparse, os, sys
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from src.supabase_db import TrafficDatabase
def main() -> None:
    p=argparse.ArgumentParser(); p.add_argument("--output", default="traffic_observations.csv"); p.add_argument("--route-id"); p.add_argument("--start-date"); p.add_argument("--end-date"); p.add_argument("--weekday"); p.add_argument("--start-time"); p.add_argument("--end-time"); a=p.parse_args()
    rows=TrafficDatabase(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"]).fetch_observations({"route_id":a.route_id} if a.route_id else None)
    
    f = pd.DataFrame(rows)
    print(len(f))

    if not f.empty:
        f["scheduled_slot"] = pd.to_datetime(f["scheduled_slot"])
        f["date_local"] = f["date_local"].astype(str)

        if a.start_date:
            f = f[f["date_local"] >= a.start_date]

        if a.end_date:
            f = f[f["date_local"] <= a.end_date]

        if a.weekday:
            f = f[
                f["day_of_week"].str.lower() == a.weekday.lower()
            ]

        clock = f["scheduled_slot"].dt.strftime("%H:%M")

        if a.start_time:
            f = f[clock >= a.start_time]

        if a.end_time:
            f = f[clock <= a.end_time]

    f.to_csv(a.output, index=False)
    print(f"Exported {len(f)} rows to {a.output}")

if __name__ == "__main__": main()
