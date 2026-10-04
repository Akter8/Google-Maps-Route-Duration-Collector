#!/usr/bin/env bash
# Run the read-only dashboard locally on the same server as the collector.
set -Eeuo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/traffic-collector"
ENV_FILE="${TRAFFIC_DASHBOARD_ENV_FILE:-$CONFIG_DIR/collector.env}"
PYTHON_BIN="${TRAFFIC_DASHBOARD_PYTHON:-$PROJECT_DIR/.venv/bin/python}"

if [[ ! -r "$ENV_FILE" ]]; then
  echo "Collector configuration file not found or unreadable: $ENV_FILE" >&2
  exit 2
fi
if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Python executable not found: $PYTHON_BIN. Create .venv and install requirements first." >&2
  exit 2
fi

set -a
# The environment file is owner-controlled; do not put commands in it.
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

cd "$PROJECT_DIR"
exec "$PYTHON_BIN" -m streamlit run dashboard/app.py --server.address 127.0.0.1 "$@"
