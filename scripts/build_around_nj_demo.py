#!/usr/bin/env python3
"""Build the Around New Jersey headlines snapshot for GitHub Pages."""

from __future__ import annotations

import argparse
import html
import ipaddress
import json
import re
import socket
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse
from zoneinfo import ZoneInfo

import feedparser
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from rss_fetcher import is_generic_broadcast  # noqa: E402

LOOKBACK_HOURS = 72
TIMEOUT = 10
DEADLINE_SECONDS = 15
MAX_BODY_BYTES = 2_000_000
UA = "CCM-AroundNJ/0.3 (+https://centerforcooperativemedia.org)"
MAX_LIST = 80
MAX_REDIRECTS = 3
NJ_TZ = ZoneInfo("America/New_York")
EXPECTED_FAILURE_PREFIXES = ("http 403",)


def is_public_http_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return False
    host = parsed.hostname
    if host in {"localhost", "localhost.localdomain"}:
        return False
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
        ):
            return False
    return True


def open_public_feed(session: requests.Session, url: str) -> requests.Response:
    current = url
    for _ in range(MAX_REDIRECTS + 1):
        if not is_public_http_url(current):
            raise ValueError("blocked host")
        response = session.get(
            current, timeout=TIMEOUT, allow_redirects=False, stream=True
        )
        if response.is_redirect or response.status_code in {301, 302, 303, 307, 308}:
            location = response.headers.get("Location")
            response.close()
            if not location:
                raise ValueError("redirect without location")
            current = urljoin(current, location)
            continue
        return response
    raise ValueError("too many redirects")


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


def read_bounded_body(response: requests.Response) -> bytes:
    started = time.monotonic()
    chunks: list[bytes] = []
    size = 0
    for chunk in response.iter_content(65536):
        if time.monotonic() - started > DEADLINE_SECONDS:
            raise TimeoutError("deadline")
        size += len(chunk)
        if size > MAX_BODY_BYTES:
            raise ValueError("too large")
        chunks.append(chunk)
    return b"".join(chunks)


def fetch_feed(session: requests.Session, url: str, source: str) -> dict:
    result = {"source": source, "url": url, "ok": False, "items": [], "error": None}
    try:
        with open_public_feed(session, url) as response:
            if response.status_code >= 400:
                result["error"] = f"http {response.status_code}"
                return result
            body = read_bounded_body(response)
        parsed = feedparser.parse(body)
        if parsed.bozo and not parsed.entries:
            result["error"] = "not a feed"
            return result
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(hours=LOOKBACK_HOURS)
        future_limit = now + timedelta(hours=1)
        items = []
        for entry in parsed.entries:
            title = re.sub(r"\s+", " ", (entry.get("title") or "").strip())
            link = (entry.get("link") or "").strip()
            if not title or not link or is_generic_broadcast(title):
                continue
            if urlparse(link).scheme not in ("http", "https"):
                continue
            when = parse_when(entry)
            if when is None or when < cutoff or when > future_limit:
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
        dt = datetime.fromisoformat(iso).astimezone(NJ_TZ)
        hour = dt.strftime("%I").lstrip("0") or "12"
        return f"{dt.strftime('%a')} {hour}:{dt.strftime('%M %p')} ET"
    except Exception:
        return iso[:16]


def fmt_now(dt: datetime) -> str:
    local = dt.astimezone(NJ_TZ)
    hour = local.strftime("%I").lstrip("0") or "12"
    return (
        f"{local.strftime('%A, %B')} {local.day}, {local.year}, "
        f"{hour}:{local.strftime('%M %p')} ET"
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

    feeds_cfg = json.loads(
        (ROOT / "config" / "rss_feeds.json").read_text(encoding="utf-8")
    )
    partners = json.loads(
        (ROOT / "config" / "pbs_partners.json").read_text(encoding="utf-8")
    )
    template = (ROOT / "scripts" / "around_nj_template.html").read_text(
        encoding="utf-8"
    )

    dnr_feeds = []
    for items in feeds_cfg.get("feeds", {}).values():
        for feed in items:
            url = feed.get("rss_nj") or feed.get("rss_url")
            if not url:
                continue
            coverage = (feed.get("coverage") or "").lower()
            if coverage in {"nyc metro", "philadelphia", "philadelphia/south jersey"}:
                # WHYY still included via rss_nj below when present.
                if not feed.get("rss_nj"):
                    continue
            dnr_feeds.append({**feed, "rss_url": url})

    jobs = [(f["rss_url"], f["name"]) for f in dnr_feeds]
    seen = {url for url, _ in jobs}
    for partner in partners:
        rss = partner.get("rss")
        if partner.get("snapshot") is False:
            continue
        if rss and rss not in seen:
            jobs.append((rss, partner["org"]))
            seen.add(rss)

    session = requests.Session()
    session.headers.update({"User-Agent": UA})
    stories: list[dict] = []
    failures: list[dict] = []
    ok_urls: set[str] = set()
    with ThreadPoolExecutor(max_workers=16) as pool:
        futs = {
            pool.submit(fetch_feed, session, url, name): (url, name)
            for url, name in jobs
        }
        for fut in as_completed(futs):
            result = fut.result()
            if result["ok"]:
                ok_urls.add(result["url"])
                stories.extend(result["items"])
            else:
                failures.append(result)
    if failures:
        expected = [
            f
            for f in failures
            if str(f.get("error") or "").startswith(EXPECTED_FAILURE_PREFIXES)
        ]
        unexpected = [f for f in failures if f not in expected]
        print(f"feed failures: {len(failures)}/{len(jobs)}")
        if expected:
            print(f"  expected: {len(expected)}")
            for failure in expected:
                print(f"    {failure['source']}: {failure['error']}")
        if unexpected:
            print(f"  unexpected: {len(unexpected)}")
            for failure in unexpected:
                print(f"    {failure['source']}: {failure['error']}")
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
    shown_partners = partner_stories[:MAX_LIST]
    shown_other = other_stories[:MAX_LIST]
    working_partners = [p for p in partners if p.get("rss") in ok_urls]
    now = fmt_now(datetime.now().astimezone())

    rows = []
    for partner in partners:
        home = partner.get("home") or ""
        home_html = (
            f'<a href="{html.escape(home)}">{html.escape(domain(home) or home)}</a>'
            if home
            else "—"
        )
        rss_ok = partner.get("rss") in ok_urls
        rows.append(
            "<tr>"
            f"<td>{html.escape(partner['org'])}</td>"
            f"<td>{html.escape(partner.get('kind') or '')}</td>"
            f"<td>{'Yes' if rss_ok else 'No'}</td>"
            f"<td>{home_html}</td>"
            "</tr>"
        )

    html_out = (
        template.replace("{{NOW}}", html.escape(now))
        .replace("{{PARTNER_COUNT}}", str(len(partner_stories)))
        .replace("{{OTHER_COUNT}}", str(len(other_stories)))
        .replace("{{PARTNER_SHOWN}}", str(len(shown_partners)))
        .replace("{{OTHER_SHOWN}}", str(len(shown_other)))
        .replace("{{PARTNER_RSS_COUNT}}", str(len(working_partners)))
        .replace("{{PARTNER_TOTAL}}", str(len(partners)))
        .replace("{{DNR_FEED_COUNT}}", str(len(dnr_feeds)))
        .replace(
            "{{PARTNER_ITEMS}}",
            "\n".join(story_li(s, True) for s in shown_partners),
        )
        .replace(
            "{{OTHER_ITEMS}}",
            "\n".join(story_li(s, False) for s in shown_other),
        )
        .replace("{{COVERAGE_ROWS}}", "".join(rows))
    )
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html_out, encoding="utf-8")
    print(f"wrote {out} partner={len(partner_stories)} other={len(other_stories)}")


if __name__ == "__main__":
    main()
