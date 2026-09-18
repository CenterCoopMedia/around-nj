"""Parse Firecrawl JSON payloads into story records."""

from datetime import datetime, timezone

from build_around_nj_demo import parse_published_text
from scrape_partner_homepages import parse_firecrawl_payload


def test_parse_nested_json_stories():
    payload = {
        "json": {
            "stories": [
                {
                    "title": "  Local board votes  ",
                    "url": "https://njbmagazine.com/story/",
                    "published": "2026-09-18",
                },
                {"title": "Skip me", "url": "javascript:alert(1)"},
            ]
        }
    }
    stories = parse_firecrawl_payload(payload)
    assert len(stories) == 1
    assert stories[0]["title"] == "Local board votes"
    assert stories[0]["url"] == "https://njbmagazine.com/story/"


def test_parse_published_text_accepts_iso_and_human_dates():
    iso = parse_published_text("2026-09-18T10:00:00Z")
    assert iso is not None
    assert iso == datetime(2026, 9, 18, 10, 0, tzinfo=timezone.utc)
    day = parse_published_text("September 18, 2026")
    assert day is not None
    assert day.date() == datetime(2026, 9, 18).date()
    assert parse_published_text("not a date") is None
