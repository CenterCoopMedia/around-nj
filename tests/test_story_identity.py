"""Story link validation, URL dedupe, and partner matching."""

from build_around_nj_demo import canonical_url, is_partner, valid_story_link


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
