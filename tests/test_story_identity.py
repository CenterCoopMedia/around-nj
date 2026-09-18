"""Story link validation, URL dedupe, and partner matching."""

from build_around_nj_demo import (
    canonical_url,
    combine_duplicate,
    fetch_feed,
    is_partner,
    valid_story_link,
)


def test_valid_story_link_rejects_junk():
    assert valid_story_link("https://villagegreennj.com/story/")
    assert valid_story_link("http://foo") is None
    assert valid_story_link("http://localhost/x") is None
    assert valid_story_link("https://user:pass@example.com/x") is None
    assert valid_story_link("http://[") is None


def test_canonical_url_collapses_duplicates():
    assert canonical_url("http://www.VillageGreenNJ.com/story/") == canonical_url(
        "https://villagegreennj.com/story"
    )


def test_canonical_url_keeps_identity_query_and_drops_tracking():
    assert canonical_url("https://youtube.com/watch?v=first") != canonical_url(
        "https://youtube.com/watch?v=second"
    )
    assert canonical_url(
        "https://example.com/story?utm_source=x&id=1"
    ) == canonical_url("https://example.com/story?id=1")


def test_relative_rss_link_is_resolved(monkeypatch):
    rss = (
        b'<?xml version="1.0"?><rss version="2.0"><channel><title>x</title>'
        b"<item><title>Hello</title><link>/story</link>"
        b"<pubDate>Fri, 18 Sep 2026 12:00:00 GMT</pubDate></item></channel></rss>"
    )
    monkeypatch.setattr(
        "build_around_nj_demo.fetch_url_bytes", lambda url, **kwargs: (200, rss)
    )
    result = fetch_feed("https://villagegreennj.com/feed/", "Village Green", True)
    assert result["ok"] is True
    assert result["items"][0]["url"] == "https://villagegreennj.com/story"


def test_duplicate_keeps_partner_source():
    current = {
        "title": "Same story",
        "url": "https://example.com/a",
        "when": "2026-09-18T16:00:00+00:00",
        "source": "NJ.com",
        "partner": False,
    }
    story = {
        "title": "Same story",
        "url": "https://example.com/a",
        "when": "2026-09-18T15:00:00+00:00",
        "source": "NJ Monitor",
        "partner": True,
    }
    merged = combine_duplicate(current, story)
    assert merged["partner"] is True
    assert merged["source"] == "NJ Monitor"


def test_partner_match_uses_normalized_source_not_url():
    names = {"Montclair Local", "Village Green"}
    assert is_partner(
        {"source": "Montclair Local", "url": "https://other.com/x"}, names
    )
    assert is_partner(
        {"source": "The Village Green", "url": "https://example.com/x"}, names
    )
    assert not is_partner(
        {"source": "Baristanet", "url": "https://montclairlocal.news/story"}, names
    )
