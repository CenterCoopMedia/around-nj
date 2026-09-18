#!/bin/bash
# Twice-daily Around New Jersey snapshot refresh.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
LOCK="/tmp/around-nj-refresh.lock"
PYTHON="${ROOT}/venv/bin/python"
LOG_DIR="${ROOT}/logs"
mkdir -p "$LOG_DIR" drafts

exec 9>"$LOCK"
if ! flock -n 9; then
  echo "around-nj refresh already running" >&2
  exit 0
fi

if [ ! -x "$PYTHON" ]; then
  echo "missing venv python at $PYTHON" >&2
  exit 1
fi

SCRAPED="${ROOT}/drafts/scraped_headlines.json"
SNAPSHOT="${ROOT}/drafts/snapshot.html"

set +e
"$PYTHON" "${ROOT}/scripts/scrape_partner_homepages.py" --output "$SCRAPED"
scrape_status=$?
set -e
BUILD_ARGS=(--output "$SNAPSHOT")
if [ -f "$SCRAPED" ]; then
  BUILD_ARGS+=(--scraped-json "$SCRAPED")
fi
"$PYTHON" "${ROOT}/scripts/build_around_nj_demo.py" "${BUILD_ARGS[@]}"
if [ "$scrape_status" -ne 0 ]; then
  echo "scrape failed ($scrape_status); RSS snapshot still built" >&2
fi

if [ "${AROUND_NJ_PUBLISH:-0}" = "1" ]; then
  "${ROOT}/scripts/publish_around_nj_snapshot.sh" "$SNAPSHOT"
fi
