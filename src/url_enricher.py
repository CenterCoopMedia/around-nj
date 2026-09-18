"""URL enrichment using Google Gemini API with URL context.

This module extracts content and summaries from URLs using Google's Gemini API,
which can read web pages and provide structured information about them.

Use cases:
- Enrich RSS stories that only have headlines (no summary)
- Get better classification context for stories
- Verify story content matches headline
"""

import os
import sys
import time
from typing import Optional

import google.generativeai as genai
from dotenv import load_dotenv

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

load_dotenv()

# Configure Gemini
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)


def extract_story_context(url: str, headline: str = "") -> dict:
    """
    Extract story context from a URL using Gemini.

    Args:
        url: The article URL to analyze
        headline: Optional headline for context

    Returns:
        Dict with summary, topics, location, and entities
    """
    if not GEMINI_API_KEY:
        return {"error": "GEMINI_API_KEY not configured"}

    try:
        model = genai.GenerativeModel("gemini-2.0-flash")

        prompt = f"""Analyze this news article URL and extract key information.

URL: {url}
Headline (if available): {headline}

Please provide a JSON response with:
1. "summary": A 1-2 sentence summary of the article
2. "topics": List of 2-4 topic keywords (e.g., "politics", "housing", "education")
3. "location": Specific NJ location mentioned (city, county, or "statewide")
4. "entities": Key people, organizations, or places mentioned
5. "news_type": One of "breaking", "feature", "opinion", "announcement", "investigation"

Respond with valid JSON only, no markdown."""

        response = model.generate_content(prompt)
        response_text = response.text.strip()

        # Try to parse as JSON
        import json

        if response_text.startswith("```"):
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]
            response_text = response_text.strip()

        result = json.loads(response_text)
        result["url"] = url
        result["success"] = True
        return result

    except Exception as e:
        return {
            "url": url,
            "success": False,
            "error": str(e),
            "summary": None,
            "topics": [],
            "location": None,
        }


def enrich_stories_batch(
    stories: list[dict], max_stories: int = 20, delay: float = 0.5
) -> list[dict]:
    """
    Enrich multiple stories with URL context.

    Args:
        stories: List of story dicts
        max_stories: Maximum stories to enrich (to control API costs)
        delay: Delay between API calls in seconds

    Returns:
        Stories with enrichment data added
    """
    if not GEMINI_API_KEY:
        print("GEMINI_API_KEY not configured, skipping enrichment")
        return stories

    print(f"\n🔍 Enriching up to {max_stories} stories with URL context...")

    enriched = []
    enriched_count = 0

    for story in stories:
        # Skip if already has good summary
        if story.get("summary") and len(story.get("summary", "")) > 100:
            enriched.append(story)
            continue

        # Only enrich up to max_stories
        if enriched_count >= max_stories:
            enriched.append(story)
            continue

        url = story.get("url", "")
        headline = story.get("headline", story.get("title", ""))

        if url:
            context = extract_story_context(url, headline)

            if context.get("success"):
                story["enriched_summary"] = context.get("summary")
                story["enriched_topics"] = context.get("topics", [])
                story["enriched_location"] = context.get("location")
                story["enriched_type"] = context.get("news_type")
                enriched_count += 1
                print(f"   Enriched: {headline[:50]}...")

            time.sleep(delay)  # Rate limiting

        enriched.append(story)

    print(f"   Enriched {enriched_count} stories")
    return enriched


def get_story_summary(url: str) -> Optional[str]:
    """
    Get just the summary for a single URL.

    Args:
        url: Article URL

    Returns:
        Summary string or None
    """
    context = extract_story_context(url)
    return context.get("summary") if context.get("success") else None


if __name__ == "__main__":
    # Test with a sample URL
    test_urls = [
        "https://www.nj.com/politics/2025/12/casino-smoking-battle-faces-fresh-scrutiny-as-judges-cite-new-science-new-realities.html?outputType=amp",
        "https://newjerseymonitor.com/2025/12/16/nj-paid-family-leave-small-businesses/",
    ]

    print("=" * 60)
    print("URL ENRICHER TEST")
    print("=" * 60)

    for url in test_urls:
        print(f"\nTesting: {url[:60]}...")
        result = extract_story_context(url)

        if result.get("success"):
            print(f"  Summary: {result.get('summary', 'N/A')[:100]}...")
            print(f"  Topics: {result.get('topics', [])}")
            print(f"  Location: {result.get('location', 'N/A')}")
            print(f"  Type: {result.get('news_type', 'N/A')}")
        else:
            print(f"  Error: {result.get('error', 'Unknown')}")
