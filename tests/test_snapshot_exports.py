"""Offline export contracts; fixtures are synthetic and never published."""

from datetime import datetime, timezone
import json
from xml.etree import ElementTree as ET

import feedparser

from build_around_nj_demo import canonical_url, combine_duplicate
from snapshot_exports import make_snapshot, render_markdown, render_rss, write_exports

NOW = datetime(2026, 10, 10, tzinfo=timezone.utc)


def row(**kwargs):
    return {
        "title": "A <script> & [link](evil)\x00",
        "url": "https://example.com/story?a=1&b=2",
        "source": "Example & newsroom",
        "partner": True,
        "when": "2026-10-09T12:00:00-04:00",
        **kwargs,
    }


def snapshot(rows):
    return make_snapshot(
        rows,
        generated_at=NOW,
        lookback_hours=72,
        canonicalize=canonical_url,
        coverage={"rss_feeds_failed": 1},
    )


def test_roundtrip_exports_and_escaping(tmp_path):
    data = snapshot([row()])
    write_exports(tmp_path, data)
    assert json.loads((tmp_path / "snapshot.json").read_text()) == data
    rss = (tmp_path / "rss.xml").read_text()
    root = ET.fromstring(rss)
    assert root.findtext("channel/item/title") == row()["title"].replace("\x00", "")
    assert root.findtext("channel/item/link") == row()["url"]
    assert root.findtext("channel/item/guid") == data["items"][0]["id"]
    parsed = feedparser.parse(rss)
    assert not parsed.bozo
    assert parsed.entries[0].published_parsed[:6] == (2026, 10, 9, 16, 0, 0)
    md = (tmp_path / "snapshot.md").read_text()
    assert "<script>" not in md
    assert "\\[link\\]" in md
    assert "Example &amp; newsroom" in md
    assert data["items"][0]["date"] == "2026-10-09T16:00:00Z"


def test_deterministic_order_stable_ids_and_no_cap():
    rows = [row(url=f"https://example.com/{i}") for i in range(200)]
    a = snapshot(rows)
    b = snapshot(list(reversed(rows)))
    assert a == b
    assert render_rss(a) == render_rss(b)
    assert render_markdown(a) == render_markdown(b)
    assert a["item_count"] == 200
    assert (
        snapshot([row(url="https://example.com/story?utm_source=x")])["items"][0]["id"]
        == snapshot([row(url="http://www.example.com/story/")])["items"][0]["id"]
    )


def test_observed_and_updated_dates_are_not_publication_dates():
    for kind in ("observed", "updated"):
        data = snapshot([row(date_kind=kind)])
        root = ET.fromstring(render_rss(data))
        assert root.find("channel/item/pubDate") is None
        assert data["items"][0]["date_kind"] == kind
        assert f"Date ({kind})" in render_markdown(data)


def test_empty_snapshot_is_valid():
    data = snapshot([])
    assert data["item_count"] == 0
    assert ET.fromstring(render_rss(data)).find("channel/item") is None


def test_equal_date_duplicate_choice_is_order_independent():
    a, b = row(title="A"), row(title="B")
    assert combine_duplicate(a, b) == combine_duplicate(b, a)


def test_builder_writes_matching_bundle_offline(tmp_path, monkeypatch):
    import build_around_nj_demo as builder
    from pathlib import Path

    (tmp_path / "config").mkdir()
    (tmp_path / "scripts").mkdir()
    (tmp_path / "config/rss_feeds.json").write_text(
        json.dumps(
            {
                "feeds": {
                    "test": [
                        {
                            "name": "Fixture newsroom",
                            "rss_url": "https://example.com/feed",
                        }
                    ]
                }
            }
        )
    )
    (tmp_path / "config/pbs_partners.json").write_text("[]")
    template = Path(builder.__file__).with_name("around_nj_template.html").read_text()
    (tmp_path / "scripts/around_nj_template.html").write_text(template)
    now = datetime.now(timezone.utc).isoformat()
    monkeypatch.setattr(builder, "ROOT", tmp_path)
    monkeypatch.setattr(
        builder,
        "fetch_feed_bounded",
        lambda url, name, partner: {
            "url": url,
            "ok": True,
            "items": [row(title="Fixture headline", when=now)],
        },
    )
    scrape = tmp_path / "scraped.json"
    scrape.write_text(
        json.dumps(
            {
                "generated_at": now,
                "results": [
                    {
                        "org": "Fixture partner",
                        "ok": True,
                        "url": "https://partner.example/",
                        "stories": [
                            {
                                "title": "Undated fixture",
                                "url": "https://partner.example/a",
                            }
                        ],
                    }
                ],
            }
        )
    )
    out = tmp_path / "output/snapshot.html"
    monkeypatch.setattr(
        "sys.argv", ["builder", "--output", str(out), "--scraped-json", str(scrape)]
    )
    builder.main()
    data = json.loads(out.with_suffix(".json").read_text())
    assert data["item_count"] == 2
    assert {x["date_kind"] for x in data["items"]} == {"published", "observed"}
    assert "Fixture headline" in out.read_text()
    assert "Undated fixture" in out.read_text()
    assert not feedparser.parse((out.parent / "rss.xml").read_bytes()).bozo


def test_subsecond_order_is_chronological():
    data = snapshot(
        [
            row(url="https://example.com/older", when="2026-10-09T12:00:00Z"),
            row(url="https://example.com/newer", when="2026-10-09T12:00:00.500000Z"),
        ]
    )
    assert data["items"][0]["url"].endswith("/newer")


def test_invalid_url_characters_rejected():
    import pytest
    from build_around_nj_demo import valid_story_link

    for char in ("\x00", "\n", " ", "\ud800", "\ufffe"):
        url = "https://example.com/a" + char
        assert valid_story_link(url) is None
        with pytest.raises(ValueError):
            snapshot([row(url=url)])


def test_timestamp_provenance_matches_selected_field():
    from build_around_nj_demo import parse_when_with_kind

    atom = """<feed xmlns="http://www.w3.org/2005/Atom"><entry>
      <title>Fixture</title><published>2026-282</published>
      <updated>2026-10-10T00:00:00Z</updated></entry></feed>"""
    entry = feedparser.parse(atom).entries[0]
    timestamp, kind = parse_when_with_kind(entry)
    assert timestamp == NOW
    assert kind == "updated"
