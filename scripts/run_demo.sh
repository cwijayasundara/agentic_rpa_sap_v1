#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

# Ports (override via env, e.g. SAP_PORT=8001 WEB_PORT=8080 bash scripts/run_demo.sh)
SAP_PORT="${SAP_PORT:-8001}"
WEB_PORT="${WEB_PORT:-8080}"
# Keep the web app's view of Fake-SAP in sync with the chosen SAP_PORT.
export FAKE_SAP_BASE_URL="http://127.0.0.1:${SAP_PORT}"

# Start Fake-SAP in the background, then the web app in the foreground.
uv run uvicorn fake_sap.app:create_app --factory --port "$SAP_PORT" &
SAP_PID=$!
trap "kill $SAP_PID" EXIT
sleep 1
echo "Fake-SAP on :$SAP_PORT  |  Web UI on http://127.0.0.1:$WEB_PORT"
uv run uvicorn web.server:app --port "$WEB_PORT"
