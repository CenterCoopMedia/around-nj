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
MAX_RUN_BATCHES = 40
MAX_BODY_BYTES = 64 * 1024
DEFAULT_URL = "https://cms-api.njpbs.org/cmsImportAroundNj"
TOKEN_RE = re.compile(r"^[A-Za-z0-9]{48}$")
FIELD_LIMITS = {
    "url": 2000,
    "canonicalUrl": 2000,
    "headline": 250,
    "outlet": 120,
    "byline": 120,
    "summary": 280,
    "county": 40,
}
REQUIRED_FIELDS = (
    "url",
    "canonicalUrl",
    "headline",
    "outlet",
    "partner",
    "publishedAt",
)


def run_id_for(generated_at: str) -> str:
    stamp = re.sub(r"[^A-Za-z0-9]", "", generated_at)[:24] or "undated"
    return f"around-nj-{stamp}"[:80]


def record_ok(story: object) -> bool:
    # Character limits are Unicode code points, the same count the import uses.
    if not isinstance(story, dict):
        return False
    for key in REQUIRED_FIELDS:
        if key not in story:
            return False
    if not isinstance(story.get("partner"), bool):
        return False
    for key, limit in FIELD_LIMITS.items():
        value = story.get(key)
        if value is None:
            continue
        if not isinstance(value, str) or not value or len(value) > limit:
            return False
    published_at = story.get("publishedAt")
    return isinstance(published_at, str) and bool(published_at)


def story_batches(
    stories: list[dict], run_id: str, generated_at: str
) -> list[list[dict]] | None:
    batches: list[list[dict]] = []
    current: list[dict] = []
    for story in stories:
        trial = [*current, story]
        body = {"runId": run_id, "generatedAt": generated_at, "stories": trial}
        encoded = json.dumps(body).encode("utf-8")
        if len(trial) <= BATCH_SIZE and len(encoded) <= MAX_BODY_BYTES:
            current = trial
            continue
        if not current:
            return None
        batches.append(current)
        current = [story]
        alone = {"runId": run_id, "generatedAt": generated_at, "stories": current}
        if len(json.dumps(alone).encode("utf-8")) > MAX_BODY_BYTES:
            return None
    if current:
        batches.append(current)
    return batches


def post_json(
    url: str, token: str, body: dict, opener=urllib.request.urlopen
) -> tuple[int, bytes]:
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
    except OSError as exc:
        return 0, str(exc)[:180].encode("utf-8", errors="replace")


def push_stories(
    url: str, token: str, payload: dict, opener=urllib.request.urlopen, sleep=time.sleep
) -> int:
    stories = payload.get("stories")
    if not isinstance(stories, list) or not stories:
        print("Around NJ Boardwalk push failed: story export is empty", file=sys.stderr)
        return 1
    if any(not record_ok(story) for story in stories):
        print(
            "Around NJ Boardwalk push failed: a story exceeds the import limits",
            file=sys.stderr,
        )
        return 1
    generated_at = str(payload.get("generatedAt") or "")
    run_id = run_id_for(generated_at)
    batches = story_batches(stories, run_id, generated_at)
    if batches is None:
        print(
            "Around NJ Boardwalk push failed: a story exceeds the import size",
            file=sys.stderr,
        )
        return 1
    if len(batches) > MAX_RUN_BATCHES:
        print(
            "Around NJ Boardwalk push failed: the run has too many batches",
            file=sys.stderr,
        )
        return 1
    sent = 0
    for batch in batches:
        body = {"runId": run_id, "generatedAt": generated_at, "stories": batch}
        status = 0
        raw = b""
        for attempt in range(4):
            status, raw = post_json(url, token, body, opener)
            if status not in (0, 429, 503):
                break
            sleep(min(2**attempt, 8))
        if status != 200:
            detail = raw.decode("utf-8", errors="replace")[:180].replace(
                token, "[redacted]"
            )
            label = f"HTTP {status}" if status else "transport error"
            print(f"Around NJ Boardwalk push failed: {label} {detail}", file=sys.stderr)
            return 1
        sent += len(batch)
    print(f"Around NJ Boardwalk push upserted {sent} stories")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stories", required=True)
    parser.add_argument(
        "--url", default=os.environ.get("AROUND_NJ_BOARDWALK_URL", DEFAULT_URL)
    )
    args = parser.parse_args(argv)
    raw_token = os.environ.get("AROUND_NJ_IMPORT_TOKEN")
    if raw_token is None:
        print(
            "Around NJ Boardwalk push skipped: import token is not set", file=sys.stderr
        )
        return 0
    token = raw_token.strip()
    if TOKEN_RE.fullmatch(token) is None:
        print(
            "Around NJ Boardwalk push failed: import token is not 48 letters or digits",
            file=sys.stderr,
        )
        return 1
    try:
        payload = json.loads(Path(args.stories).read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        print(
            "Around NJ Boardwalk push failed: story export is invalid", file=sys.stderr
        )
        return 1
    if not isinstance(payload, dict):
        print(
            "Around NJ Boardwalk push failed: story export is invalid", file=sys.stderr
        )
        return 1
    return push_stories(args.url, token, payload)


if __name__ == "__main__":
    raise SystemExit(main())
