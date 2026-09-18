#!/usr/bin/env python3
"""Scrape no-RSS partner homepages with Firecrawl for recent headlines."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from build_around_nj_demo import valid_story_link  # noqa: E402

PASS_GET = Path.home() / ".claude" / "pass-get"
FIRECRAWL_PASS = "claude/api/firecrawl"
TIMEOUT_SECONDS = 120


def load_api_key() -> None:
    if os.environ.get("FIRECRAWL_API_KEY"):
        return
    if not PASS_GET.exists():
        return
    try:
        key = (
            subprocess.check_output(
                [str(PASS_GET), FIRECRAWL_PASS],
                timeout=8,
                stderr=subprocess.DEVNULL,
            )
            .decode()
            .strip()
        )
    except Exception:
        return
    if key:
        os.environ["FIRECRAWL_API_KEY"] = key


def parse_firecrawl_payload(data: object) -> list[dict]:
    if not isinstance(data, dict):
        return []
    nested = data.get("json") if isinstance(data.get("json"), dict) else {}
    stories = data.get("stories") or nested.get("stories") or []
    if not isinstance(stories, list):
        return []
    out = []
    for item in stories:
        if not isinstance(item, dict):
            continue
        title = " ".join(str(item.get("title") or "").split()).strip()
        url = valid_story_link(str(item.get("url") or "").strip())
        if not title or not url:
            continue
        out.append(
            {
                "title": title,
                "url": url,
                "published": str(item.get("published") or "").strip() or None,
            }
        )
    return out


def scrape_home(url: str, schema: Path) -> dict:
    with tempfile.TemporaryDirectory(prefix="around-nj-fc-") as tmp:
        out = Path(tmp) / "out.json"
        cmd = [
            "firecrawl",
            "scrape",
            url,
            "--only-main-content",
            "--wait-for",
            "2500",
            "--format",
            "json",
            "--schema-file",
            str(schema),
            "-o",
            str(out),
        ]
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
            env=os.environ.copy(),
        )
        if proc.returncode != 0 or not out.exists():
            err = (proc.stderr or proc.stdout or "scrape failed").strip().splitlines()
            safe = err[-1][:160] if err else "scrape failed"
            return {"ok": False, "stories": [], "error": safe}
        payload = json.loads(out.read_text(encoding="utf-8"))
        stories = parse_firecrawl_payload(payload)
        return {"ok": True, "stories": stories, "error": None}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        default=str(ROOT / "drafts" / "scraped_headlines.json"),
    )
    parser.add_argument(
        "--limit", type=int, default=0, help="Scrape at most N sites (0=all)"
    )
    args = parser.parse_args()
    load_api_key()
    if not os.environ.get("FIRECRAWL_API_KEY"):
        raise SystemExit("FIRECRAWL_API_KEY is not set")

    partners = json.loads(
        (ROOT / "config" / "pbs_partners.json").read_text(encoding="utf-8")
    )
    schema = ROOT / "config" / "headline_schema.json"
    targets = []
    for partner in partners:
        if partner.get("snapshot") is False:
            continue
        scrape = partner.get("scrape")
        if not scrape:
            continue
        targets.append(partner)
    if args.limit:
        targets = targets[: args.limit]

    results = []
    for partner in targets:
        url = partner["scrape"]
        print(f"scrape {partner['org']}: {url}", flush=True)
        hit = scrape_home(url, schema)
        results.append(
            {
                "org": partner["org"],
                "url": url,
                "ok": hit["ok"],
                "error": hit["error"],
                "stories": [
                    {**story, "source": partner["org"], "partner": True}
                    for story in hit["stories"]
                ],
            }
        )
        print(
            f"  {'ok' if hit['ok'] else 'fail'} {len(hit['stories'])} stories"
            + (f" ({hit['error']})" if hit["error"] else ""),
            flush=True,
        )

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "results": results,
    }
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
