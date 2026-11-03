#!/usr/bin/env bash
# Export traffic observations safely using the collector's configuration.
set -Eeuo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/traffic-collector"
ENV_FILE="${TRAFFIC_COLLECTOR_ENV_FILE:-$CONFIG_DIR/collector.env}"
PYTHON_BIN="${TRAFFIC_COLLECTOR_PYTHON:-$PROJECT_DIR/.venv/bin/python}"

if [[ ! -r "$ENV_FILE" ]]; then
  echo "Configuration file not found or unreadable: $ENV_FILE" >&2
  exit 2
fi

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Python executable not found: $PYTHON_BIN. Create .venv and install requirements first." >&2
  exit 2
fi

# Load the same environment used by the collector.
# shellcheck disable=SC1090
set -a
source "$ENV_FILE"
set +a

cd "$PROJECT_DIR"
exec "$PYTHON_BIN" "$PROJECT_DIR/analysis/export_csv.py" "$@"
