"""Boardwalk story export and import push."""

import json
import urllib.error
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path

from build_around_nj_demo import (
    boardwalk_record,
    combine_duplicate,
    feed_summary,
    fetch_feed,
    plain_text,
)
from push_around_nj_boardwalk import main as push_main
from push_around_nj_boardwalk import push_stories
from push_around_nj_boardwalk import run_id_for


def test_plain_text_strips_markup_and_trims():
    assert plain_text("<p>Hello&nbsp;there</p>", 280) == "Hello there"
    assert plain_text("x" * 300, 280) is not None
    assert len(plain_text("x" * 300, 280)) == 280
    assert plain_text("  ", 20) is None


def test_feed_keeps_description_and_author(monkeypatch):
    published = (datetime.now(timezone.utc) - timedelta(hours=2)).strftime(
        "%a, %d %b %Y %H:%M:%S GMT"
    )
    rss = (
        '<?xml version="1.0"?><rss version="2.0"><channel><title>x</title>'
        "<item><title>Hello</title><link>https://villagegreennj.com/story</link>"
        "<author>Pat Lee</author>"
        "<description>&lt;p&gt;A short desk summary.&lt;/p&gt;</description>"
        f"<pubDate>{published}</pubDate></item></channel></rss>"
    ).encode()
    monkeypatch.setattr(
        "build_around_nj_demo.fetch_url_bytes", lambda url, **kwargs: (200, rss)
    )
    item = fetch_feed("https://villagegreennj.com/feed/", "Village Green", True)["items"][0]
    assert item["byline"] == "Pat Lee"
    assert item["summary"] == "A short desk summary."
    assert feed_summary({"summary": "<b>Kept</b>"}) == "Kept"


def test_boardwalk_record_skips_a_nondefault_port():
    assert boardwalk_record({
        "title": "Hello",
        "url": "https://example.com:8443/story",
        "when": "2026-09-25T14:00:00+00:00",
        "source": "Example",
        "partner": False,
    }) is None


def test_duplicate_keeps_summary_from_the_other_copy():
    current = {
        "title": "Same story",
        "url": "https://example.com/a",
        "when": "2026-09-18T16:00:00+00:00",
        "source": "NJ.com",
        "partner": False,
        "summary": "The feed description.",
    }
    story = {
        "title": "Same story",
        "url": "https://example.com/a",
        "when": "2026-09-18T15:00:00+00:00",
        "source": "NJ Monitor",
        "partner": True,
    }
    merged = combine_duplicate(current, story)
    assert merged["summary"] == "The feed description."
    record = boardwalk_record(merged)
    assert record["canonicalUrl"] == "https://example.com/a"
    assert record["summary"] == "The feed description."
    assert record["partner"] is True


def test_push_skips_when_the_token_is_absent(tmp_path, monkeypatch, capsys):
    path = tmp_path / "stories.json"
    path.write_text(json.dumps({"generatedAt": "2026-09-25T15:00:00+00:00", "stories": []}), encoding="utf-8")
    monkeypatch.delenv("AROUND_NJ_IMPORT_TOKEN", raising=False)
    assert push_main(["--stories", str(path)]) == 0
    assert "not set" in capsys.readouterr().err


def test_push_batches_and_retries_a_full_batch(monkeypatch):
    calls = []

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self, _limit):
            return b'{"upserted":40}'

    def opener(request, timeout):
        calls.append((request.full_url, request.data, timeout))
        if len(calls) == 1:
            raise urllib.error.HTTPError(request.full_url, 429, "busy", hdrs=None, fp=BytesIO(b"later"))
        return Response()

    stories = [
        {
            "url": f"https://example.com/{index}",
            "canonicalUrl": f"https://example.com/{index}",
            "headline": f"Story {index}",
            "outlet": "Example",
            "partner": True,
            "publishedAt": "2026-09-25T14:00:00+00:00",
        }
        for index in range(41)
    ]
    sleeps = []
    assert push_stories(
        "https://cms.test/cmsImportAroundNj",
        "a" * 48,
        {"generatedAt": "2026-09-25T15:00:00+00:00", "stories": stories},
        opener=opener,
        sleep=sleeps.append,
    ) == 0
    assert sleeps == [1]
    bodies = [json.loads(data) for _url, data, _timeout in calls]
    assert [len(body["stories"]) for body in bodies] == [40, 40, 1]
    assert bodies[0]["runId"] == run_id_for("2026-09-25T15:00:00+00:00")
    assert all(body["runId"] == bodies[0]["runId"] for body in bodies)


def test_push_redacts_the_token_from_an_error(capsys):
    token = "b" * 48

    def opener(request, timeout):
        raise urllib.error.HTTPError(
            request.full_url,
            401,
            "no",
            hdrs=None,
            fp=BytesIO(f"rejected {token}".encode()),
        )

    status = push_stories(
        "https://cms.test/cmsImportAroundNj",
        token,
        {
            "generatedAt": "2026-09-25T15:00:00+00:00",
            "stories": [{
                "url": "https://example.com/a",
                "canonicalUrl": "https://example.com/a",
                "headline": "Hello",
                "outlet": "Example",
                "partner": True,
                "publishedAt": "2026-09-25T14:00:00+00:00",
            }],
        },
        opener=opener,
        sleep=lambda _seconds: None,
    )
    assert status == 1
    error = capsys.readouterr().err
    assert token not in error
    assert "[redacted]" in error


def test_refresh_script_reads_pass_without_printing_it():
    script = (Path(__file__).parents[1] / "scripts" / "run_around_nj_refresh.sh").read_text(encoding="utf-8")
    assert "njpbs/boardwalk/around-nj-import" in script
    assert "--stories-json" in script
    assert 'echo "$token"' not in script
    assert "echo $token" not in script
