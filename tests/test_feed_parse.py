"""Reject non-feed HTTP 200 bodies."""

from build_around_nj_demo import fetch_feed


def test_html_page_is_not_a_feed(monkeypatch):
    monkeypatch.setattr(
        "build_around_nj_demo.fetch_url_bytes",
        lambda url: (200, b"<html><title>Maintenance</title></html>"),
    )
    result = fetch_feed("https://example.com/feed", "Example")
    assert result["ok"] is False
    assert result["error"] == "not a feed"


def test_empty_body_is_not_a_feed(monkeypatch):
    monkeypatch.setattr(
        "build_around_nj_demo.fetch_url_bytes",
        lambda url: (200, b""),
    )
    result = fetch_feed("https://example.com/feed", "Example")
    assert result["ok"] is False
    assert result["error"] == "not a feed"
