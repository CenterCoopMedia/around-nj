#!/usr/bin/env python3
"""Build the Around New Jersey headlines snapshot for GitHub Pages."""

from __future__ import annotations

import argparse
import html
import http.client
import ipaddress
import json
import re
import socket
import ssl
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse
from zoneinfo import ZoneInfo

import feedparser

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


TOKEN_RE = re.compile(r"\{\{[A-Z_]+\}\}")


def ip_is_allowed(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Allow only globally routed unicast addresses. This excludes Tailscale CGNAT."""
    return bool(ip.is_global) and not ip.is_multicast


def render_template(template: str, mapping: dict[str, str]) -> str:
    """Replace {{TOKENS}} in the template only. Values are not rescanned."""

    def repl(match: re.Match[str]) -> str:
        return mapping.get(match.group(0), match.group(0))

    return TOKEN_RE.sub(repl, template)


def pinned_addrinfo(host: str, port: int):
    infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    chosen = None
    for family, socktype, proto, _, sockaddr in infos:
        ip = ipaddress.ip_address(sockaddr[0])
        if not ip_is_allowed(ip):
            raise ValueError("blocked host")
        if chosen is None:
            chosen = (family, socktype, proto, sockaddr)
    if chosen is None:
        raise ValueError("blocked host")
    return chosen


def fetch_url_bytes(url: str, hops: int = 0) -> tuple[int, bytes]:
    if hops > MAX_REDIRECTS:
        raise ValueError("too many redirects")
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("blocked host")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    family, socktype, proto, sockaddr = pinned_addrinfo(parsed.hostname, port)
    sock = socket.socket(family, socktype, proto)
    sock.settimeout(TIMEOUT)
    sock.connect(sockaddr)
    if parsed.scheme == "https":
        ctx = ssl.create_default_context()
        sock = ctx.wrap_socket(sock, server_hostname=parsed.hostname)
    if parsed.scheme == "https":
        conn = http.client.HTTPSConnection(parsed.hostname, port, timeout=TIMEOUT)
    else:
        conn = http.client.HTTPConnection(parsed.hostname, port, timeout=TIMEOUT)
    conn.sock = sock
    path = parsed.path or "/"
    if parsed.query:
        path += "?" + parsed.query
    conn.request("GET", path, headers={"User-Agent": UA, "Host": parsed.hostname})
    response = conn.getresponse()
    try:
        if response.status in {301, 302, 303, 307, 308}:
            location = response.getheader("Location")
            if not location:
                raise ValueError("redirect without location")
            return fetch_url_bytes(urljoin(url, location), hops + 1)
        started = time.monotonic()
        chunks: list[bytes] = []
        size = 0
        while True:
            if time.monotonic() - started > DEADLINE_SECONDS:
                raise TimeoutError("deadline")
            chunk = response.read(65536)
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_BODY_BYTES:
                raise ValueError("too large")
            chunks.append(chunk)
        return response.status, b"".join(chunks)
    finally:
        conn.close()


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


def fetch_feed(url: str, source: str) -> dict:
    result = {"source": source, "url": url, "ok": False, "items": [], "error": None}
    try:
        status, body = fetch_url_bytes(url)
        if status >= 400:
            result["error"] = f"http {status}"
            return result
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
            try:
                parsed_link = urlparse(link)
            except ValueError:
                continue
            if parsed_link.scheme not in ("http", "https") or not parsed_link.hostname:
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
        detail = str(exc).strip().replace("\n", " ")[:120]
        result["error"] = (
            f"{type(exc).__name__}: {detail}" if detail else type(exc).__name__
        )
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
    partners = [p for p in partners if p.get("snapshot") is not False]

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

    stories: list[dict] = []
    failures: list[dict] = []
    ok_urls: set[str] = set()
    with ThreadPoolExecutor(max_workers=16) as pool:
        futs = {pool.submit(fetch_feed, url, name): (url, name) for url, name in jobs}
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
            else "none"
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

    html_out = render_template(
        template,
        {
            "{{NOW}}": html.escape(now),
            "{{PARTNER_COUNT}}": str(len(partner_stories)),
            "{{OTHER_COUNT}}": str(len(other_stories)),
            "{{PARTNER_SHOWN}}": str(len(shown_partners)),
            "{{OTHER_SHOWN}}": str(len(shown_other)),
            "{{PARTNER_RSS_COUNT}}": str(len(working_partners)),
            "{{PARTNER_TOTAL}}": str(len(partners)),
            "{{DNR_FEED_COUNT}}": str(len(dnr_feeds)),
            "{{PARTNER_ITEMS}}": "\n".join(story_li(s, True) for s in shown_partners),
            "{{OTHER_ITEMS}}": "\n".join(story_li(s, False) for s in shown_other),
            "{{COVERAGE_ROWS}}": "".join(rows),
        },
    )
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html_out, encoding="utf-8")
    print(f"wrote {out} partner={len(partner_stories)} other={len(other_stories)}")


if __name__ == "__main__":
    main()
