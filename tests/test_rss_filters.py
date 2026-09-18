"""Offline filters used before classification."""

from rss_fetcher import is_generic_broadcast, transform_url


def test_generic_broadcast_headlines_are_skipped():
    assert is_generic_broadcast("WHYY Newscast for Tuesday, 11:00 a.m.")
    assert is_generic_broadcast("NJ Spotlight News: December 15, 2025")
    assert is_generic_broadcast("This week on NJTV")


def test_policy_headlines_are_not_skipped():
    assert not is_generic_broadcast("Murphy signs affordable housing bill")
    assert not is_generic_broadcast("NJ Transit delays after overhead wire failure")


def test_nj_dot_com_urls_get_amp_output_type():
    assert (
        transform_url("https://www.nj.com/politics/2026/09/story.html", "NJ.com")
        == "https://www.nj.com/politics/2026/09/story.html?outputType=amp"
    )
    assert (
        transform_url("https://www.nj.com/politics/2026/09/story.html?foo=1", "NJ.com")
        == "https://www.nj.com/politics/2026/09/story.html?foo=1&outputType=amp"
    )


def test_non_nj_dot_com_urls_are_unchanged():
    url = "https://newjerseymonitor.com/2026/09/18/story/"
    assert transform_url(url, "NJ Monitor") == url
