"""Playwright-based fetcher for sites with broken RSS feeds or paywalls.

This module handles scraping news sites that:
- Have broken or non-functional RSS feeds (TAPinto network)
- Have paywalls that can be bypassed by disabling JavaScript (USA Today network)
- Require special handling for content extraction

Sites covered:
- TAPinto network (tapinto.net subdomains)
- USA Today network: NorthJersey.com, Asbury Park Press (app.com), Press of AC
- Any other sites where RSS fails
"""

import re
import sys
from datetime import datetime
from urllib.parse import urljoin

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


# Sites to scrape with Playwright (RSS feeds broken or unavailable)
PLAYWRIGHT_SOURCES = {
    # USA Today Network (disable JS to bypass paywall)
    "northjersey": {
        "name": "NorthJersey.com",
        "url": "https://www.northjersey.com/news/",
        "disable_js": True,
        "selectors": {"articles": "a.gnt_m_flm_a", "headline": "self", "link": "self"},
    },
    "app": {
        "name": "Asbury Park Press",
        "url": "https://www.app.com/news/",
        "disable_js": True,
        "selectors": {"articles": "a.gnt_m_flm_a", "headline": "self", "link": "self"},
    },
    "pressofac": {
        "name": "Press of Atlantic City",
        "url": "https://pressofatlanticcity.com/news/local/",
        "disable_js": False,
        "selectors": {
            "articles": "h3.tnt-headline a",
            "headline": "self",
            "link": "self",
        },
    },
    # TAPinto network
    "tapinto_montclair": {
        "name": "TAPinto Montclair",
        "url": "https://www.tapinto.net/towns/montclair/sections/news",
        "disable_js": False,
        "selectors": {
            "articles": "div.article-card a.article-card__link",
            "headline": "h3.article-card__title",
            "link": "self",
        },
    },
    "tapinto_newark": {
        "name": "TAPinto Newark",
        "url": "https://www.tapinto.net/towns/newark/sections/news",
        "disable_js": False,
        "selectors": {
            "articles": "div.article-card a.article-card__link",
            "headline": "h3.article-card__title",
            "link": "self",
        },
    },
    "tapinto_jerseycity": {
        "name": "TAPinto Jersey City",
        "url": "https://www.tapinto.net/towns/jersey-city/sections/news",
        "disable_js": False,
        "selectors": {
            "articles": "div.article-card a.article-card__link",
            "headline": "h3.article-card__title",
            "link": "self",
        },
    },
    "tapinto_trenton": {
        "name": "TAPinto Trenton",
        "url": "https://www.tapinto.net/towns/trenton/sections/news",
        "disable_js": False,
        "selectors": {
            "articles": "div.article-card a.article-card__link",
            "headline": "h3.article-card__title",
            "link": "self",
        },
    },
    "tapinto_elizabeth": {
        "name": "TAPinto Elizabeth",
        "url": "https://www.tapinto.net/towns/elizabeth/sections/news",
        "disable_js": False,
        "selectors": {
            "articles": "div.article-card a.article-card__link",
            "headline": "h3.article-card__title",
            "link": "self",
        },
    },
    "tapinto_newbrunswick": {
        "name": "TAPinto New Brunswick",
        "url": "https://www.tapinto.net/towns/new-brunswick/sections/news",
        "disable_js": False,
        "selectors": {
            "articles": "div.article-card a.article-card__link",
            "headline": "h3.article-card__title",
            "link": "self",
        },
    },
}


def scrape_site(
    source_key: str, config: dict, max_articles: int = 20, hours_back: int = 24
) -> list[dict]:
    """
    Scrape a single news site using Playwright.

    Args:
        source_key: Key from PLAYWRIGHT_SOURCES
        config: Site configuration dict
        max_articles: Maximum articles to fetch
        hours_back: How far back to look (for filtering if dates available)

    Returns:
        List of story dicts with headline, url, source, published
    """
    stories = []

    try:
        with sync_playwright() as p:
            # Launch browser
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            )

            # Disable JavaScript if needed (paywall bypass)
            if config.get("disable_js"):
                context.set_extra_http_headers({"Accept": "text/html"})
                # Create page with JS disabled
                page = context.new_page()
                page.route(
                    "**/*",
                    lambda route: (
                        route.abort()
                        if route.request.resource_type
                        in ["script", "stylesheet", "image", "font"]
                        else route.continue_()
                    ),
                )
            else:
                page = context.new_page()

            # Navigate to the news page
            page.goto(config["url"], timeout=30000, wait_until="domcontentloaded")

            # Wait a moment for content
            page.wait_for_timeout(2000)

            # Get article elements
            selectors = config["selectors"]
            articles = page.query_selector_all(selectors["articles"])

            for article in articles[:max_articles]:
                try:
                    # Get headline
                    if selectors["headline"] == "self":
                        headline = article.text_content()
                    else:
                        headline_el = article.query_selector(selectors["headline"])
                        headline = headline_el.text_content() if headline_el else None

                    # Get link
                    if selectors["link"] == "self":
                        url = article.get_attribute("href")
                    else:
                        link_el = article.query_selector(selectors["link"])
                        url = link_el.get_attribute("href") if link_el else None

                    if headline and url:
                        # Clean up headline
                        headline = headline.strip()
                        headline = re.sub(r"\s+", " ", headline)

                        # Make URL absolute
                        if url and not url.startswith("http"):
                            url = urljoin(config["url"], url)

                        # Skip if headline is too short or looks like navigation
                        if len(headline) < 15:
                            continue

                        stories.append(
                            {
                                "headline": headline,
                                "title": headline,
                                "url": url,
                                "source": config["name"],
                                "published": datetime.now(),  # No date available from listing
                                "from_playwright": True,
                            }
                        )

                except Exception:
                    continue

            browser.close()

    except PlaywrightTimeout:
        print(f"  Timeout scraping {config['name']}")
    except Exception as e:
        print(f"  Error scraping {config['name']}: {e}")

    return stories


def fetch_all_playwright_sources(
    hours_back: int = 24, max_per_source: int = 15
) -> list[dict]:
    """
    Fetch stories from all Playwright-based sources.

    Args:
        hours_back: How far back to look for stories
        max_per_source: Max stories per source

    Returns:
        Combined list of stories from all sources
    """
    all_stories = []

    print("\n🎭 Fetching from Playwright sources (broken RSS/paywalled sites)...")

    for source_key, config in PLAYWRIGHT_SOURCES.items():
        print(f"Scraping {config['name']}...")
        stories = scrape_site(source_key, config, max_per_source, hours_back)
        print(f"  Found {len(stories)} articles")
        all_stories.extend(stories)

    print(f"\nTotal from Playwright sources: {len(all_stories)}")
    return all_stories


def test_single_source(source_key: str) -> None:
    """Test scraping a single source."""
    if source_key not in PLAYWRIGHT_SOURCES:
        print(f"Unknown source: {source_key}")
        print(f"Available: {list(PLAYWRIGHT_SOURCES.keys())}")
        return

    config = PLAYWRIGHT_SOURCES[source_key]
    print(f"Testing {config['name']} ({config['url']})")
    print(f"  JavaScript disabled: {config.get('disable_js', False)}")

    stories = scrape_site(source_key, config, max_articles=5)

    print(f"\nFound {len(stories)} articles:")
    for story in stories:
        print(f"  - {story['headline'][:60]}...")
        print(f"    {story['url'][:80]}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Playwright-based news scraper")
    parser.add_argument("--test", type=str, help="Test a single source by key")
    parser.add_argument("--list", action="store_true", help="List available sources")
    parser.add_argument("--all", action="store_true", help="Fetch from all sources")

    args = parser.parse_args()

    if args.list:
        print("Available Playwright sources:")
        for key, config in PLAYWRIGHT_SOURCES.items():
            print(f"  {key}: {config['name']}")
            print(f"    URL: {config['url']}")
            print(f"    JS disabled: {config.get('disable_js', False)}")
    elif args.test:
        test_single_source(args.test)
    elif args.all:
        stories = fetch_all_playwright_sources()
        print(f"\n{'=' * 60}")
        print(f"Total stories fetched: {len(stories)}")
    else:
        # Default: test NorthJersey.com
        test_single_source("northjersey")
