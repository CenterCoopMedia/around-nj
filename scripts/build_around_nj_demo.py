#!/usr/bin/env python3
"""Build the Around New Jersey headlines snapshot for GitHub Pages."""

from __future__ import annotations

import argparse
import html
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlparse

import feedparser
import requests

ROOT = Path(__file__).resolve().parents[1]
LOOKBACK_HOURS = 72
TIMEOUT = 10
UA = "CCM-DNR-demo/0.2 (+https://centerforcooperativemedia.org)"
MAX_LIST = 80


def domain(url: str | None) -> str:
    if not url:
        return ""
    try:
        return urlparse(url).netloc.lower().replace("www.", "")
    except Exception:
        return ""


def parse_when(entry) -> datetime | None:
    for key in ("published", "updated"):
        raw = entry.get(key)
        if not raw:
            continue
        try:
            dt = parsedate_to_datetime(raw)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception:
            pass
    for key in ("published_parsed", "updated_parsed"):
        parsed = entry.get(key)
        if parsed:
            try:
                return datetime(*parsed[:6], tzinfo=timezone.utc)
            except Exception:
                pass
    return None


def fetch_feed(session: requests.Session, url: str, source: str) -> dict:
    result = {"source": source, "url": url, "ok": False, "items": [], "error": None}
    try:
        response = session.get(url, timeout=TIMEOUT, allow_redirects=True)
        if response.status_code >= 400:
            result["error"] = f"http {response.status_code}"
            return result
        parsed = feedparser.parse(response.content)
        cutoff = datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HOURS)
        items = []
        for entry in parsed.entries:
            title = re.sub(r"\s+", " ", (entry.get("title") or "").strip())
            link = (entry.get("link") or "").strip()
            if not title or not link:
                continue
            if urlparse(link).scheme not in ("http", "https"):
                continue
            when = parse_when(entry)
            if when is None or when < cutoff:
                continue
            items.append(
                {
                    "title": title,
                    "url": link,
                    "when": when.isoformat(),
                    "source": source,
                }
            )
        result["ok"] = True
        result["items"] = items
        return result
    except Exception as exc:
        result["error"] = type(exc).__name__
        return result


def fmt_when(iso: str | None) -> str:
    if not iso:
        return ""
    try:
        dt = datetime.fromisoformat(iso).astimezone()
        hour = dt.strftime("%I").lstrip("0") or "12"
        return f"{dt.strftime('%a')} {hour}:{dt.strftime('%M %p')}"
    except Exception:
        return iso[:16]


def fmt_now(dt: datetime) -> str:
    hour = dt.strftime("%I").lstrip("0") or "12"
    return (
        f"{dt.strftime('%A, %B')} {dt.day}, {dt.year}, {hour}:{dt.strftime('%M %p %Z')}"
    )


def story_li(story: dict, partner: bool) -> str:
    cls = "is-partner" if partner else "is-other"
    star = (
        '<span class="star" title="News Commons partner">Partner</span>'
        if partner
        else ""
    )
    when = fmt_when(story.get("when"))
    return (
        f'<li class="{cls}">{star}<a href="{html.escape(story["url"])}">'
        f"{html.escape(story['title'])}</a>"
        f' <span class="src">{html.escape(story["source"])}</span>'
        f' <span class="when">{html.escape(when)}</span></li>'
    )


def is_partner(story: dict, partner_names: set[str], partner_domains: set[str]) -> bool:
    src = (story.get("source") or "").lower()
    d = domain(story.get("url"))
    if src in partner_names or any(
        name in src for name in partner_names if len(name) > 8
    ):
        return True
    return bool(d) and any(d == pd or d.endswith("." + pd) for pd in partner_domains)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        default=str(ROOT / "drafts" / "around-nj-demo.html"),
        help="HTML output path",
    )
    args = parser.parse_args()

    feeds_cfg = json.loads((ROOT / "config" / "rss_feeds.json").read_text())
    partners = json.loads((ROOT / "config" / "pbs_partners.json").read_text())
    template = (ROOT / "scripts" / "around_nj_template.html").read_text()

    dnr_feeds = []
    for items in feeds_cfg.get("feeds", {}).values():
        for feed in items:
            if feed.get("rss_url"):
                dnr_feeds.append(feed)

    jobs = [(f["rss_url"], f["name"]) for f in dnr_feeds]
    seen = {url for url, _ in jobs}
    for partner in partners:
        rss = partner.get("rss")
        if rss and rss not in seen:
            jobs.append((rss, partner["org"]))
            seen.add(rss)

    session = requests.Session()
    session.headers.update({"User-Agent": UA})
    stories: list[dict] = []
    failures: list[dict] = []
    with ThreadPoolExecutor(max_workers=16) as pool:
        futs = {
            pool.submit(fetch_feed, session, url, name): (url, name)
            for url, name in jobs
        }
        for fut in as_completed(futs):
            result = fut.result()
            if result["ok"]:
                stories.extend(result["items"])
            else:
                failures.append(result)
    if failures:
        print(f"feed failures: {len(failures)}/{len(jobs)}")
        for failure in failures[:12]:
            print(f"  {failure['source']}: {failure['error']}")
    if failures and len(failures) * 2 >= len(jobs):
        raise SystemExit("too many feed failures to publish a snapshot")
    if not stories:
        raise SystemExit("no stories fetched")

    partner_names = {p["org"].lower() for p in partners}
    partner_domains = set()
    for partner in partners:
        if partner.get("star_domain"):
            partner_domains.add(partner["star_domain"])
        if partner.get("home"):
            partner_domains.add(domain(partner["home"]))

    unique = []
    seen_urls = set()
    for story in sorted(stories, key=lambda s: s.get("when") or "", reverse=True):
        if story["url"] in seen_urls:
            continue
        seen_urls.add(story["url"])
        story["partner"] = is_partner(story, partner_names, partner_domains)
        unique.append(story)

    partner_stories = [s for s in unique if s["partner"]]
    other_stories = [s for s in unique if not s["partner"]]
    with_rss = [p for p in partners if p.get("rss")]
    now = fmt_now(datetime.now().astimezone())

    rows = []
    for partner in partners:
        home = partner.get("home") or ""
        home_html = (
            f'<a href="{html.escape(home)}">{html.escape(domain(home) or home)}</a>'
            if home
            else "—"
        )
        rows.append(
            "<tr>"
            f"<td>{html.escape(partner['org'])}</td>"
            f"<td>{html.escape(partner.get('kind') or '')}</td>"
            f"<td>{'Yes' if partner.get('rss') else 'No'}</td>"
            f"<td>{home_html}</td>"
            "</tr>"
        )

    html_out = (
        template.replace("{{NOW}}", html.escape(now))
        .replace("{{PARTNER_COUNT}}", str(len(partner_stories)))
        .replace("{{OTHER_COUNT}}", str(len(other_stories)))
        .replace("{{PARTNER_RSS_COUNT}}", str(len(with_rss)))
        .replace("{{PARTNER_TOTAL}}", str(len(partners)))
        .replace("{{DNR_FEED_COUNT}}", str(len(dnr_feeds)))
        .replace(
            "{{PARTNER_ITEMS}}",
            "\n".join(story_li(s, True) for s in partner_stories[:MAX_LIST]),
        )
        .replace(
            "{{OTHER_ITEMS}}",
            "\n".join(story_li(s, False) for s in other_stories[:MAX_LIST]),
        )
        .replace("{{COVERAGE_ROWS}}", "".join(rows))
    )
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html_out)
    print(f"wrote {out} partner={len(partner_stories)} other={len(other_stories)}")


if __name__ == "__main__":
    main()
