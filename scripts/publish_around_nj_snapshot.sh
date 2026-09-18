#!/bin/bash
# Copy a built snapshot.html onto the gh-pages worktree and push.
set -euo pipefail

SNAPSHOT="${1:?snapshot html path}"
PAGES="${AROUND_NJ_PAGES:-$HOME/projects/around-nj-pages}"

if [ ! -f "$SNAPSHOT" ]; then
  echo "missing snapshot $SNAPSHOT" >&2
  exit 1
fi
if [ ! -d "$PAGES/.git" ]; then
  echo "missing gh-pages worktree at $PAGES" >&2
  exit 1
fi

cp "$SNAPSHOT" "$PAGES/snapshot.html"
git -C "$PAGES" add snapshot.html
if git -C "$PAGES" diff --cached --quiet; then
  echo "no snapshot changes"
  exit 0
fi
git -C "$PAGES" -c user.email="6799804+jamditis@users.noreply.github.com" \
  -c user.name="Joe Amditis" \
  commit -m "Refresh Around New Jersey snapshot."
git -C "$PAGES" push origin gh-pages
