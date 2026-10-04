# Traffic travel-time tracker

A private-route, traffic-aware commute observation system. The Python collector runs locally from Linux cron (or can run from the existing GitHub Actions workflow), converts the actual execution time to a Los Angeles sampling slot, avoids duplicates, queries Google Compute Routes, and writes only non-identifying measurements to Supabase.

## Setup

1. Create a Supabase project and run [`supabase_schema.sql`](supabase_schema.sql) in its SQL Editor.
2. In Google Cloud, enable **Routes API**, attach billing, create a server API key restricted to Routes API, and configure a budget alert and quota.
3. For local cron, create an owner-only environment file at `~/.config/traffic-collector/collector.env` from [`config/collector.env.example`](config/collector.env.example). It contains `GOOGLE_MAPS_API_KEY`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, and `ROUTES_JSON`.
4. Make `ROUTES_JSON` a compact private value such as `{"routes":[{"id":"R1","origin":"private origin","destination":"private destination"}]}`. Never commit it, a `.env`, addresses, or keys.
5. Install the local cron schedule described below. The GitHub Actions workflow remains in the repository unchanged; disable it in GitHub if you do not want a second runner attempting the same slots. The Supabase uniqueness constraint prevents duplicate measurements, but running both wastes API-request quota.

Only route IDs (`R1`–`R6`) and measurements reach `traffic_observations`; addresses are never logged or stored. Before each route call, the collector checks for an existing slot and atomically reserves a request in Supabase. Its unique `(route_id, scheduled_slot)` constraint makes retries idempotent.

## Schedule and commands

Scheduling uses `America/Los_Angeles`, including DST. Weekday windows are: 05:00–07:00 every 30 minutes; 07:00–10:00 every 15; 10:00–15:00 every 30; 15:00–19:00 every 15; and 19:00–22:00 every 30. The default seven-minute tolerance maps 07:14–07:17 to 07:15, while storing both actual and intended timestamps. Set `SLOT_TOLERANCE_MINUTES` (0–30) to change it.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export ROUTES_JSON='{"routes":[{"id":"R1","origin":"...","destination":"..."}]}'
python -m src.collector --dry-run
export GOOGLE_MAPS_API_KEY='...'; export SUPABASE_URL='https://<project>.supabase.co'; export SUPABASE_SERVICE_ROLE_KEY='...'
python -m src.collector --force
pytest -q
python analysis/analyze.py --route-id R1
python analysis/export_csv.py --route-id R1 --start-date 2026-09-01 --end-date 2026-09-30 --output traffic.csv
```

Dry run needs only `ROUTES_JSON` and writes/calls nothing. `--force` bypasses only scheduling. Export supports date, route, weekday, and time filters.

## Create and run the local dashboard

The repository includes a Streamlit dashboard in `dashboard/app.py` and a pure
analysis layer in `analysis/commute_metrics.py`. It is separate from the
collector, is read-only with respect to traffic observations, and shows matching
**Outbound** and **Return** tabs, plus a **Route comparison** tab. The comparison
tab shows `R1`–`R5` side by side for one selected direction and departure slot,
including percentiles, delay, threshold risk, sample size, and coverage without
inventing a single commute score. Directions follow the collector rule exactly:
13:00 through before 19:00 is return, and the other scheduled slots are outbound.

1. Create the existing collector configuration first, following the local cron
   setup below. The dashboard reads `SUPABASE_URL` and
   `SUPABASE_SERVICE_ROLE_KEY` from the
   existing owner-only collector file at `~/.config/traffic-collector/collector.env`.
   Its Python code only performs `select` queries; the key is never sent to the
   browser. Keep the dashboard bound to localhost or access it through an SSH
   tunnel.
2. From the repository root, install dependencies, make the runner executable,
   then start the dashboard:

```bash
cd "/path/to/Google Maps Route Duration"
.venv/bin/pip install -r requirements.txt
chmod +x scripts/run_dashboard.sh
scripts/run_dashboard.sh
```

The runner binds only to `127.0.0.1` by default. Open the Streamlit URL it
prints (normally `http://127.0.0.1:8501`) locally. If the collector server is
remote, create a tunnel from your computer, then open the same URL locally:

```bash
ssh -L 8501:127.0.0.1:8501 your-user@your-server
```

### Dashboard data caching

The dashboard fetches the selected date range from Supabase and caches that
result in the Streamlit process for **five minutes**. Switching route,
Outbound/Return tab, departure slot, or thresholds uses the cached frame and
does not make another Supabase request. Changing the date range uses a separate
cached entry and fetches only that new range. The **Refresh data** button clears
the cache and fetches again. Reads are paginated, so a selected range remains
complete after it grows past the API's default result page size.

## Local Linux cron

The local runner loads credentials from `~/.config/traffic-collector/collector.env`, writes operational output to `~/.local/state/traffic-collector/collector.log`, and uses `flock` so a delayed cron run cannot overlap the next one. It runs exactly at the valid weekday sampling slots in `America/Los_Angeles`, including across DST changes.

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
mkdir -p ~/.config/traffic-collector
cp config/collector.env.example ~/.config/traffic-collector/collector.env
chmod 600 ~/.config/traffic-collector/collector.env
# Edit collector.env locally with your real keys and routes.
chmod +x scripts/run_collector.sh scripts/install_cron.sh
scripts/run_collector.sh --dry-run
scripts/install_cron.sh
```

Confirm the installed schedule with `crontab -l`; watch runs with `tail -f ~/.local/state/traffic-collector/collector.log`. To remove it, run `crontab -e` and delete the lines from `# BEGIN traffic-collector` through `# END traffic-collector`. Cron must be enabled for your Linux user (for example, `systemctl status cron` or `systemctl status crond`).

## Cost and references

The default `MAX_MONTHLY_GOOGLE_REQUESTS=4500` applies a conservative request cap. Compute Routes is billed per request; `TRAFFIC_AWARE_OPTIMAL` is a higher-cost, higher-latency tier. Keep a Google Cloud budget alert and quota as independent safeguards. `duration` is traffic-aware and `staticDuration` is preserved so the collector calculates traffic delay.

Implementation follows Google’s [Compute Routes](https://developers.google.com/maps/documentation/routes/compute_route_directions), [traffic routing](https://developers.google.com/maps/documentation/routes/config_trade_offs), and [billing](https://developers.google.com/maps/documentation/routes/usage-and-billing) documentation, Supabase [Python guidance](https://supabase.com/docs/reference/python/installing), and GitHub [scheduled workflows](https://docs.github.com/actions/reference/events-that-trigger-workflows#schedule).
