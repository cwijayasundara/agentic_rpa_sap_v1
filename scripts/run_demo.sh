#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
# Start Fake-SAP in the background, then the web app in the foreground.
uv run uvicorn fake_sap.app:create_app --factory --port 8001 &
SAP_PID=$!
trap "kill $SAP_PID" EXIT
sleep 1
uv run uvicorn web.server:app --port 8000
