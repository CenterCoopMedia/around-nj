"""
Daily News Roundup - Main Pipeline

This script orchestrates the full newsletter generation workflow:
1. Fetch stories from RSS feeds
2. Fetch submissions from Airtable
3. Classify stories into sections
4. Deduplicate and group similar stories
5. Format as HTML
6. Create Mailchimp draft campaign

Usage:
    python src/main.py              # Run full pipeline, create draft
    python src/main.py --preview    # Preview only, no Mailchimp
    python src/main.py --dry-run    # Show what would be included
"""

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

from airtable_fetcher import SECTION_MAP, fetch_submissions
from classifier import SECTIONS, classify_stories_batch, filter_top_stories
from html_formatter import build_newsletter, count_stories
from rss_fetcher import fetch_all_feeds

try:
    from playwright_fetcher import fetch_all_playwright_sources

    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    fetch_all_playwright_sources = None
    PLAYWRIGHT_AVAILABLE = False

try:
    from url_enricher import enrich_stories_batch

    ENRICHMENT_AVAILABLE = True
except ImportError:
    enrich_stories_batch = None
    ENRICHMENT_AVAILABLE = False

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

load_dotenv()


def fetch_all_stories(
    hours_back: int = 24, include_playwright: bool = False
) -> list[dict]:
    """
    Fetch stories from all sources (RSS + Airtable + optionally Playwright).

    Args:
        hours_back: How many hours back to look for RSS stories
        include_playwright: Whether to fetch from Playwright sources (slower)

    Returns:
        Combined list of stories from all sources
    """
    print("\n📡 Fetching stories from RSS feeds...")
    rss_stories = fetch_all_feeds(hours_back=hours_back, priority_filter=2)
    print(f"   Found {len(rss_stories)} RSS stories")

    # Optionally fetch from Playwright sources (sites with broken RSS)
    playwright_stories = []
    if include_playwright and PLAYWRIGHT_AVAILABLE:
        playwright_stories = fetch_all_playwright_sources(hours_back=hours_back)
        print(f"   Found {len(playwright_stories)} Playwright stories")
    elif include_playwright and not PLAYWRIGHT_AVAILABLE:
        print("   Playwright not available (install with: pip install playwright)")

    print("\n📋 Fetching submissions from Airtable...")
    airtable_stories = fetch_submissions(days_back=7)
    print(f"   Found {len(airtable_stories)} Airtable submissions")

    # Combine all sources
    all_stories = rss_stories + playwright_stories + airtable_stories
    print(f"\n📊 Total stories to process: {len(all_stories)}")

    return all_stories


def classify_all_stories(stories: list[dict]) -> list[dict]:
    """
    Classify stories into newsletter sections.

    Stories from Airtable with sections already assigned keep their sections.
    RSS stories get classified via Claude API.

    Args:
        stories: List of story dicts

    Returns:
        Stories with section assignments
    """
    print("\n🏷️  Classifying stories...")

    # Separate pre-classified (Airtable) from unclassified (RSS)
    classified = []
    to_classify = []

    for story in stories:
        if story.get("from_airtable") and story.get("section"):
            # Map Airtable section name to newsletter section
            airtable_section = story["section"]
            newsletter_section = SECTION_MAP.get(airtable_section, "lastly")
            story["section"] = newsletter_section
            classified.append(story)
        else:
            to_classify.append(story)

    print(f"   Pre-classified (Airtable): {len(classified)}")
    print(f"   Need classification: {len(to_classify)}")

    # Classify RSS stories in batches
    if to_classify:
        print("   Classifying via Claude API...")
        newly_classified = classify_stories_batch(to_classify)
        classified.extend(newly_classified)

    # Post-classification filter: remove crime/crash from top_stories
    classified = filter_top_stories(classified)

    return classified


def deduplicate_stories(stories: list[dict]) -> list[dict]:
    """
    Remove duplicate stories based on URL.

    TODO: Implement smarter grouping of related stories.

    Args:
        stories: List of stories

    Returns:
        Deduplicated list
    """
    print("\n🔄 Deduplicating stories...")

    seen_urls = set()
    unique = []

    for story in stories:
        url = story.get("url", "")
        if url and url not in seen_urls:
            seen_urls.add(url)
            unique.append(story)

    removed = len(stories) - len(unique)
    print(f"   Removed {removed} duplicates, {len(unique)} unique stories")

    return unique


def organize_by_section(
    stories: list[dict], max_top_stories: int = 6
) -> dict[str, list[dict]]:
    """
    Organize stories by section.

    Args:
        stories: Classified stories
        max_top_stories: Maximum stories for top_stories section

    Returns:
        Dict mapping section names to story lists (excludes "skip" section)
    """
    print("\n📁 Organizing by section...")

    # Create sections dict excluding "skip" - those stories are filtered out
    newsletter_sections = [s for s in SECTIONS if s != "skip"]
    sections = {section: [] for section in newsletter_sections}

    skipped_count = 0

    for story in stories:
        section = story.get("section", "lastly")
        # Filter out stories marked as "skip" (non-NJ content)
        if section == "skip":
            skipped_count += 1
            continue
        if section in sections:
            sections[section].append(story)
        else:
            sections["lastly"].append(story)

    if skipped_count > 0:
        print(f"   Filtered out {skipped_count} non-NJ stories")

    # Enforce top_stories limit
    if len(sections["top_stories"]) > max_top_stories:
        # Move overflow to appropriate sections based on content
        overflow = sections["top_stories"][max_top_stories:]
        sections["top_stories"] = sections["top_stories"][:max_top_stories]
        # Re-classify overflow
        for story in overflow:
            # Try to find a better section based on keywords
            headline = story.get("headline", story.get("title", "")).lower()
            if any(
                kw in headline
                for kw in ["governor", "legislature", "election", "court"]
            ):
                sections["politics"].append(story)
            elif any(
                kw in headline for kw in ["housing", "rent", "development", "zoning"]
            ):
                sections["housing"].append(story)
            elif any(
                kw in headline
                for kw in ["school", "education", "university", "teacher"]
            ):
                sections["education"].append(story)
            elif any(
                kw in headline for kw in ["health", "hospital", "covid", "medical"]
            ):
                sections["health"].append(story)
            elif any(
                kw in headline
                for kw in ["climate", "environment", "energy", "pollution"]
            ):
                sections["environment"].append(story)
            else:
                sections["lastly"].append(story)

    return sections


def create_mailchimp_draft(
    html_content: str, subject: Optional[str] = None
) -> Optional[str]:
    """
    Create a draft campaign in Mailchimp.

    Args:
        html_content: Full newsletter HTML
        subject: Email subject line (defaults to date-based)

    Returns:
        Campaign ID if successful, None otherwise
    """
    import mailchimp_marketing as MailchimpMarketing
    from mailchimp_marketing.api_client import ApiClientError

    print("\n📧 Creating Mailchimp draft campaign...")

    if not subject:
        today = datetime.now()
        # Format: "Daily News Roundup: Dec. 16, 2025"
        subject = f"Daily News Roundup: {today.strftime('%b. %d, %Y')}"

    try:
        client = MailchimpMarketing.Client()
        client.set_config(
            {
                "api_key": os.getenv("MAILCHIMP_API_KEY"),
                "server": os.getenv("MAILCHIMP_SERVER_PREFIX"),
            }
        )

        list_id = os.getenv("MAILCHIMP_LIST_ID")

        # Create campaign
        campaign = client.campaigns.create(
            {
                "type": "regular",
                "recipients": {"list_id": list_id},
                "settings": {
                    "subject_line": subject,
                    "title": f"DNR - {datetime.now().strftime('%Y-%m-%d')}",
                    "from_name": "NJ News Commons",
                    "reply_to": "info@centerforcooperativemedia.org",
                    "preview_text": "The latest stories from across the NJ news ecosystem.",
                },
            }
        )

        campaign_id = campaign["id"]
        print(f"   Created campaign: {campaign_id}")

        # Set content
        client.campaigns.set_content(campaign_id, {"html": html_content})
        print("   Content uploaded successfully")

        # Get web link
        campaign_info = client.campaigns.get(campaign_id)
        web_id = campaign_info.get("web_id")

        print("\n✅ Draft created successfully!")
        print(f"   Campaign ID: {campaign_id}")
        print(
            f"   Edit in Mailchimp: https://us5.admin.mailchimp.com/campaigns/edit?id={web_id}"
        )

        return campaign_id

    except ApiClientError as e:
        print(f"\n❌ Mailchimp error: {e.text}")
        return None
    except Exception as e:
        print(f"\n❌ Error creating campaign: {e}")
        return None


def run_pipeline(
    hours_back: int = 24,
    preview_only: bool = False,
    dry_run: bool = False,
    output_dir: Optional[str] = None,
    include_playwright: bool = False,
    enrich_stories: bool = False,
    enrich_max: int = 20,
) -> Optional[str]:
    """
    Run the full newsletter generation pipeline.

    Args:
        hours_back: How far back to look for RSS stories
        preview_only: If True, generate HTML but don't create Mailchimp draft
        dry_run: If True, just show counts without generating
        output_dir: Directory for preview HTML output
        include_playwright: If True, also fetch from Playwright sources (slower)
        enrich_stories: If True, enrich stories with Gemini URL context
        enrich_max: Maximum stories to enrich (to control API costs)

    Returns:
        Campaign ID if created, preview path if preview_only, None otherwise
    """
    print("=" * 60)
    print("🗞️  DAILY NEWS ROUNDUP - PIPELINE")
    print("=" * 60)
    print(f"   Date: {datetime.now().strftime('%A, %B %d, %Y')}")
    mode_str = "Dry run" if dry_run else "Preview" if preview_only else "Full pipeline"
    if include_playwright:
        mode_str += " + Playwright"
    if enrich_stories:
        mode_str += " + Enrichment"
    print(f"   Mode: {mode_str}")

    # Step 1: Fetch stories
    stories = fetch_all_stories(
        hours_back=hours_back, include_playwright=include_playwright
    )

    if not stories:
        print("\n⚠️  No stories found!")
        return None

    if dry_run:
        print("\n📊 Dry run complete - story counts only")
        return None

    # Optional: Enrich stories with URL context
    if enrich_stories and ENRICHMENT_AVAILABLE:
        stories = enrich_stories_batch(stories, max_stories=enrich_max)
    elif enrich_stories and not ENRICHMENT_AVAILABLE:
        print("   Enrichment not available (install google-generativeai)")

    # Step 2: Classify
    classified = classify_all_stories(stories)

    # Step 3: Deduplicate
    unique = deduplicate_stories(classified)

    # Step 4: Organize by section
    sections = organize_by_section(unique)

    # Show counts
    counts = count_stories(sections)
    print("\n📊 Stories by section:")
    total = 0
    for section, count in counts.items():
        emoji = {
            "top_stories": "📰",
            "politics": "🏛️",
            "housing": "🏘️",
            "education": "🏫",
            "health": "🦠",
            "environment": "🌳",
            "lastly": "☝️",
        }.get(section, "•")
        print(f"   {emoji} {section}: {count}")
        total += count
    print(f"   Total: {total}")

    # Step 5: Generate HTML
    print("\n📝 Generating HTML...")
    html = build_newsletter(sections)
    print(f"   Generated {len(html):,} characters")

    # Save preview
    if output_dir is None:
        output_dir = Path(__file__).parent.parent / "drafts"
    else:
        output_dir = Path(output_dir)

    output_dir.mkdir(exist_ok=True)
    preview_path = output_dir / f"dnr-{datetime.now().strftime('%Y-%m-%d')}.html"

    with open(preview_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"   Preview saved: {preview_path}")

    if preview_only:
        print("\n✅ Preview mode complete")
        return str(preview_path)

    # Step 6: Create Mailchimp draft
    campaign_id = create_mailchimp_draft(html)

    return campaign_id


def main():
    parser = argparse.ArgumentParser(description="Daily News Roundup Pipeline")
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Generate preview only, don't create Mailchimp draft",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Show story counts without generating"
    )
    parser.add_argument(
        "--hours",
        type=int,
        default=24,
        help="Hours back to look for RSS stories (default: 24)",
    )
    parser.add_argument("--output", type=str, help="Output directory for preview HTML")
    parser.add_argument(
        "--playwright",
        action="store_true",
        help="Include Playwright sources (slower, for paywalled/broken RSS sites)",
    )
    parser.add_argument(
        "--enrich",
        action="store_true",
        help="Enrich stories with Gemini URL context (uses API credits)",
    )
    parser.add_argument(
        "--enrich-max", type=int, default=20, help="Max stories to enrich (default: 20)"
    )

    args = parser.parse_args()

    result = run_pipeline(
        hours_back=args.hours,
        preview_only=args.preview,
        dry_run=args.dry_run,
        output_dir=args.output,
        include_playwright=args.playwright,
        enrich_stories=args.enrich,
        enrich_max=args.enrich_max,
    )

    if result:
        print(f"\n🎉 Pipeline complete: {result}")
    else:
        print("\n⏹️  Pipeline finished")


if __name__ == "__main__":
    main()
