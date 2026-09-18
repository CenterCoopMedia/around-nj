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

"$PYTHON" "${ROOT}/scripts/scrape_partner_homepages.py" --output "$SCRAPED"
"$PYTHON" "${ROOT}/scripts/build_around_nj_demo.py" \
  --scraped-json "$SCRAPED" \
  --output "$SNAPSHOT"

if [ "${AROUND_NJ_PUBLISH:-0}" = "1" ]; then
  "${ROOT}/scripts/publish_around_nj_snapshot.sh" "$SNAPSHOT"
fi
