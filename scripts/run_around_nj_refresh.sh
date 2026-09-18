#!/bin/bash
# Twice-daily Around New Jersey snapshot refresh.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
LOCK="/tmp/around-nj-refresh.lock"
PYTHON="${ROOT}/venv/bin/python"
LOG_DIR="${ROOT}/logs"
mkdir -p "$LOG_DIR" drafts

notify() {
  if command -v jawn-ops >/dev/null 2>&1; then
    jawn-ops telegram notify --message "$1" || true
  fi
}

exec 9>"$LOCK"
if ! flock -n 9; then
  echo "around-nj refresh already running" >&2
  exit 0
fi

if [ ! -x "$PYTHON" ]; then
  echo "missing venv python at $PYTHON" >&2
  notify "Around New Jersey refresh failed: missing venv python at $PYTHON."
  exit 1
fi

SCRAPED="${ROOT}/drafts/scraped_headlines.json"
SNAPSHOT="${ROOT}/drafts/snapshot.html"

set +e
"$PYTHON" "${ROOT}/scripts/scrape_partner_homepages.py" --output "$SCRAPED"
scrape_status=$?
set -e
BUILD_ARGS=(--output "$SNAPSHOT")
if [ "$scrape_status" -eq 0 ] && [ -f "$SCRAPED" ]; then
  BUILD_ARGS+=(--scraped-json "$SCRAPED")
fi

set +e
"$PYTHON" "${ROOT}/scripts/build_around_nj_demo.py" "${BUILD_ARGS[@]}"
build_status=$?
set -e
if [ "$build_status" -ne 0 ]; then
  notify "Around New Jersey snapshot build failed on officejawn (exit $build_status)."
  exit "$build_status"
fi
if [ "$scrape_status" -ne 0 ]; then
  echo "scrape failed ($scrape_status); RSS snapshot still built" >&2
  notify "Around New Jersey scrape failed (exit $scrape_status). RSS snapshot still built."
fi

if [ "${AROUND_NJ_PUBLISH:-0}" = "1" ]; then
  set +e
  "${ROOT}/scripts/publish_around_nj_snapshot.sh" "$SNAPSHOT"
  publish_status=$?
  set -e
  if [ "$publish_status" -ne 0 ]; then
    notify "Around New Jersey snapshot publish failed (exit $publish_status)."
    exit "$publish_status"
  fi
fi
