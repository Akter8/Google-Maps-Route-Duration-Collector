#!/usr/bin/env bash
# Run the dashboard locally. It reads only .streamlit/secrets.toml, never collector.env.
set -Eeuo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${TRAFFIC_DASHBOARD_PYTHON:-$PROJECT_DIR/.venv/bin/python}"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/traffic-collector"
STATE_DIR="${TRAFFIC_COLLECTOR_STATE_DIR:-${XDG_STATE_HOME:-$HOME/.local/state}/traffic-collector}"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Python executable not found: $PYTHON_BIN. Create .venv and install requirements first." >&2
  exit 2
fi

cd "$PROJECT_DIR"
exec "$PYTHON_BIN" -m streamlit run dashboard/app.py --server.address 127.0.0.1 "$@" >> "$STATE_DIR/dashboard.log" 2>&1
