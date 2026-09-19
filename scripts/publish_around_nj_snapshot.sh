#!/bin/bash
# Copy a built snapshot.html onto the gh-pages worktree and push.
set -euo pipefail

SNAPSHOT="${1:?snapshot html path}"
PAGES="${AROUND_NJ_PAGES:-$HOME/projects/around-nj-live}"

if [ ! -f "$SNAPSHOT" ]; then
  echo "missing snapshot $SNAPSHOT" >&2
  exit 1
fi
if ! git -C "$PAGES" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "missing gh-pages worktree at $PAGES" >&2
  exit 1
fi

branch="$(git -C "$PAGES" branch --show-current)"
if [ "$branch" != "gh-pages" ]; then
  echo "AROUND_NJ_PAGES must be checked out on gh-pages (got ${branch:-detached} at $PAGES)" >&2
  exit 1
fi

git -C "$PAGES" fetch origin refs/heads/gh-pages:refs/remotes/origin/gh-pages
git -C "$PAGES" merge --ff-only origin/gh-pages

dest="$PAGES/snapshot.html"
if [ -e "$dest" ] && [ ! -f "$dest" ] && [ ! -L "$dest" ]; then
  echo "refusing to replace non-file $dest" >&2
  exit 1
fi
tmp="$(mktemp "$PAGES/snapshot.html.tmp.XXXXXX")"
cp "$SNAPSHOT" "$tmp"
if [ -L "$dest" ]; then
  rm -f "$dest"
fi
mv -f "$tmp" "$dest"
git -C "$PAGES" add snapshot.html
if git -C "$PAGES" diff --cached --quiet; then
  echo "no snapshot changes"
  exit 0
fi
git -C "$PAGES" -c user.email="6799804+jamditis@users.noreply.github.com" \
  -c user.name="Joe Amditis" \
  commit -m "$(cat <<'EOF'
Refresh Around New Jersey snapshot.

[skip ci]
EOF
)"
git -C "$PAGES" push origin HEAD:gh-pages
