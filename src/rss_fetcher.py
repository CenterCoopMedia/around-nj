"""RSS feed fetcher for NJ news sources."""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import feedparser


def transform_url(url: str, source_name: str) -> str:
    """
    Transform URLs for paywall bypass or other fixes.

    Args:
        url: Original article URL
        source_name: Name of the source

    Returns:
        Transformed URL (or original if no transform needed)
    """
    # NJ.com: Add ?outputType=amp to bypass paywall
    if "nj.com" in url.lower() and "outputType=amp" not in url:
        parsed = urlparse(url)
        # Add amp parameter
        if parsed.query:
            new_url = f"{url}&outputType=amp"
        else:
            new_url = f"{url}?outputType=amp"
        return new_url

    return url


# Patterns that indicate generic broadcasts/roundups to skip
SKIP_HEADLINE_PATTERNS = [
    "newscast for",  # "WHYY Newscast for Tuesday, 11:00 a.m."
    "morning edition",  # Generic morning shows
    "evening edition",
    "daily briefing",
    "news roundup for",  # Generic daily roundups
    "weather forecast for",  # Generic weather forecasts (not weather news)
    "traffic report",
    "this week on",  # Weekly show promos
    "tonight on",
    "podcast:",  # Podcast episode announcements
    "listen:",
    "watch:",
    "live stream",
    "livestream",
    "nj spotlight news:",  # "NJ Spotlight News: December 15, 2025"
    "whyy news:",  # Similar date-based broadcasts
    "njtv news:",
]


def is_generic_broadcast(headline: str) -> bool:
    """
    Check if a headline is a generic broadcast/roundup that should be skipped.

    Args:
        headline: Article headline

    Returns:
        True if this is a generic broadcast to skip, False otherwise
    """
    headline_lower = headline.lower()
    for pattern in SKIP_HEADLINE_PATTERNS:
        if pattern in headline_lower:
            return True
    return False


def load_feed_config() -> dict:
    """Load RSS feed configuration from JSON file."""
    config_path = Path(__file__).parent.parent / "config" / "rss_feeds.json"
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def parse_feed(url: str, source_name: str, hours_back: int = 24) -> list[dict]:
    """
    Parse an RSS feed and return recent articles.

    Args:
        url: RSS feed URL
        source_name: Name of the source for attribution
        hours_back: How many hours back to look for articles (default 24)

    Returns:
        List of article dicts with title, url, source, published date
    """
    if not url:
        return []

    try:
        feed = feedparser.parse(url)
        articles = []
        cutoff = datetime.now() - timedelta(hours=hours_back)

        for entry in feed.entries:
            # Parse published date
            published = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                published = datetime(*entry.published_parsed[:6])
            elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
                published = datetime(*entry.updated_parsed[:6])

            # Skip old articles if we have a date
            if published and published < cutoff:
                continue

            # Get and transform URL
            raw_url = entry.get("link", "")
            transformed_url = transform_url(raw_url, source_name)

            title = entry.get("title", "").strip()

            # Skip generic broadcasts (e.g., "WHYY Newscast for Tuesday")
            if is_generic_broadcast(title):
                continue

            article = {
                "title": title,
                "url": transformed_url,
                "source": source_name,
                "published": published.isoformat() if published else None,
                "summary": entry.get("summary", "")[:500]
                if entry.get("summary")
                else None,
            }

            # Only add if we have title and URL
            if article["title"] and article["url"]:
                articles.append(article)

        return articles

    except Exception as e:
        print(f"Error parsing feed for {source_name}: {e}")
        return []


def fetch_all_feeds(
    hours_back: int = 24, priority_filter: Optional[int] = None
) -> list[dict]:
    """
    Fetch articles from all configured RSS feeds.

    Args:
        hours_back: How many hours back to look
        priority_filter: Only fetch from sources with this priority or higher (lower number = higher priority)

    Returns:
        List of all articles from all feeds
    """
    config = load_feed_config()
    all_articles = []

    # Combine all feed categories (dynamic - gets all keys under "feeds")
    all_sources = []
    for category_name, sources in config["feeds"].items():
        if isinstance(sources, list):
            all_sources.extend(sources)

    for source in all_sources:
        # Apply priority filter
        if priority_filter and source.get("priority", 99) > priority_filter:
            continue

        name = source["name"]

        # Try main RSS URL
        rss_url = source.get("rss_url")
        if rss_url:
            print(f"Fetching from {name}...")
            articles = parse_feed(rss_url, name, hours_back)
            all_articles.extend(articles)
            print(f"  Found {len(articles)} articles")

        # Also try category-specific feeds if available
        for key, url in source.items():
            if key.startswith("rss_") and key != "rss_url" and url:
                category_name = key.replace("rss_", "")
                print(f"Fetching from {name} ({category_name})...")
                articles = parse_feed(url, name, hours_back)
                all_articles.extend(articles)
                print(f"  Found {len(articles)} articles")

    # Remove duplicates based on URL
    seen_urls = set()
    unique_articles = []
    for article in all_articles:
        if article["url"] not in seen_urls:
            seen_urls.add(article["url"])
            unique_articles.append(article)

    print(f"\nTotal unique articles: {len(unique_articles)}")
    return unique_articles


def test_feeds():
    """Test all RSS feeds and report status."""
    config = load_feed_config()

    print("=" * 60)
    print("RSS FEED TEST REPORT")
    print("=" * 60)

    results = {"working": [], "failed": [], "no_feed": []}

    # Combine all feed categories (dynamic)
    all_sources = []
    for category_name, sources in config["feeds"].items():
        if isinstance(sources, list):
            all_sources.extend(sources)

    for source in all_sources:
        name = source["name"]
        rss_url = source.get("rss_url")

        if not rss_url:
            results["no_feed"].append(name)
            print(f"[ -- ] {name}: No RSS feed configured")
            continue

        try:
            feed = feedparser.parse(rss_url)
            if feed.entries:
                results["working"].append(name)
                print(f"[ OK ] {name}: {len(feed.entries)} entries")
            else:
                results["failed"].append(name)
                print(f"[FAIL] {name}: No entries returned")
        except Exception as e:
            results["failed"].append(name)
            print(f"[FAIL] {name}: {e}")

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Working: {len(results['working'])}")
    print(f"Failed: {len(results['failed'])}")
    print(f"No feed: {len(results['no_feed'])}")

    if results["failed"]:
        print(f"\nFailed feeds: {', '.join(results['failed'])}")
    if results["no_feed"]:
        print(f"No feed configured: {', '.join(results['no_feed'])}")

    return results


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        test_feeds()
    else:
        # Fetch last 24 hours of articles
        articles = fetch_all_feeds(hours_back=24)

        print("\n" + "=" * 60)
        print("SAMPLE ARTICLES")
        print("=" * 60)

        for article in articles[:10]:
            print(f"\n{article['source']}: {article['title'][:70]}...")
            print(f"  URL: {article['url'][:60]}...")
