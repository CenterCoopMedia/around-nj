"""Interactive DNR workflow - preview, review, approve, publish.

This script provides a guided workflow for creating the Daily News Roundup:
1. Fetch and classify stories
2. Generate HTML preview
3. Open preview in browser for review
4. Prompt for approval
5. Create Mailchimp draft if approved

Schedule: Monday through Thursday mornings
- Monday: Pulls content from Friday 5am until now (covers weekend)
- Tuesday-Thursday: Pulls content from last 36 hours

Usage:
    python src/workflow.py              # Standard workflow (auto-detects hours)
    python src/workflow.py --playwright # Include paywalled sites
    python src/workflow.py --enrich     # Include URL enrichment
    python src/workflow.py --hours 48   # Override auto-detection
"""

import argparse
import json
import os
import sys
import webbrowser
from datetime import datetime, timedelta
from importlib.util import find_spec
from pathlib import Path

import anthropic
from dotenv import load_dotenv

from airtable_fetcher import update_submissions_batch
from html_formatter import build_newsletter, count_stories
from main import (
    classify_all_stories,
    create_mailchimp_draft,
    deduplicate_stories,
    fetch_all_stories,
    organize_by_section,
)

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

load_dotenv()


# Day of week constants
MONDAY = 0
TUESDAY = 1
WEDNESDAY = 2
THURSDAY = 3
FRIDAY = 4
SATURDAY = 5
SUNDAY = 6

DAY_NAMES = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
]


def calculate_hours_back() -> tuple[int, str]:
    """
    Calculate how many hours back to fetch stories based on current day.

    Returns:
        Tuple of (hours_back, explanation)

    Schedule logic:
    - Monday: From Friday 5am until now (covers weekend news)
    - Tuesday-Thursday: Last 36 hours
    - Friday-Sunday: Not a normal publish day, defaults to 24 hours
    """
    now = datetime.now()
    day_of_week = now.weekday()

    if day_of_week == MONDAY:
        # Monday: go back to Friday 5am
        # Calculate hours from Friday 5am to now
        days_since_friday = 3  # Mon=0, Fri was 3 days ago
        friday_5am = now.replace(hour=5, minute=0, second=0, microsecond=0) - timedelta(
            days=days_since_friday
        )
        hours_back = int((now - friday_5am).total_seconds() / 3600)
        explanation = (
            f"Monday edition: covering Friday 5am through now ({hours_back} hours)"
        )
        return hours_back, explanation

    elif day_of_week in (TUESDAY, WEDNESDAY, THURSDAY):
        # Tue-Thu: 36 hours back
        hours_back = 36
        explanation = f"{DAY_NAMES[day_of_week]} edition: last 36 hours"
        return hours_back, explanation

    else:
        # Friday, Saturday, Sunday - not normal publish days
        hours_back = 24
        explanation = (
            f"{DAY_NAMES[day_of_week]}: not a normal publish day (using 24 hours)"
        )
        return hours_back, explanation


def check_publish_day() -> tuple[bool, str]:
    """
    Check if today is a normal DNR publish day.

    Returns:
        Tuple of (is_publish_day, message)
    """
    day_of_week = datetime.now().weekday()

    if day_of_week in (MONDAY, TUESDAY, WEDNESDAY, THURSDAY):
        return True, f"Today is {DAY_NAMES[day_of_week]} - normal publish day"
    else:
        return (
            False,
            f"Today is {DAY_NAMES[day_of_week]} - NOT a normal publish day (DNR runs Mon-Thu)",
        )


def clear_screen():
    """Clear the terminal screen."""
    os.system("cls" if os.name == "nt" else "clear")


def print_header():
    """Print the workflow header."""
    clear_screen()
    print("=" * 60)
    print("  DAILY NEWS ROUNDUP - WORKFLOW")
    print("=" * 60)
    print(f"  Date: {datetime.now().strftime('%A, %B %d, %Y')}")
    print("=" * 60)
    print()


def print_step(step_num: int, total: int, description: str):
    """Print a step indicator."""
    print(f"\n[Step {step_num}/{total}] {description}")
    print("-" * 40)


def prompt_yes_no(question: str, default: bool = True) -> bool:
    """Prompt user for yes/no response."""
    suffix = " [Y/n]: " if default else " [y/N]: "
    while True:
        response = input(question + suffix).strip().lower()
        if not response:
            return default
        if response in ("y", "yes"):
            return True
        if response in ("n", "no"):
            return False
        print("Please enter 'y' or 'n'")


def prompt_continue():
    """Prompt user to continue."""
    input("\nPress Enter to continue...")


def review_airtable_submissions(classified_stories: list[dict]) -> list[dict]:
    """
    Review and approve source and section assignments for Airtable submissions.

    Both source and section must be set to trigger the notification automation.

    Args:
        classified_stories: List of classified stories (some may be from Airtable)

    Returns:
        List of approved updates to send to Airtable
    """
    # Find stories from Airtable that need review
    # Only include stories that don't have BOTH source and section already set
    airtable_stories = [
        s for s in classified_stories if s.get("from_airtable") and s.get("id")
    ]

    if not airtable_stories:
        print("\n  No Airtable submissions to review.")
        return []

    print(f"\n  Found {len(airtable_stories)} user-submitted stories to review.")
    print("  You'll review the SOURCE and SECTION for each story.")
    print("  Both must be set to trigger the notification email to the submitter.")
    print()
    print("  Commands:")
    print("    - Enter: Approve suggested values")
    print("    - 's': Skip this story (don't update Airtable)")
    print()

    # Section options
    sections = [
        "top_stories",
        "politics",
        "housing",
        "education",
        "health",
        "environment",
        "lastly",
    ]
    section_display = {
        "top_stories": "Top stories",
        "politics": "Politics + government",
        "housing": "Housing + development",
        "education": "Work + education",
        "health": "Health + safety",
        "environment": "Climate + environment",
        "lastly": "Lastly",
    }

    approved_updates = []

    for i, story in enumerate(airtable_stories, 1):
        headline = story.get("headline", story.get("title", "No headline"))[:70]
        url = story.get("url", "")
        current_source = story.get("source", "").strip()
        suggested_section = story.get("section", "lastly")
        submitter = story.get("submitter_name", "Anonymous")
        submitter_email = story.get("submitter_email", "")

        print(f"\n{'=' * 60}")
        print(f"[{i}/{len(airtable_stories)}] {headline}...")
        print(f"    URL: {url[:60]}...")
        print(
            f"    Submitted by: {submitter}"
            + (f" ({submitter_email})" if submitter_email else "")
        )
        print()

        # Step 1: Review/set SOURCE
        print(f"    Current source: {current_source if current_source else '(empty)'}")

        if current_source:
            source_response = input(f"    Source [{current_source}]: ").strip()
            final_source = source_response if source_response else current_source
        else:
            # Try to extract source from URL
            from html_formatter import extract_source_from_url

            suggested_source = extract_source_from_url(url)
            if suggested_source:
                source_response = input(f"    Source [{suggested_source}]: ").strip()
                final_source = source_response if source_response else suggested_source
            else:
                final_source = input("    Source (required): ").strip()
                if not final_source:
                    print("    ⊘ Skipped (source is required)")
                    continue

        # Check for skip
        if final_source.lower() == "s":
            print("    ⊘ Skipped")
            continue

        # Step 2: Review/set SECTION
        print()
        print(
            f"    Suggested section: {section_display.get(suggested_section, suggested_section)}"
        )
        print("    Section options:")
        for j, sec in enumerate(sections, 1):
            marker = " *" if sec == suggested_section else ""
            print(f"      {j}. {section_display.get(sec, sec)}{marker}")

        while True:
            section_response = (
                input("\n    Section (1-7 or Enter to approve): ").strip().lower()
            )

            if section_response == "":
                final_section = suggested_section
                break
            elif section_response == "s":
                final_section = None
                break
            elif section_response.isdigit() and 1 <= int(section_response) <= 7:
                final_section = sections[int(section_response) - 1]
                break
            else:
                print("    Invalid choice. Enter 1-7, 's' to skip, or press Enter.")

        if final_section is None:
            print("    ⊘ Skipped")
            continue

        # Approve the update
        approved_updates.append(
            {"id": story["id"], "source": final_source, "section": final_section}
        )

        # Update the story object for the newsletter
        story["source"] = final_source
        story["section"] = final_section

        print("\n    ✓ Approved:")
        print(f"      Source: {final_source}")
        print(f"      Section: {section_display.get(final_section, final_section)}")

    return approved_updates


def process_feedback(
    sections: dict[str, list[dict]], feedback: str, all_stories: list[dict]
) -> dict[str, list[dict]]:
    """
    Process natural language feedback to modify newsletter sections using Claude AI.

    This function enables editors to refine the newsletter using plain English commands.
    It sends the user's feedback to Claude Haiku, which interprets the request and
    returns structured JSON actions that are then applied to modify the sections.

    Workflow:
        1. Build a summary of current sections (headlines + sources) for context
        2. Send the summary + user feedback to Claude Haiku with a structured prompt
        3. Parse Claude's JSON response into actionable instructions
        4. Apply each action (move/remove) by matching partial headline text
        5. Print confirmation messages for each action taken

    Args:
        sections: Dictionary mapping section names to lists of story dicts.
            Valid section names: 'top_stories', 'politics', 'housing',
            'education', 'health', 'environment', 'lastly'.
            Each story dict should have 'headline' or 'title' and 'source' keys.
        feedback: Natural language instruction from the user, e.g.:
            - "Move the NJ Transit story to politics"
            - "Remove all crime stories from top stories"
            - "Move the Murphy budget story from politics to top_stories"
        all_stories: List of all classified stories (currently unused but passed
            for potential future enhancements like adding stories back).

    Returns:
        The modified sections dict with actions applied. The original dict is
        mutated in-place AND returned for convenience.

    JSON Action Format (returned by Claude):
        The function expects Claude to return JSON in this structure:
        {
            "actions": [
                {
                    "action": "move",
                    "headline_contains": "partial headline text",
                    "from_section": "section_name",
                    "to_section": "section_name"
                },
                {
                    "action": "remove",
                    "headline_contains": "partial headline text",
                    "from_section": "section_name"
                },
                {
                    "action": "note",
                    "message": "Explanation when feedback cannot be processed"
                }
            ]
        }

    Headline Matching:
        - Uses case-insensitive partial string matching
        - The 'headline_contains' value is searched within each story's headline
        - Only the FIRST matching story is affected (not all matches)
        - Matching uses: `headline_contains.lower() in headline.lower()`

    Error Handling:
        - If Claude's response cannot be parsed as JSON, returns sections unchanged
        - If no stories match the requested headline, prints "No matching stories found"
        - Network/API errors are caught and logged, sections returned unchanged
        - Markdown code blocks in Claude's response are automatically stripped

    Example Usage:
        >>> sections = {'top_stories': [{'headline': 'NJ Transit delays'}],
        ...             'politics': []}
        >>> process_feedback(sections, "Move NJ Transit to politics", [])
        # Output: ✓ Moved 'nj transit...' from top_stories to politics
        >>> sections
        {'top_stories': [], 'politics': [{'headline': 'NJ Transit delays'}]}

    Note:
        - Uses Claude claude-3-haiku-20240307 model for fast, cost-effective processing
        - Max tokens set to 500 (sufficient for typical action responses)
        - The function modifies sections in-place; callers should regenerate HTML after
    """
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    # --- Step 1: Build context for Claude ---
    # Create a text summary of all sections and their stories so Claude understands
    # the current newsletter state. We limit to 15 stories per section and truncate
    # headlines to 70 chars to stay within reasonable token limits.
    sections_summary = []
    for section_name, stories in sections.items():
        if stories:
            sections_summary.append(
                f"\n{section_name.upper()} ({len(stories)} stories):"
            )
            for i, story in enumerate(
                stories[:15], 1
            ):  # Limit context to first 15 per section
                headline = story.get("headline", story.get("title", ""))[:70]
                source = story.get("source", "Unknown")
                sections_summary.append(f"  {i}. {headline}... ({source})")
            if len(stories) > 15:
                sections_summary.append(f"  ... and {len(stories) - 15} more")

    sections_text = "\n".join(sections_summary)

    # --- Step 2: Construct the Claude prompt ---
    # The prompt provides Claude with:
    # - The current newsletter state (sections_text)
    # - The user's natural language feedback
    # - A strict JSON schema for the expected response format
    # - Examples to guide Claude's output
    prompt = f"""You are helping edit a newsletter. Here are the current sections:

{sections_text}

The user's feedback is:
"{feedback}"

Based on this feedback, provide specific instructions in JSON format for how to modify the sections.
Return a JSON object with an "actions" array. Each action can be:
- {{"action": "move", "headline_contains": "partial headline text", "from_section": "section_name", "to_section": "section_name"}}
- {{"action": "remove", "headline_contains": "partial headline text", "from_section": "section_name"}}
- {{"action": "note", "message": "explanation if feedback can't be processed"}}

Valid sections: top_stories, politics, housing, education, health, environment, lastly

Example response:
{{"actions": [{{"action": "move", "headline_contains": "NJ Transit", "from_section": "top_stories", "to_section": "politics"}}]}}

Respond with JSON only, no explanation."""

    try:
        # --- Step 3: Call Claude API ---
        message = client.messages.create(
            model="claude-3-haiku-20240307",  # Fast, cost-effective model for simple parsing
            max_tokens=500,  # Actions are typically small JSON objects
            messages=[{"role": "user", "content": prompt}],
        )

        response_text = message.content[0].text.strip()

        # --- Step 4: Parse Claude's JSON response ---
        # Claude sometimes wraps JSON in markdown code blocks (```json ... ```),
        # so we strip those if present before parsing.
        if "```" in response_text:
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]  # Remove "json" language identifier
            response_text = response_text.strip()

        instructions = json.loads(response_text)

        # --- Step 5: Apply each action to the sections dict ---
        # We iterate through Claude's suggested actions and apply them one by one.
        # The sections dict is modified in-place.
        actions_taken = []
        for action in instructions.get("actions", []):
            action_type = action.get("action")

            # "note" actions are informational messages from Claude
            # (e.g., explaining why a request couldn't be fulfilled)
            if action_type == "note":
                print(f"    Note: {action.get('message', '')}")
                continue

            # Extract action parameters (case-insensitive headline matching)
            headline_contains = action.get("headline_contains", "").lower()
            from_section = action.get("from_section")
            to_section = action.get("to_section")

            if action_type == "move" and from_section and to_section:
                # MOVE action: Transfer story from one section to another
                # We iterate over a copy of the list ([:]) since we're modifying it
                for story in sections.get(from_section, [])[:]:
                    headline = story.get("headline", story.get("title", "")).lower()
                    # Partial match: check if the search term appears anywhere in headline
                    if headline_contains in headline:
                        sections[from_section].remove(story)
                        # Create target section if it doesn't exist
                        if to_section not in sections:
                            sections[to_section] = []
                        sections[to_section].append(story)
                        actions_taken.append(
                            f"Moved '{headline_contains}...' from {from_section} to {to_section}"
                        )
                        break  # Only move the FIRST matching story

            elif action_type == "remove" and from_section:
                # REMOVE action: Delete story from a section entirely
                for story in sections.get(from_section, [])[:]:
                    headline = story.get("headline", story.get("title", "")).lower()
                    if headline_contains in headline:
                        sections[from_section].remove(story)
                        actions_taken.append(
                            f"Removed '{headline_contains}...' from {from_section}"
                        )
                        break  # Only remove the FIRST matching story

        # --- Step 6: Report results to user ---
        if actions_taken:
            for action_msg in actions_taken:
                print(f"    ✓ {action_msg}")
        else:
            print("    No matching stories found for the requested changes.")

        return sections

    except Exception as e:
        # Graceful degradation: if anything fails (API error, JSON parse error,
        # network issue), we log the error and return sections unchanged.
        # This ensures the workflow can continue even if feedback processing fails.
        print(f"    Error processing feedback: {e}")
        return sections


def feedback_loop(
    sections: dict[str, list[dict]], all_stories: list[dict], preview_path: Path
) -> tuple[dict[str, list[dict]], str]:
    """
    Interactive feedback loop for refining the newsletter via natural language.

    This function provides a REPL-like interface where editors can iteratively
    refine the newsletter by providing natural language feedback. Each piece of
    feedback is processed by `process_feedback()`, which uses Claude AI to
    interpret and apply the requested changes.

    Args:
        sections: Dictionary mapping section names to lists of story dicts.
            This is modified in-place as feedback is processed.
        all_stories: All classified stories (passed to process_feedback for
            potential future use, e.g., adding stories back).
        preview_path: Path to the HTML preview file. Updated after each
            feedback round so editors can see changes.

    Returns:
        Tuple of (final sections dict, final HTML string).

    User Commands:
        - Any natural language text: Processed as feedback (move/remove stories)
        - 'done' or empty Enter: Exit the loop and finalize
        - 'refresh': Regenerate HTML and reopen browser preview

    Example Session:
        >>> feedback_loop(sections, stories, Path("drafts/dnr-2024-01-15.html"))
        Feedback (or 'done'): Move the Murphy story to top stories
            ✓ Moved 'murphy...' from politics to top_stories
            Preview updated. Refresh your browser or type 'refresh'.
        Feedback (or 'done'): Remove all lottery stories
            ✓ Removed 'powerball...' from lastly
            Preview updated. Refresh your browser or type 'refresh'.
        Feedback (or 'done'): done
    """
    print("\n  You can now provide feedback to refine the newsletter.")
    print("  Examples:")
    print("    - 'Move the NJ Transit story to politics'")
    print("    - 'Remove the carjacking story from top stories'")
    print("    - 'Move all crime stories out of top stories'")
    print("  Type 'done' when satisfied, 'refresh' to reload preview.\n")

    while True:
        feedback = input("  Feedback (or 'done'): ").strip()

        if feedback.lower() == "done" or feedback == "":
            break

        if feedback.lower() == "refresh":
            # Regenerate HTML and refresh browser
            html = build_newsletter(sections)
            with open(preview_path, "w", encoding="utf-8") as f:
                f.write(html)
            webbrowser.open(f"file://{preview_path.absolute()}")
            print("    Preview refreshed.")
            continue

        # Process the feedback
        print("    Processing feedback...")
        sections = process_feedback(sections, feedback, all_stories)

        # Regenerate HTML
        html = build_newsletter(sections)
        with open(preview_path, "w", encoding="utf-8") as f:
            f.write(html)

        print("    Preview updated. Refresh your browser or type 'refresh'.")

    # Final HTML
    html = build_newsletter(sections)
    return sections, html


def run_workflow(
    include_playwright: bool = False,
    enrich_stories: bool = False,
    hours_back: int = None,  # None = auto-detect based on day
):
    """
    Run the interactive DNR workflow.

    Args:
        include_playwright: Include Playwright sources
        enrich_stories: Enable URL enrichment
        hours_back: Hours to look back for stories (None = auto-detect)
    """
    print_header()

    # Check if today is a publish day
    is_publish_day, day_message = check_publish_day()
    print(f"  {day_message}")

    if not is_publish_day:
        print("\n  Warning: Today is not a normal DNR publish day.")
        if not prompt_yes_no("  Continue anyway?", default=False):
            print("\n  Workflow cancelled.")
            return

    # Calculate hours_back if not specified
    if hours_back is None:
        hours_back, hours_explanation = calculate_hours_back()
        print(f"\n  {hours_explanation}")
    else:
        print(f"\n  Custom hours: {hours_back} (override)")

    # Show configuration
    print("\nConfiguration:")
    print(f"  - Time range: last {hours_back} hours")
    print(f"  - Playwright sources: {'Yes' if include_playwright else 'No'}")
    print(f"  - URL enrichment: {'Yes' if enrich_stories else 'No'}")

    if not prompt_yes_no("\nReady to start?"):
        print("\nWorkflow cancelled.")
        return

    total_steps = 7

    # Step 1: Fetch stories
    print_step(1, total_steps, "Fetching stories from all sources")

    try:
        # Import optional modules
        if include_playwright and find_spec("playwright") is None:
            print("  Warning: Playwright not available")
            include_playwright = False

        if enrich_stories:
            try:
                from url_enricher import enrich_stories_batch

                enrichment_available = True
            except ImportError:
                print("  Warning: URL enrichment not available")
                enrichment_available = False
                enrich_stories = False

        stories = fetch_all_stories(
            hours_back=hours_back, include_playwright=include_playwright
        )

        if not stories:
            print("\nNo stories found! Check your RSS feeds and Airtable connection.")
            return

        print(f"\nTotal stories fetched: {len(stories)}")

    except Exception as e:
        print(f"\nError fetching stories: {e}")
        return

    # Step 2: Optional enrichment
    if enrich_stories and enrichment_available:
        print_step(2, total_steps, "Enriching stories with URL context")
        stories = enrich_stories_batch(stories, max_stories=20)
    else:
        print_step(2, total_steps, "Skipping URL enrichment")

    # Step 3: Classify stories
    print_step(3, total_steps, "Classifying stories into sections")

    try:
        classified = classify_all_stories(stories)
        unique = deduplicate_stories(classified)
        sections = organize_by_section(unique)

        # Show counts
        counts = count_stories(sections)
        print("\nStories by section:")
        total = 0
        section_emojis = {
            "top_stories": "📰",
            "politics": "🏛️",
            "housing": "🏘️",
            "education": "🏫",
            "health": "🦠",
            "environment": "🌳",
            "lastly": "☝️",
        }
        for section, count in counts.items():
            emoji = section_emojis.get(section, "•")
            print(f"  {emoji} {section}: {count}")
            total += count
        print(f"  Total: {total}")

    except Exception as e:
        print(f"\nError classifying stories: {e}")
        return

    # Step 4: Review Airtable submissions
    print_step(4, total_steps, "Review user-submitted stories")

    airtable_updates = review_airtable_submissions(unique)

    if airtable_updates:
        print(f"\n  {len(airtable_updates)} stories approved for Airtable update.")
        if prompt_yes_no("  Update Airtable now?"):
            print("  Updating Airtable...")
            results = update_submissions_batch(airtable_updates)
            print(f"  ✓ Updated {results['success']} records in Airtable")
            if results["failed"]:
                print(f"  ⚠ Failed to update {len(results['failed'])} records")
            print("  (Submitters will receive notification emails)")
        else:
            print("  Skipped Airtable update.")

    # Re-organize sections in case any were changed during review
    sections = organize_by_section(unique)

    # Step 5: Generate HTML
    print_step(5, total_steps, "Generating HTML preview")

    try:
        html = build_newsletter(sections)

        # Save preview
        output_dir = Path(__file__).parent.parent / "drafts"
        output_dir.mkdir(exist_ok=True)
        preview_path = output_dir / f"dnr-{datetime.now().strftime('%Y-%m-%d')}.html"

        with open(preview_path, "w", encoding="utf-8") as f:
            f.write(html)

        print(f"  Generated {len(html):,} characters")
        print(f"  Saved to: {preview_path}")

    except Exception as e:
        print(f"\nError generating HTML: {e}")
        return

    # Step 6: Review and refine
    print_step(6, total_steps, "Review and refine preview")

    print("\nOpening preview in your browser...")
    webbrowser.open(f"file://{preview_path.absolute()}")

    print("\nPlease review the newsletter in your browser.")
    print("Check for:")
    print("  - Story selection and placement")
    print("  - Headline accuracy")
    print("  - No duplicate stories across sections")
    print("  - Top stories don't appear in other sections")

    # Interactive feedback loop
    sections, html = feedback_loop(sections, unique, preview_path)

    # Step 7: Approval and publish
    print_step(7, total_steps, "Create Mailchimp draft")

    print("\nReady to create Mailchimp draft campaign?")
    print("This will create a DRAFT - you still need to review and send in Mailchimp.")

    if prompt_yes_no("\nCreate Mailchimp draft?"):
        print("\nCreating Mailchimp draft...")

        try:
            campaign_id = create_mailchimp_draft(html)

            if campaign_id:
                print("\n" + "=" * 60)
                print("  SUCCESS!")
                print("=" * 60)
                print(f"\n  Campaign ID: {campaign_id}")
                print("\n  Next steps:")
                print("  1. Open Mailchimp and find the draft")
                print("  2. Review the email preview")
                print("  3. Send a test email to yourself")
                print("  4. Schedule or send when ready")
            else:
                print("\nFailed to create Mailchimp draft. Check the error above.")

        except Exception as e:
            print(f"\nError creating Mailchimp draft: {e}")
    else:
        print("\nMailchimp draft NOT created.")
        print(f"HTML preview saved at: {preview_path}")
        print("\nYou can manually copy/paste the HTML into Mailchimp later.")

    print("\n" + "=" * 60)
    print("  WORKFLOW COMPLETE")
    print("=" * 60)
    print()


def main():
    parser = argparse.ArgumentParser(description="Interactive DNR Workflow")
    parser.add_argument(
        "--playwright",
        action="store_true",
        help="Include Playwright sources (paywalled sites)",
    )
    parser.add_argument(
        "--enrich", action="store_true", help="Enable URL enrichment with Gemini"
    )
    parser.add_argument(
        "--hours",
        type=int,
        default=None,
        help="Hours back to look for stories (default: auto-detect based on day)",
    )

    args = parser.parse_args()

    try:
        run_workflow(
            include_playwright=args.playwright,
            enrich_stories=args.enrich,
            hours_back=args.hours,  # None = auto-detect
        )
    except KeyboardInterrupt:
        print("\n\nWorkflow cancelled by user.")
        sys.exit(0)


if __name__ == "__main__":
    main()
