"""Story classifier using Claude API to categorize news stories."""

import json
import os
from typing import Optional

import anthropic
from dotenv import load_dotenv

load_dotenv()

# Newsletter sections
SECTIONS = [
    "top_stories",
    "politics",
    "housing",
    "education",
    "health",
    "environment",
    "lastly",
    "skip",  # For non-NJ or irrelevant content
]

# Section descriptions based on historical newsletter patterns
SECTION_DESCRIPTIONS = {
    "top_stories": "Major NJ POLICY news with statewide impact: stories covered by 2+ major NJ outlets (NJ Monitor, NJ Spotlight, NJ Globe, NJ.com), major court rulings, statewide investigations, government accountability, budget/fiscal news, infrastructure (Gateway Tunnel), immigration policy, election coverage. NEVER include: individual crimes, car crashes, fires, murders, 'if it bleeds it leads' stories, local incidents without policy implications.",
    "politics": "NJ government and policy: NJ legislature bills/votes, elections/campaigns, county/municipal government, court decisions, cannabis licensing/policy, corruption/scandals, open records/transparency, NJ Transit policy, taxes/budgets, police reform. Focus on NEW JERSEY government only.",
    "housing": "NJ housing and development: affordable housing projects, rent control, utility shutoffs, zoning decisions, real estate market, Blue Acres flood buyouts, senior housing, warehouse developments, property tax, homelessness, evictions. Must be about New Jersey locations.",
    "education": "NJ education: K-12 school budgets, school board elections/controversies, higher ed (Rutgers, MSU, community colleges), curriculum debates (sex ed), teacher issues, student mental health, school start times, school segregation. Must involve New Jersey educational institutions.",
    "health": "NJ health: COVID updates (cases, vaccines, mandates), hospital news, health disparities, public health policy, mental health, nursing homes, healthcare access. Must be about New Jersey healthcare or directly affect NJ residents.",
    "environment": "NJ environment: offshore wind projects, clean energy policy, warehouse bans (environmental impact), significant weather events (NOT routine forecasts), tree preservation, Superfund sites/PFAS, climate initiatives, plastic bag ban, Pinelands, spotted lanternfly. Must be about New Jersey.",
    "lastly": "Lighter NJ news: arts/culture, NJ sports (Devils, local teams), restaurants/food, community events, human interest profiles, tourism (shore, AC), product recalls, casinos, local celebrations. Lighter news with NJ focus.",
    "skip": "NOT for newsletter: National/wire stories without NJ focus, NYC-only news (Manhattan, Brooklyn, etc.), generic health/lifestyle advice, Pennsylvania/Delaware news, national politics without NJ angle, stories that only mention NJ in passing, individual crimes/crashes without policy implications.",
}

# Keywords that indicate NJ relevance
NJ_KEYWORDS = [
    "new jersey",
    "n.j.",
    "nj",
    "jersey",
    "newark",
    "trenton",
    "camden",
    "paterson",
    "jersey city",
    "elizabeth",
    "edison",
    "woodbridge",
    "lakewood",
    "toms river",
    "hamilton",
    "clifton",
    "brick",
    "cherry hill",
    "passaic",
    "union city",
    "bayonne",
    "east orange",
    "vineland",
    "new brunswick",
    "perth amboy",
    "hoboken",
    "plainfield",
    "hackensack",
    "sayreville",
    "kearny",
    "linden",
    "atlantic city",
    "montclair",
    "maplewood",
    "south orange",
    "morristown",
    "princeton",
    "rutgers",
    "murphy",
    "sherrill",
    "nj transit",
    "garden state",
    "turnpike",
    "parkway",
    "shore",
    "pinelands",
    "meadowlands",
]

# Keywords that indicate non-NJ content to skip
SKIP_KEYWORDS = [
    "new york city",
    "nyc",
    "manhattan",
    "brooklyn",
    "queens",
    "bronx",
    "staten island",
    "long island",
    "upstate new york",
    "westchester",
    "connecticut",
    "pennsylvania",
    "washington d.c.",
    "california",
    "texas",
    "florida",
    "chicago",
    "los angeles",
    "trump tower",
    "white house",  # National politics without NJ angle
]

# Keywords that should NEVER be in top_stories (crime/crash/"if it bleeds it leads")
# These stories should go to skip or other sections, not top_stories
TOP_STORIES_EXCLUSION_KEYWORDS = [
    # Crime
    "carjacked",
    "carjacking",
    "robbed",
    "robbery",
    "robbery",
    "murder",
    "murdered",
    "homicide",
    "killed",
    "killing",
    "stabbed",
    "stabbing",
    "shot",
    "shooting",
    "assault",
    "assaulted",
    "armed robbery",
    "home invasion",
    "burglar",
    "burglary",
    "theft",
    "stolen",
    "arson",
    "kidnapped",
    "kidnapping",
    "rape",
    "raped",
    "sex assault",
    "sexual assault",
    "manslaughter",
    "hit-and-run",
    "hit and run",
    "drug bust",
    "drug arrest",
    "overdose",
    "found dead",
    "body found",
    # Crashes/accidents
    "crash",
    "crashed",
    "fatal crash",
    "deadly crash",
    "wrong-way driver",
    "car accident",
    "vehicle accident",
    "truck crash",
    "bus crash",
    "pedestrian struck",
    "pedestrian hit",
    "pedestrian killed",
    "motorcyclist killed",
    "cyclist killed",
    "dies in crash",
    "killed in crash",
    "injured in crash",
    "multi-car",
    "multi-vehicle",
    "pileup",
    "pile-up",
    "rollover",
    # Fires/disasters (unless policy-related)
    "house fire",
    "apartment fire",
    "building fire",
    "blaze kills",
    "fire kills",
    "explosion kills",
    "gas explosion",
    # Other incidents
    "drowning",
    "drowned",
    "missing person",
    "amber alert",
    "child abduction",
    # High school sports
    "high school football",
    "high school basketball",
    "high school soccer",
    "high school baseball",
    "high school softball",
    "high school wrestling",
    "high school hockey",
    "high school lacrosse",
    "high school track",
    "varsity",
    "jv ",
    "junior varsity",
    "state championship",
    "tournament seeds",
    "all-state",
    "all-county",
    "player of the week",
    "athlete of the week",
    "game of the week",
    "final score",
    "box score",
    "playoff bracket",
    # Shopping/gift guides/deals
    "gift guide",
    "gift ideas",
    "holiday gifts",
    "best gifts",
    "top gifts",
    "shopping guide",
    "deals",
    "discount",
    "sale prices",
    "black friday",
    "cyber monday",
    "where to buy",
    "best places to buy",
    "shopping list",
    "stocking stuffers",
    # Lottery/gambling results
    "lottery",
    "powerball",
    "mega millions",
    "winning numbers",
    "jackpot winner",
    "lottery winner",
    "scratch-off",
    "pick-6",
    "pick 6",
    "cash5",
    "cash 5",
    # Restaurant/food reviews
    "restaurant review",
    "food review",
    "best restaurants",
    "best pizza",
    "best bagels",
    "best diners",
    "best burgers",
    "best tacos",
    "best sushi",
    "best ice cream",
    "best coffee",
    "where to eat",
    "new restaurant",
    "restaurant opens",
    "restaurant closing",
    "michelin",
    "food critic",
    "we tried",
    "taste test",
    "food ranking",
    "ranked the best",
    # Expensive house sales (rich people real estate porn)
    "most expensive home",
    "most expensive house",
    "mansion sells",
    "mansion sold",
    "just sold for",
    "sells for $",
    "sold for $",
    "million-dollar home",
    "multi-million",
    "luxury home sells",
    "priciest home",
    "record-breaking sale",
    "celebrity home",
    "stunning home",
    "dream home sold",
    "these homes just sold",
    "houses that sold",
    "highest-priced",
]


def is_crime_or_crash_headline(headline: str) -> bool:
    """
    Check if a headline is about crime, crashes, or other incidents
    that shouldn't be in top_stories.

    Args:
        headline: Story headline

    Returns:
        True if this is a crime/crash story
    """
    headline_lower = headline.lower()
    for keyword in TOP_STORIES_EXCLUSION_KEYWORDS:
        if keyword in headline_lower:
            return True
    return False


def filter_top_stories(stories: list[dict]) -> list[dict]:
    """
    Post-classification filter to move crime/crash stories out of top_stories.

    Stories with crime/crash keywords are moved to 'skip' section.

    Args:
        stories: List of classified stories

    Returns:
        Stories with top_stories filtered
    """
    filtered_count = 0
    for story in stories:
        if story.get("section") == "top_stories":
            headline = story.get("headline", story.get("title", ""))
            if is_crime_or_crash_headline(headline):
                story["section"] = "skip"
                story["filter_reason"] = "crime/crash content excluded from top_stories"
                filtered_count += 1

    if filtered_count > 0:
        print(f"   Filtered {filtered_count} crime/crash stories from top_stories")

    return stories


def classify_story(
    headline: str, url: str, summary: Optional[str] = None, source: Optional[str] = None
) -> dict:
    """
    Classify a single story into a newsletter section using Claude.

    Args:
        headline: Story headline
        url: Story URL
        summary: Optional story summary
        source: Optional source name

    Returns:
        Dict with section, confidence, and reasoning
    """
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    # Build context
    story_info = f"Headline: {headline}\nURL: {url}"
    if summary:
        story_info += f"\nSummary: {summary}"
    if source:
        story_info += f"\nSource: {source}"

    section_list = "\n".join(
        [f"- {section}: {desc}" for section, desc in SECTION_DESCRIPTIONS.items()]
    )

    prompt = f"""You are classifying news stories for a NEW JERSEY-focused daily newsletter.

CRITICAL: This newsletter is ONLY for New Jersey news. Stories must be directly about New Jersey.

Given this story:
{story_info}

Classify it into ONE of these sections:
{section_list}

Respond with JSON only:
{{"section": "section_name", "confidence": 0.0-1.0, "reasoning": "brief explanation"}}

Rules:
- FIRST: Check if story is about New Jersey. Use "skip" if:
  - Story is about NYC, NY state, Pennsylvania, or other states (unless NJ is primary focus)
  - Story is national news without a specific NJ angle
  - Story is generic health/lifestyle advice not specific to NJ
  - Story mentions NJ only in passing but focuses elsewhere

- TOP_STORIES is ONLY for major POLICY news with statewide impact:
  - Stories covered by multiple major NJ outlets
  - Government accountability, investigations, major court rulings
  - Budget/fiscal news, infrastructure, immigration policy
  - NEVER put crimes, car crashes, fires, murders, or "if it bleeds it leads" in top_stories
  - Individual incidents without policy implications go elsewhere or skip

- Light/fun NJ stories, arts, sports, restaurants = "lastly"
- When uncertain between sections, choose the more specific one
- Confidence should reflect how clearly it fits the section"""

    try:
        message = client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        )

        response_text = message.content[0].text.strip()

        # Parse JSON from response
        # Handle potential markdown code blocks
        if "```" in response_text:
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]
            response_text = response_text.strip()

        result = json.loads(response_text)

        # Validate section
        if result.get("section") not in SECTIONS:
            result["section"] = "lastly"  # Default fallback

        return result

    except Exception as e:
        print(f"Classification error for '{headline[:50]}...': {e}")
        return {
            "section": "lastly",
            "confidence": 0.3,
            "reasoning": f"Classification failed: {str(e)}",
        }


def classify_stories_batch(
    stories: list[dict], max_per_request: int = 10
) -> list[dict]:
    """
    Classify multiple stories efficiently using batch requests.

    Args:
        stories: List of story dicts with headline, url, etc.
        max_per_request: Max stories to classify in one API call

    Returns:
        List of stories with section assignments added
    """
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    results = []

    # Process in batches
    for i in range(0, len(stories), max_per_request):
        batch = stories[i : i + max_per_request]

        # Build batch prompt
        stories_text = "\n\n".join(
            [
                f"[{j + 1}] Headline: {s.get('headline', s.get('title', ''))}\n"
                f"    URL: {s.get('url', '')}\n"
                f"    Source: {s.get('source', 'Unknown')}"
                for j, s in enumerate(batch)
            ]
        )

        section_list = "\n".join(
            [f"- {section}: {desc}" for section, desc in SECTION_DESCRIPTIONS.items()]
        )

        prompt = f"""Classify these news stories for a NEW JERSEY-focused daily newsletter.

CRITICAL: This newsletter is ONLY for New Jersey news. Stories must be directly about New Jersey.

Stories:
{stories_text}

Sections:
{section_list}

Respond with JSON array only - one object per story in order:
[{{"story": 1, "section": "section_name", "confidence": 0.0-1.0}}, ...]

Rules:
- FIRST: Check if each story is about New Jersey. Use "skip" if:
  - Story is about NYC, NY state, Pennsylvania, or other states (unless NJ is primary focus)
  - Story is national news without a specific NJ angle
  - Story is generic health/lifestyle advice not specific to NJ
  - Story mentions NJ only in passing but focuses elsewhere

- TOP_STORIES is ONLY for major POLICY news with statewide impact:
  - Stories covered by multiple major NJ outlets
  - Government accountability, investigations, major court rulings
  - Budget/fiscal news, infrastructure, immigration policy
  - NEVER put crimes, car crashes, fires, murders, or "if it bleeds it leads" in top_stories
  - Individual incidents without policy implications go elsewhere or skip

- Light/fun NJ stories, arts, sports, restaurants, human interest = "lastly"
- Choose the most specific applicable section"""

        try:
            message = client.messages.create(
                model="claude-3-haiku-20240307",
                max_tokens=500,
                messages=[{"role": "user", "content": prompt}],
            )

            response_text = message.content[0].text.strip()

            # Parse JSON
            if "```" in response_text:
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
                response_text = response_text.strip()

            classifications = json.loads(response_text)

            # Merge classifications with stories
            for j, story in enumerate(batch):
                story_copy = story.copy()
                if j < len(classifications):
                    cls = classifications[j]
                    story_copy["section"] = cls.get("section", "lastly")
                    story_copy["confidence"] = cls.get("confidence", 0.5)
                else:
                    story_copy["section"] = "lastly"
                    story_copy["confidence"] = 0.3
                results.append(story_copy)

        except Exception as e:
            print(f"Batch classification error: {e}")
            # Fall back to individual classification
            for story in batch:
                result = classify_story(
                    headline=story.get("headline", story.get("title", "")),
                    url=story.get("url", ""),
                    summary=story.get("summary"),
                    source=story.get("source"),
                )
                story_copy = story.copy()
                story_copy["section"] = result["section"]
                story_copy["confidence"] = result["confidence"]
                results.append(story_copy)

    return results


def select_best_headline(headlines: list[str]) -> str:
    """
    Given multiple headlines for the same story, select the best one.

    Args:
        headlines: List of headlines from different outlets

    Returns:
        The best headline (clear, accurate, not clickbaity)
    """
    if len(headlines) == 1:
        return headlines[0]

    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    headlines_text = "\n".join([f"{i + 1}. {h}" for i, h in enumerate(headlines)])

    prompt = f"""Select the best headline from these options covering the same story:

{headlines_text}

Choose the headline that:
- Best captures the essence of the story
- Is clear and informative
- Is NOT clickbaity or hyperbolic
- Uses appropriate tone

Respond with just the number of the best headline."""

    try:
        message = client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=10,
            messages=[{"role": "user", "content": prompt}],
        )

        response = message.content[0].text.strip()
        # Extract number
        num = int("".join(c for c in response if c.isdigit()))
        if 1 <= num <= len(headlines):
            return headlines[num - 1]
    except Exception:
        pass

    # Fallback: return first headline
    return headlines[0]


if __name__ == "__main__":
    import sys

    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    # Test classification
    test_stories = [
        {
            "headline": "Murphy signs bill expanding offshore wind development in New Jersey",
            "url": "https://example.com/1",
            "source": "NJ Spotlight",
        },
        {
            "headline": "Jersey City school board approves $1.2 billion budget",
            "url": "https://example.com/2",
            "source": "NJ.com",
        },
        {
            "headline": "New ramen shop opens in Montclair, draws crowds",
            "url": "https://example.com/3",
            "source": "Montclair Local",
        },
        {
            "headline": "NJ Transit fares to increase 15% starting July 1",
            "url": "https://example.com/4",
            "source": "NorthJersey.com",
        },
    ]

    print("=" * 60)
    print("CLASSIFIER TEST")
    print("=" * 60)

    results = classify_stories_batch(test_stories)

    for story in results:
        print(f"\n{story['source']}: {story['headline'][:50]}...")
        print(
            f"  → Section: {story['section']} (confidence: {story.get('confidence', 'N/A')})"
        )
