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

## Streamlit Community Cloud Deployment

The repository includes a Streamlit dashboard at `dashboard/app.py` and a pure
analysis layer at `analysis/commute_metrics.py`. It has Outbound, Return, and
Route comparison views. The dashboard is deployable directly from GitHub to
Streamlit Community Cloud: it never contacts the local collector, WireGuard, or
the local server. Supabase is the single source of truth:

```text
local collector (service_role write access) -> Supabase <- Streamlit dashboard (dashboard_reader SELECT only)
```

### Database identity (one-time Supabase setup)

1. Run [`supabase_schema.sql`](supabase_schema.sql) first if the tables do not
   already exist.
2. In the Supabase SQL Editor, open
   [`supabase_dashboard_reader.sql`](supabase_dashboard_reader.sql), replace
   `REPLACE_WITH_A_LONG_RANDOM_PASSWORD` with a newly generated password, and
   execute it manually. Do not save that edited script in Git.
3. The current schema does not enable RLS, so database grants are the access
   boundary for this direct PostgreSQL connection. The script creates
   `dashboard_reader` with `LOGIN`, `NOINHERIT`, no object
   creation/admin privileges, and only column-level `SELECT` on
   `public.traffic_observations`. It explicitly has no access to `api_usage`,
   sequences, or functions and no write privileges.
4. In Supabase **Connect**, select the Session Pooler connection details for an
   externally hosted application. Build a URL using `dashboard_reader`, that
   generated password, and `sslmode=require`. Do not use the Supabase REST URL,
   an API key, or `SUPABASE_SERVICE_ROLE_KEY` for the dashboard.

The SQL script ends with privilege checks. They should report `true` only for
`can_select_observations`; all other displayed permissions should be `false`.

### Streamlit Cloud secrets and deployment

1. Push this repository to GitHub without any credentials.
2. Create an app in Streamlit Community Cloud, select that repository/branch,
   and use `dashboard/app.py` as the entry point. Community Cloud installs
   [`requirements.txt`](requirements.txt), including the PostgreSQL driver.
3. In the app's **Settings → Secrets**, enter exactly this placeholder-shaped
   TOML with your real pooler URL only in the Cloud secret store:

```toml
[database]
url = "postgresql://dashboard_reader:YOUR_LONG_RANDOM_PASSWORD@YOUR_PROJECT_POOLER_HOST:5432/postgres?sslmode=require"
```

URL-encode the password if it contains URL-reserved characters such as `@`,
`:` or `/`.

4. Keep the app private and use Streamlit Community Cloud's sharing/access
   controls to invite only approved accounts. Do not make the app public: the
   underlying commute data is personal. Streamlit users receive rendered data
   only; they never receive the database URL or password.

To rotate access, run the commented `ALTER ROLE` command in
`supabase_dashboard_reader.sql` with a new password, then replace only the
Cloud/local secret and restart/redeploy the app. Remove access for departed
users in Streamlit Cloud as well.

### Local dashboard development

Copy the safe example and fill in the *dashboard_reader* Session Pooler URL;
do not copy collector credentials:

```bash
mkdir -p .streamlit
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
chmod 600 .streamlit/secrets.toml
# Edit .streamlit/secrets.toml locally with the dashboard_reader URL.
.venv/bin/pip install -r requirements.txt
scripts/run_dashboard.sh
```

`scripts/run_dashboard.sh` binds locally to `127.0.0.1`, but it does not read
`collector.env`; Cloud runs use Streamlit Secrets instead. If the secret is
missing, the app shows an actionable configuration error without displaying a
credential or connection URL.

### Dashboard reads and caching

For each selected date range the dashboard makes one parameterized `SELECT`
against the eight columns it needs, then calculates all filters, percentiles,
metrics, and charts locally with pandas. `st.cache_data` caches that result for
five minutes; the **Refresh data** button clears it. There is no arbitrary SQL
UI and no dashboard write path.

### Credential separation

- **Collector credentials:** `GOOGLE_MAPS_API_KEY`, `SUPABASE_URL`, and
  `SUPABASE_SERVICE_ROLE_KEY` stay in the local owner-only
  `~/.config/traffic-collector/collector.env`. They are never used by the
  dashboard or put in Streamlit Secrets.
- **Dashboard credentials:** only the `dashboard_reader` PostgreSQL URL belongs
  in Streamlit Secrets or local `.streamlit/secrets.toml`.
- Never commit `.streamlit/secrets.toml`, `.env` files, route addresses,
  passwords, database URLs containing passwords, API keys, or service-role
  keys. `.streamlit/secrets.toml` is ignored by Git.

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
