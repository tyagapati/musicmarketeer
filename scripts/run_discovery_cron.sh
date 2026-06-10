#!/usr/bin/env bash
# Weekly discovery cron (Linux/macOS/Render).
set -euo pipefail
APP_URL="${APP_URL:-http://127.0.0.1:8000}"
if [ -z "${DISCOVERY_CRON_SECRET:-}" ]; then
  echo "DISCOVERY_CRON_SECRET is not set." >&2
  exit 1
fi
curl -fsS -X POST -H "X-Cron-Secret: ${DISCOVERY_CRON_SECRET}" "${APP_URL}/admin/ingest"
