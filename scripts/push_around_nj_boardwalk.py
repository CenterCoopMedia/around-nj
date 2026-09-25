#!/usr/bin/env python3
"""Push one Around NJ story export to the Boardwalk import endpoint."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BATCH_SIZE = 40
DEFAULT_URL = "https://cms-api.njpbs.org/cmsImportAroundNj"
TOKEN_RE = re.compile(r"^[A-Za-z0-9]{48}$")


def run_id_for(generated_at: str) -> str:
    stamp = re.sub(r"[^A-Za-z0-9]", "", generated_at)[:24] or "undated"
    return f"around-nj-{stamp}"[:80]


def post_json(url: str, token: str, body: dict, opener=urllib.request.urlopen) -> tuple[int, bytes]:
    data = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "CCM-AroundNJ/0.3",
        },
    )
    try:
        with opener(request, timeout=60) as response:
            return response.status, response.read(4096)
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(4096)


def push_stories(url: str, token: str, payload: dict, opener=urllib.request.urlopen, sleep=time.sleep) -> int:
    stories = payload.get("stories")
    if not isinstance(stories, list) or not stories:
        print("Around NJ Boardwalk push skipped: no stories", file=sys.stderr)
        return 0
    generated_at = str(payload.get("generatedAt") or "")
    run_id = run_id_for(generated_at)
    sent = 0
    for start in range(0, len(stories), BATCH_SIZE):
        batch = stories[start : start + BATCH_SIZE]
        body = {"runId": run_id, "generatedAt": generated_at, "stories": batch}
        status = 0
        raw = b""
        for attempt in range(4):
            status, raw = post_json(url, token, body, opener)
            if status != 429 and status != 503:
                break
            sleep(min(2 ** attempt, 8))
        if status != 200:
            detail = raw.decode("utf-8", errors="replace")[:180].replace(token, "[redacted]")
            print(f"Around NJ Boardwalk push failed: HTTP {status} {detail}", file=sys.stderr)
            return 1
        sent += len(batch)
    print(f"Around NJ Boardwalk push upserted {sent} stories")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stories", required=True)
    parser.add_argument("--url", default=os.environ.get("AROUND_NJ_BOARDWALK_URL", DEFAULT_URL))
    args = parser.parse_args(argv)
    token = os.environ.get("AROUND_NJ_IMPORT_TOKEN", "").strip()
    if not token:
        print("Around NJ Boardwalk push skipped: import token is not set", file=sys.stderr)
        return 0
    if TOKEN_RE.fullmatch(token) is None:
        print(
            "Around NJ Boardwalk push skipped: import token is not 48 letters or digits",
            file=sys.stderr,
        )
        return 0
    payload = json.loads(Path(args.stories).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        print("Around NJ Boardwalk push failed: story export is invalid", file=sys.stderr)
        return 1
    return push_stories(args.url, token, payload)


if __name__ == "__main__":
    raise SystemExit(main())
