#!/usr/bin/env python3
"""Build the Around New Jersey headlines snapshot for GitHub Pages."""

from __future__ import annotations

import argparse
import html
import http.client
import ipaddress
import json
import multiprocessing
import re
import socket
import ssl
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse
from zoneinfo import ZoneInfo

import feedparser

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from rss_fetcher import is_generic_broadcast  # noqa: E402

LOOKBACK_HOURS = 72
TIMEOUT = 10
DEADLINE_SECONDS = 15
MAX_BODY_BYTES = 2_000_000
TRACKING_QUERY = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
}
UA = "CCM-AroundNJ/0.3 (+https://centerforcooperativemedia.org)"
MAX_LIST = 80
MAX_REDIRECTS = 3


def load_nj_tz():
    try:
        return ZoneInfo("America/New_York")
    except Exception:
        # Windows without the IANA database: Eastern Daylight as a last resort.
        return timezone(timedelta(hours=-4))


NJ_TZ = load_nj_tz()
EXPECTED_FAILURES = (
    ("tapinto.net", "http 403"),
    ("northjersey.com", "http 404"),
    ("app.com", "http 404"),
    ("dailyrecord.com", "http 404"),
    ("courierpostonline.com", "http 404"),
)


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
    allowed = []
    seen = set()
    for family, socktype, proto, _, sockaddr in infos:
        ip = ipaddress.ip_address(sockaddr[0])
        if not ip_is_allowed(ip):
            raise ValueError("blocked host")
        key = (family, sockaddr)
        if key in seen:
            continue
        seen.add(key)
        allowed.append((family, socktype, proto, sockaddr))
    if not allowed:
        raise ValueError("blocked host")
    return allowed


def remaining_timeout(deadline: float) -> float:
    left = deadline - time.monotonic()
    if left <= 0:
        raise TimeoutError("deadline")
    return min(TIMEOUT, left)


def fetch_url_bytes(
    url: str, hops: int = 0, deadline: float | None = None
) -> tuple[int, bytes]:
    if hops > MAX_REDIRECTS:
        raise ValueError("too many redirects")
    if deadline is None:
        deadline = time.monotonic() + DEADLINE_SECONDS
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("blocked host")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    last_error: Exception | None = None
    sock = None
    for family, socktype, proto, sockaddr in pinned_addrinfo(parsed.hostname, port):
        candidate = socket.socket(family, socktype, proto)
        try:
            candidate.settimeout(remaining_timeout(deadline))
            candidate.connect(sockaddr)
            sock = candidate
            break
        except OSError as exc:
            last_error = exc
            candidate.close()
    if sock is None:
        raise last_error or OSError("connection failed")
    sock.settimeout(remaining_timeout(deadline))
    if parsed.scheme == "https":
        ctx = ssl.create_default_context()
        sock = ctx.wrap_socket(sock, server_hostname=parsed.hostname)
        sock.settimeout(remaining_timeout(deadline))
    timeout = remaining_timeout(deadline)
    if parsed.scheme == "https":
        conn = http.client.HTTPSConnection(parsed.hostname, port, timeout=timeout)
    else:
        conn = http.client.HTTPConnection(parsed.hostname, port, timeout=timeout)
    conn.sock = sock
    path = parsed.path or "/"
    if parsed.query:
        path += "?" + parsed.query
    conn.request("GET", path, headers={"User-Agent": UA, "Host": parsed.hostname})
    sock.settimeout(remaining_timeout(deadline))
    response = conn.getresponse()
    try:
        if response.status in {301, 302, 303, 307, 308}:
            location = response.getheader("Location")
            if not location:
                raise ValueError("redirect without location")
            return fetch_url_bytes(urljoin(url, location), hops + 1, deadline)
        chunks: list[bytes] = []
        size = 0
        while True:
            sock.settimeout(remaining_timeout(deadline))
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


def is_expected_failure(url: str, error: str) -> bool:
    host = domain(url)
    err = (error or "").lower()
    for suffix, expected in EXPECTED_FAILURES:
        if host == suffix or host.endswith("." + suffix):
            if err.startswith(expected):
                return True
    return False


def domain(url: str | None) -> str:
    if not url:
        return ""
    try:
        host = urlparse(url).hostname or ""
    except Exception:
        return ""
    host = host.lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def canonical_url(url: str) -> str:
    parsed = urlparse(url)
    host = domain(url)
    path = (parsed.path or "/").rstrip("/") or "/"
    scheme = "https" if parsed.scheme in {"http", "https"} else parsed.scheme
    kept = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() not in TRACKING_QUERY
    ]
    query = urlencode(kept)
    return f"{scheme}://{host}{path}" + (f"?{query}" if query else "")


def valid_story_link(link: str) -> str | None:
    try:
        parsed = urlparse(link)
    except ValueError:
        return None
    if parsed.scheme not in {"http", "https"}:
        return None
    if parsed.username or parsed.password:
        return None
    host = (parsed.hostname or "").lower()
    if not host or "." not in host or host == "localhost":
        return None
    return link


def norm_name(value: str) -> str:
    text = (value or "").lower().strip()
    if text.startswith("the "):
        text = text[4:]
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


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


def fetch_feed(url: str, source: str, partner: bool = False) -> dict:
    result = {"source": source, "url": url, "ok": False, "items": [], "error": None}
    try:
        status, body = fetch_url_bytes(url)
        if status >= 400:
            result["error"] = f"http {status}"
            return result
        parsed = feedparser.parse(body)
        if not parsed.entries and (parsed.bozo or not parsed.get("version")):
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
            link = urljoin(url, link)
            if valid_story_link(link) is None:
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
                    "partner": partner,
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


def _fetch_feed_worker(url: str, source: str, partner: bool, conn) -> None:
    try:
        conn.send(fetch_feed(url, source, partner))
    except Exception as exc:
        conn.send(
            {
                "source": source,
                "url": url,
                "ok": False,
                "items": [],
                "error": type(exc).__name__,
            }
        )
    finally:
        conn.close()


def fetch_feed_bounded(url: str, source: str, partner: bool = False) -> dict:
    ctx = multiprocessing.get_context("spawn")
    parent, child = ctx.Pipe(duplex=False)
    proc = ctx.Process(
        target=_fetch_feed_worker,
        args=(url, source, partner, child),
        daemon=True,
    )
    proc.start()
    child.close()
    proc.join(timeout=DEADLINE_SECONDS + 2)
    if proc.is_alive():
        proc.terminate()
        proc.join(1)
        return {
            "source": source,
            "url": url,
            "ok": False,
            "items": [],
            "error": "deadline",
        }
    if parent.poll():
        return parent.recv()
    return {
        "source": source,
        "url": url,
        "ok": False,
        "items": [],
        "error": "deadline",
    }


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


def combine_duplicate(current: dict, story: dict) -> dict:
    merged_partner = bool(current.get("partner")) or bool(story.get("partner"))
    newer = (story.get("when") or "") > (current.get("when") or "")
    keep = dict(story if newer else current)
    if merged_partner:
        if story.get("partner") and not current.get("partner"):
            partner_row = story
        elif current.get("partner") and not story.get("partner"):
            partner_row = current
        else:
            partner_row = keep
        keep["source"] = partner_row["source"]
        keep["partner"] = True
    else:
        keep["partner"] = False
    return keep


def is_partner(story: dict, partner_names: set[str]) -> bool:
    src = norm_name(story.get("source") or "")
    names = {norm_name(name) for name in partner_names if name}
    if not src:
        return False
    if src in names:
        return True
    for name in names:
        if len(name) < 10:
            continue
        if name in src or src in name:
            return True
    return False


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        default=str(ROOT / "drafts" / "around-nj-demo.html"),
        help="HTML output path",
    )
    parser.add_argument(
        "--scraped-json",
        help="Optional Firecrawl homepage scrape output to merge",
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

    partner_rss = {p["rss"] for p in partners if p.get("rss")}
    partner_feed_hosts = set()
    for partner in partners:
        if partner.get("star_domain"):
            partner_feed_hosts.add(partner["star_domain"].lower().removeprefix("www."))
        if partner.get("home"):
            host = domain(partner["home"])
            if host:
                partner_feed_hosts.add(host)

    def feed_is_partner(url: str, name: str) -> bool:
        if url in partner_rss:
            return True
        host = domain(url)
        if host and (
            host in partner_feed_hosts
            or any(host == h or host.endswith("." + h) for h in partner_feed_hosts)
        ):
            return True
        return is_partner({"source": name, "url": url}, {p["org"] for p in partners})

    jobs = [
        (f["rss_url"], f["name"], feed_is_partner(f["rss_url"], f["name"]))
        for f in dnr_feeds
    ]
    seen = {url for url, _, _ in jobs}
    for partner in partners:
        rss = partner.get("rss")
        if rss and rss not in seen:
            jobs.append((rss, partner["org"], True))
            seen.add(rss)

    stories: list[dict] = []
    failures: list[dict] = []
    ok_urls: set[str] = set()
    with ThreadPoolExecutor(max_workers=16) as pool:
        futs = {
            pool.submit(fetch_feed_bounded, url, name, partner): (url, name)
            for url, name, partner in jobs
        }
        for fut in as_completed(futs):
            result = fut.result()
            if result["ok"]:
                ok_urls.add(result["url"])
                stories.extend(result["items"])
            else:
                failures.append(result)
    if args.scraped_json:
        scraped = json.loads(Path(args.scraped_json).read_text(encoding="utf-8"))
        cutoff = datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HOURS)
        for block in scraped.get("results") or []:
            org = str(block.get("org") or "Scrape")
            if block.get("ok") and block.get("url"):
                ok_urls.add(str(block["url"]))
            for item in block.get("stories") or []:
                link = valid_story_link(str(item.get("url") or ""))
                title = " ".join(str(item.get("title") or "").split())
                if not link or not title:
                    continue
                when = parse_when({"published": item.get("published")})
                if when is None:
                    when = datetime.now(timezone.utc)
                if when < cutoff:
                    continue
                stories.append(
                    {
                        "title": title,
                        "url": link,
                        "when": when.isoformat(),
                        "source": str(item.get("source") or org),
                        "partner": True,
                    }
                )
    if failures:
        expected = [
            f
            for f in failures
            if is_expected_failure(str(f.get("url") or ""), str(f.get("error") or ""))
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

    partner_names = {p["org"] for p in partners if p.get("org")}

    by_key: dict[str, dict] = {}
    for story in stories:
        key = canonical_url(story["url"])
        current = by_key.get(key)
        if current is None:
            by_key[key] = story
            continue
        by_key[key] = combine_duplicate(current, story)
    unique = []
    for story in sorted(
        by_key.values(), key=lambda s: s.get("when") or "", reverse=True
    ):
        story["partner"] = bool(story.get("partner")) or is_partner(
            story, partner_names
        )
        unique.append(story)

    partner_stories = [s for s in unique if s["partner"]]
    other_stories = [s for s in unique if not s["partner"]]
    shown_partners = partner_stories[:MAX_LIST]
    shown_other = other_stories[:MAX_LIST]
    working_partners = [p for p in partners if p.get("rss") in ok_urls]
    now = fmt_now(datetime.now().astimezone())
    tapinto_jobs = [url for url, _, _ in jobs if "tapinto.net" in url]
    tapinto_stories = [s for s in unique if "tapinto.net" in (s.get("url") or "")]
    tapinto_403 = [
        f
        for f in failures
        if "tapinto.net" in str(f.get("url") or "")
        and str(f.get("error") or "").startswith("http 403")
    ]
    if tapinto_stories:
        tapinto_note = (
            "This build includes TAPinto headlines from feeds that responded."
        )
    elif tapinto_jobs and len(tapinto_403) == len(tapinto_jobs):
        tapinto_note = "TAPinto RSS returned 403 in this build, so that network is not in this snapshot."
    elif tapinto_jobs:
        tapinto_note = "TAPinto feeds did not yield headlines in this build."
    else:
        tapinto_note = "No TAPinto feeds were queued in this build."

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
            "{{TAPINTO_NOTE}}": tapinto_note,
        },
    )
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html_out, encoding="utf-8")
    print(f"wrote {out} partner={len(partner_stories)} other={len(other_stories)}")


if __name__ == "__main__":
    main()
