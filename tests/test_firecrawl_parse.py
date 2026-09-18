"""Parse Firecrawl JSON payloads into story records."""

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
