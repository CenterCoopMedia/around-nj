"""Airtable fetcher for reader/publisher story submissions."""

import os
from datetime import datetime, timedelta
from typing import Optional

from dotenv import load_dotenv
from pyairtable import Api
from pyairtable.formulas import match

load_dotenv()


def get_airtable_table():
    """Get the Airtable table object."""
    api = Api(os.getenv("AIRTABLE_PAT"))
    return api.table(os.getenv("AIRTABLE_BASE_ID"), os.getenv("AIRTABLE_TABLE_ID"))


def fetch_submissions(
    days_back: int = 7,
    section_filter: Optional[str] = None,
    include_unassigned: bool = True,
) -> list[dict]:
    """
    Fetch story submissions from Airtable.

    Args:
        days_back: How many days back to look for submissions
        section_filter: Only fetch submissions assigned to this section
        include_unassigned: Include submissions without a section assigned

    Returns:
        List of submission dicts with headline, url, source, section, etc.
    """
    table = get_airtable_table()

    # Calculate cutoff date
    cutoff = datetime.now() - timedelta(days=days_back)

    # Build formula for filtering
    # Note: Airtable date filtering can be tricky; we'll filter in Python too
    formula = None
    if section_filter:
        formula = match({"Section": section_filter})

    try:
        records = table.all(formula=formula)
    except Exception as e:
        print(f"Error fetching from Airtable: {e}")
        return []

    submissions = []
    for record in records:
        fields = record.get("fields", {})

        # Parse the date
        date_added = fields.get("Date added")
        if date_added:
            try:
                # Airtable dates come in ISO format
                record_date = datetime.fromisoformat(date_added.replace("Z", "+00:00"))
                if record_date.replace(tzinfo=None) < cutoff:
                    continue
            except Exception:
                pass

        # Skip if no section and we're not including unassigned
        section = fields.get("Section")
        if not include_unassigned and not section:
            continue

        submission = {
            "id": record.get("id"),
            "headline": fields.get("Headline", "").strip(),
            "url": fields.get("URL", "").strip(),
            "source": fields.get("Source", "").strip(),
            "section": section,
            "summary": fields.get("Summary", ""),
            "submitter_name": fields.get("Name", ""),
            "submitter_email": fields.get("Email", ""),
            "date_added": date_added,
            "from_airtable": True,
        }

        # Only include if we have headline and URL
        if submission["headline"] and submission["url"]:
            submissions.append(submission)

    return submissions


def fetch_unprocessed_submissions() -> list[dict]:
    """
    Fetch submissions that haven't been processed yet.
    You may want to add a 'Processed' checkbox field to Airtable.
    """
    table = get_airtable_table()

    # If you add a 'Processed' field, use this formula:
    # formula = match({"Processed": False})

    records = table.all()
    return [
        {
            "id": r.get("id"),
            "headline": r["fields"].get("Headline", ""),
            "url": r["fields"].get("URL", ""),
            "source": r["fields"].get("Source", ""),
            "section": r["fields"].get("Section"),
            "summary": r["fields"].get("Summary", ""),
            "date_added": r["fields"].get("Date added"),
            "from_airtable": True,
        }
        for r in records
        if r["fields"].get("Headline") and r["fields"].get("URL")
    ]


def mark_as_processed(record_ids: list[str]) -> None:
    """
    Mark submissions as processed (requires 'Processed' field in Airtable).

    Args:
        record_ids: List of Airtable record IDs to mark
    """
    table = get_airtable_table()
    for record_id in record_ids:
        try:
            table.update(record_id, {"Processed": True})
        except Exception as e:
            print(f"Error marking {record_id} as processed: {e}")


def update_submission(record_id: str, source: str = None, section: str = None) -> bool:
    """
    Update a submission's source and/or section in Airtable.

    This triggers the automation that notifies submitters their story was approved.

    Args:
        record_id: Airtable record ID
        source: Source name to set (optional)
        section: Newsletter section name (will be converted to Airtable format)

    Returns:
        True if successful, False otherwise
    """
    table = get_airtable_table()

    updates = {}
    if source:
        updates["Source"] = source
    if section:
        # Convert newsletter section name to Airtable section name
        airtable_section = NEWSLETTER_TO_AIRTABLE.get(section, section)
        updates["Section"] = airtable_section

    if not updates:
        return True  # Nothing to update

    try:
        table.update(record_id, updates)
        return True
    except Exception as e:
        print(f"Error updating {record_id}: {e}")
        return False


def update_submissions_batch(updates: list[dict]) -> dict:
    """
    Update multiple submissions in Airtable.

    Args:
        updates: List of dicts with 'id', 'source', and 'section' keys

    Returns:
        Dict with 'success' count and 'failed' list
    """
    results = {"success": 0, "failed": []}

    for update in updates:
        record_id = update.get("id")
        if not record_id:
            continue

        success = update_submission(
            record_id=record_id,
            source=update.get("source"),
            section=update.get("section"),
        )

        if success:
            results["success"] += 1
        else:
            results["failed"].append(record_id)

    return results


def get_submissions_by_section() -> dict[str, list[dict]]:
    """
    Fetch all recent submissions grouped by section.

    Returns:
        Dict mapping section names to lists of submissions
    """
    submissions = fetch_submissions(days_back=7)

    # Section names as they appear in Airtable
    by_section = {
        "Top stories": [],
        "Politics + government": [],
        "Housing + development": [],
        "Work + education": [],
        "Health + safety": [],
        "Climate + environment": [],
        "Lastly": [],
        "Unassigned": [],
    }

    for sub in submissions:
        section = sub.get("section")
        if section and section in by_section:
            by_section[section].append(sub)
        else:
            by_section["Unassigned"].append(sub)

    return by_section


# Map Airtable section names to newsletter section names
SECTION_MAP = {
    "Top stories": "top_stories",
    "Politics + government": "politics",
    "Housing + development": "housing",
    "Work + education": "education",
    "Health + safety": "health",
    "Climate + environment": "environment",
    "Lastly": "lastly",
}

# Reverse map
NEWSLETTER_TO_AIRTABLE = {v: k for k, v in SECTION_MAP.items()}


if __name__ == "__main__":
    import sys

    # Fix Windows console encoding
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    print("=" * 60)
    print("AIRTABLE SUBMISSIONS TEST")
    print("=" * 60)

    submissions = fetch_submissions(days_back=30)
    print(f"\nFound {len(submissions)} submissions in the last 30 days\n")

    by_section = get_submissions_by_section()
    for section, subs in by_section.items():
        if subs:
            print(f"\n{section}: {len(subs)} submissions")
            for s in subs[:3]:  # Show first 3
                print(f"  - {s['headline'][:50]}... ({s['source']})")
