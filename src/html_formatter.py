"""HTML formatter for Daily News Roundup newsletter."""

import re
from datetime import datetime
from pathlib import Path
from typing import Optional


def load_template() -> str:
    """Load the HTML template from history folder."""
    template_path = Path(__file__).parent.parent / "history" / "dnr-template.html"
    with open(template_path, "r", encoding="utf-8") as f:
        return f.read()


def format_story(headline: str, url: str, source: str) -> str:
    """
    Format a single story as an HTML list item.

    Args:
        headline: Story headline
        url: Story URL
        source: Source name for attribution

    Returns:
        HTML string: <li>Headline (<a href="URL">Source</a>)</li>
    """
    # Clean headline
    headline = headline.strip()
    # Remove any existing HTML tags
    headline = re.sub(r"<[^>]+>", "", headline)

    return f'<li>{headline} (<a href="{url}">{source}</a>)</li>'


def format_grouped_story(headline: str, sources: list[tuple[str, str]]) -> str:
    """
    Format a grouped story (same event, multiple sources) as HTML.

    Args:
        headline: Best headline for the story
        sources: List of (source_name, url) tuples

    Returns:
        HTML string with multiple source links
    """
    headline = headline.strip()
    headline = re.sub(r"<[^>]+>", "", headline)

    source_links = ", ".join([f'<a href="{url}">{name}</a>' for name, url in sources])

    return f"<li>{headline} ({source_links})</li>"


def format_section_stories(stories: list[dict], max_stories: int = 20) -> str:
    """
    Format all stories for a section as HTML list items.

    Args:
        stories: List of story dicts with headline, url, source
        max_stories: Maximum stories to include per section

    Returns:
        HTML string of all <li> elements
    """
    items = []
    for story in stories[:max_stories]:  # Limit stories per section
        # Get source - skip stories without proper attribution
        source = story.get("source", "").strip()
        if not source or source == "Unknown":
            # Try to extract source from URL domain
            url = story.get("url", "")
            source = extract_source_from_url(url)

        # Skip stories without source attribution
        if not source:
            continue

        # Check if it's a grouped story (has multiple sources)
        if "sources" in story and isinstance(story["sources"], list):
            item = format_grouped_story(
                headline=story.get("headline", story.get("title", "")),
                sources=story["sources"],
            )
        else:
            item = format_story(
                headline=story.get("headline", story.get("title", "")),
                url=story.get("url", ""),
                source=source,
            )
        items.append(item)

    return "\n                      ".join(items)


def extract_source_from_url(url: str) -> str:
    """
    Extract a readable source name from a URL domain.

    Args:
        url: Full URL

    Returns:
        Source name or empty string if can't determine
    """
    from urllib.parse import urlparse

    if not url:
        return ""

    try:
        domain = urlparse(url).netloc.lower()
        domain = domain.replace("www.", "")

        # Map domains to source names
        domain_map = {
            "nj.com": "NJ.com",
            "njspotlightnews.org": "NJ Spotlight News",
            "newjerseymonitor.com": "NJ Monitor",
            "newjerseyglobe.com": "NJ Globe",
            "northjersey.com": "NorthJersey.com",
            "app.com": "Asbury Park Press",
            "pressofatlanticcity.com": "Press of Atlantic City",
            "njbiz.com": "NJBIZ",
            "roi-nj.com": "ROI-NJ",
            "trentonian.com": "Trentonian",
            "montclairlocal.news": "Montclair Local",
            "villagegreennj.com": "Village Green",
            "baristanet.com": "Baristanet",
            "hudsonreporter.com": "Hudson Reporter",
            "jerseydigs.com": "Jersey Digs",
            "morristowngreen.com": "Morristown Green",
            "unionnewsdaily.com": "Union News Daily",
            "mercerme.com": "MercerMe",
            "planetprinceton.com": "Planet Princeton",
            "jerseyshoreonline.com": "Jersey Shore Online",
            "njpen.com": "NJ Pen",
            "njarts.net": "NJ Arts",
            "njedreport.com": "NJ Education Report",
            "insidernj.com": "InsiderNJ",
            "whyy.org": "WHYY",
            "gothamist.com": "Gothamist",
            "tapinto.net": "TAPinto",
            "njdemocrat.substack.com": "NJ Democrat",
            "echonewstv.com": "Echo News TV",
        }

        # Check for exact match
        if domain in domain_map:
            return domain_map[domain]

        # Check for partial match (subdomains)
        for key, value in domain_map.items():
            if key in domain:
                return value

        return ""
    except Exception:
        return ""


def build_newsletter(
    sections: dict[str, list[dict]], date: Optional[datetime] = None
) -> str:
    """
    Build the complete newsletter HTML.

    Args:
        sections: Dict mapping section names to lists of stories
            Keys: top_stories, politics, housing, education, health, environment, lastly
        date: Newsletter date (defaults to today)

    Returns:
        Complete HTML string ready for Mailchimp
    """
    if date is None:
        date = datetime.now()

    template = load_template()

    # Section placeholders in template
    section_placeholders = {
        "top_stories": "<!-- TOP STORIES -->",
        "politics": "<!-- POLITICS STORIES -->",
        "housing": "<!-- HOUSING STORIES -->",
        "education": "<!-- EDUCATION STORIES -->",
        "health": "<!-- HEALTH STORIES -->",
        "environment": "<!-- ENVIRONMENT STORIES -->",
        "lastly": "<!-- LASTLY STORIES -->",
    }

    # Replace each section placeholder with formatted stories
    for section_key, placeholder in section_placeholders.items():
        stories = sections.get(section_key, [])
        if stories:
            html_content = format_section_stories(stories)
            template = template.replace(placeholder, html_content)
        else:
            # Empty section - add a placeholder message or leave empty
            template = template.replace(placeholder, "")

    # Update date in title (if using merge tags, Mailchimp handles this)
    # But we can also set a static date if needed
    # The template uses *|DATE:l, F j, Y|* which Mailchimp will replace

    return template


def preview_newsletter(
    sections: dict[str, list[dict]], output_path: Optional[str] = None
) -> str:
    """
    Generate newsletter HTML and optionally save to file for preview.

    Args:
        sections: Dict mapping section names to lists of stories
        output_path: Optional path to save HTML file

    Returns:
        HTML string
    """
    html = build_newsletter(sections)

    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"Preview saved to: {output_path}")

    return html


def count_stories(sections: dict[str, list[dict]]) -> dict[str, int]:
    """Count stories per section."""
    return {section: len(stories) for section, stories in sections.items()}


if __name__ == "__main__":
    import sys

    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    # Test with sample data
    test_sections = {
        "top_stories": [
            {
                "headline": "NJ Transit announces major service expansion to Newark Airport",
                "url": "https://example.com/1",
                "source": "NJ.com",
            },
            {
                "headline": "Governor Murphy signs sweeping climate legislation",
                "sources": [
                    ("NJ Spotlight", "https://example.com/2a"),
                    ("NJ Monitor", "https://example.com/2b"),
                    ("WHYY", "https://example.com/2c"),
                ],
            },
        ],
        "politics": [
            {
                "headline": "State Senate passes budget with record education funding",
                "url": "https://example.com/3",
                "source": "NJ Globe",
            }
        ],
        "housing": [
            {
                "headline": "Jersey City approves 500-unit affordable housing development",
                "url": "https://example.com/4",
                "source": "Jersey Digs",
            }
        ],
        "education": [
            {
                "headline": "Rutgers announces tuition freeze for 2025-26 academic year",
                "url": "https://example.com/5",
                "source": "NJ.com",
            }
        ],
        "health": [
            {
                "headline": "New hospital opens in Camden, first in decades",
                "url": "https://example.com/6",
                "source": "NJ Spotlight",
            }
        ],
        "environment": [
            {
                "headline": "Offshore wind farm begins generating power off Atlantic City coast",
                "url": "https://example.com/7",
                "source": "Press of Atlantic City",
            }
        ],
        "lastly": [
            {
                "headline": "New Jersey diner named best in America by Food Network",
                "url": "https://example.com/8",
                "source": "NJ Monthly",
            },
            {
                "headline": "Devils secure playoff spot with overtime win",
                "url": "https://example.com/9",
                "source": "NorthJersey.com",
            },
        ],
    }

    print("=" * 60)
    print("HTML FORMATTER TEST")
    print("=" * 60)

    # Count stories
    counts = count_stories(test_sections)
    print("\nStory counts:")
    for section, count in counts.items():
        print(f"  {section}: {count}")

    # Generate preview
    output_file = Path(__file__).parent.parent / "drafts" / "preview.html"
    output_file.parent.mkdir(exist_ok=True)

    html = preview_newsletter(test_sections, str(output_file))
    print(f"\nGenerated {len(html):,} characters of HTML")
    print(f"Preview saved to: {output_file}")
