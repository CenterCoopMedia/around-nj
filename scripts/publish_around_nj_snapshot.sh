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

# Validate the whole bundle before replacing any output. index.html stays untouched.
SOURCE_DIR="$(dirname "$SNAPSHOT")"
FILES=(snapshot.html snapshot.json snapshot.md rss.xml)
for name in "${FILES[@]}"; do
  source="$SOURCE_DIR/$name"
  [ "$name" != snapshot.html ] || source="$SNAPSHOT"
  if [ ! -f "$source" ]; then
    echo "missing snapshot bundle file $source; rebuild before publishing" >&2
    exit 1
  fi
  dest="$PAGES/$name"
  if [ -e "$dest" ] && [ ! -f "$dest" ] && [ ! -L "$dest" ]; then
    echo "refusing to replace non-file $dest" >&2
    exit 1
  fi
done
# Never include an operator's unrelated staged edits in the refresh commit.
if ! git -C "$PAGES" diff --cached --quiet; then
  echo "refusing to publish with staged changes in $PAGES" >&2
  exit 1
fi
for name in "${FILES[@]}"; do
  source="$SOURCE_DIR/$name"
  [ "$name" != snapshot.html ] || source="$SNAPSHOT"
  dest="$PAGES/$name"
  tmp="$(mktemp "$PAGES/$name.tmp.XXXXXX")"
  cp "$source" "$tmp"
  if [ -L "$dest" ]; then
    rm -f "$dest"
  fi
  mv -f "$tmp" "$dest"
done
git -C "$PAGES" add -- "${FILES[@]}"
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
