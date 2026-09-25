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
from push_around_nj_boardwalk import story_batches


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
    item = fetch_feed("https://villagegreennj.com/feed/", "Village Green", True)[
        "items"
    ][0]
    assert item["byline"] == "Pat Lee"
    assert item["summary"] == "A short desk summary."
    assert feed_summary({"summary": "<b>Kept</b>"}) == "Kept"


def story_row(url):
    return {
        "title": "Hello",
        "url": url,
        "when": "2026-09-25T14:00:00+00:00",
        "source": "Example",
        "partner": False,
    }


def test_boardwalk_record_skips_a_nondefault_port():
    assert boardwalk_record(story_row("https://example.com:8443/story")) is None
    assert boardwalk_record(story_row("https://exa mple.com/story")) is None
    assert boardwalk_record(story_row("https://[::ffff:192.0.2.1]/story")) is None
    assert boardwalk_record(story_row("https://example.com:abc/story")) is None
    assert boardwalk_record(story_row("https://example.com:80/story")) is None
    assert boardwalk_record(story_row("http://example.com:443/story")) is None
    assert boardwalk_record(story_row("https://example.com/" + "a" * 2000)) is None
    kept = boardwalk_record(story_row("https://example.com:443/story"))
    assert kept["canonicalUrl"] == "https://example.com/story"


def test_duplicate_keeps_a_valid_url_when_the_newer_copy_cannot_be_exported():
    current = {
        "title": "Same story",
        "url": "https://example.com/a",
        "when": "2026-09-18T15:00:00+00:00",
        "source": "Example",
        "partner": True,
    }
    newer = {
        "title": "Same story",
        "url": "https://example.com/a?utm_source=" + ("x" * 2000),
        "when": "2026-09-18T16:00:00+00:00",
        "source": "Example",
        "partner": True,
    }
    merged = combine_duplicate(current, newer)
    assert merged["url"] == "https://example.com/a"
    assert merged["when"] == "2026-09-18T16:00:00+00:00"
    assert boardwalk_record(merged)["canonicalUrl"] == "https://example.com/a"


def test_duplicate_does_not_keep_metadata_from_a_rejected_port():
    current = {
        "title": "Real headline",
        "url": "https://example.com/a",
        "when": "2026-09-18T15:00:00+00:00",
        "source": "Example",
        "partner": False,
    }
    newer = {
        "title": "Other origin",
        "url": "https://example.com:8443/a",
        "when": "2026-09-18T16:00:00+00:00",
        "source": "Elsewhere",
        "partner": True,
    }
    merged = combine_duplicate(current, newer)
    assert merged == current
    assert boardwalk_record(merged)["canonicalUrl"] == "https://example.com/a"


def test_duplicate_ignores_an_older_rejected_port():
    older = {
        "title": "Other origin",
        "url": "https://example.com:8443/a",
        "when": "2026-09-18T15:00:00+00:00",
        "source": "Elsewhere",
        "partner": True,
        "summary": "Do not keep",
    }
    newer = {
        "title": "Real headline",
        "url": "https://example.com/a",
        "when": "2026-09-18T16:00:00+00:00",
        "source": "Example",
        "partner": False,
    }
    merged = combine_duplicate(older, newer)
    assert merged["url"] == "https://example.com/a"
    assert merged["title"] == "Real headline"
    assert merged["source"] == "Example"
    assert merged["partner"] is False
    assert "summary" not in merged


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
    path.write_text(
        json.dumps({"generatedAt": "2026-09-25T15:00:00+00:00", "stories": []}),
        encoding="utf-8",
    )
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
            raise urllib.error.HTTPError(
                request.full_url, 429, "busy", hdrs=None, fp=BytesIO(b"later")
            )
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
    assert (
        push_stories(
            "https://cms.test/cmsImportAroundNj",
            "a" * 48,
            {"generatedAt": "2026-09-25T15:00:00+00:00", "stories": stories},
            opener=opener,
            sleep=sleeps.append,
        )
        == 0
    )
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
            "stories": [
                {
                    "url": "https://example.com/a",
                    "canonicalUrl": "https://example.com/a",
                    "headline": "Hello",
                    "outlet": "Example",
                    "partner": True,
                    "publishedAt": "2026-09-25T14:00:00+00:00",
                }
            ],
        },
        opener=opener,
        sleep=lambda _seconds: None,
    )
    assert status == 1
    error = capsys.readouterr().err
    assert token not in error
    assert "[redacted]" in error


def test_push_fails_when_a_configured_token_is_only_spaces(
    tmp_path, monkeypatch, capsys
):
    path = tmp_path / "stories.json"
    path.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("AROUND_NJ_IMPORT_TOKEN", "   ")
    assert push_main(["--stories", str(path)]) == 1
    assert "not 48" in capsys.readouterr().err


def test_push_fails_when_the_export_or_token_is_unusable(tmp_path, monkeypatch, capsys):
    path = tmp_path / "stories.json"
    path.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("AROUND_NJ_IMPORT_TOKEN", "not-a-token")
    assert push_main(["--stories", str(path)]) == 1
    assert "not 48" in capsys.readouterr().err
    monkeypatch.setenv("AROUND_NJ_IMPORT_TOKEN", "c" * 48)
    path.write_text(
        json.dumps({"generatedAt": "2026-09-25T15:00:00+00:00", "stories": []}),
        encoding="utf-8",
    )
    assert push_main(["--stories", str(path)]) == 1
    assert "empty" in capsys.readouterr().err
    path.write_text("{", encoding="utf-8")
    assert push_main(["--stories", str(path)]) == 1


def test_push_splits_batches_that_would_exceed_64_kib():
    stories = []
    for index in range(20):
        url = f"https://example.com/{index}/" + ("a" * 1700)
        stories.append(
            {
                "url": url,
                "canonicalUrl": url,
                "headline": f"Story {index}",
                "outlet": "Example",
                "partner": True,
                "publishedAt": "2026-09-25T14:00:00+00:00",
            }
        )
    generated_at = "2026-09-25T15:00:00+00:00"
    batches = story_batches(stories, run_id_for(generated_at), generated_at)
    assert batches is not None
    assert len(batches) > 1
    assert sum(len(batch) for batch in batches) == 20
    for batch in batches:
        body = {
            "runId": run_id_for(generated_at),
            "generatedAt": generated_at,
            "stories": batch,
        }
        assert len(json.dumps(body).encode("utf-8")) <= 64 * 1024


def test_push_retries_when_the_error_body_cannot_be_read():
    calls = {"count": 0}

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self, _limit):
            return b'{"upserted":1}'

    def opener(request, timeout):
        calls["count"] += 1
        if calls["count"] == 1:
            error = urllib.error.HTTPError(
                request.full_url, 503, "down", hdrs=None, fp=BytesIO(b"later")
            )

            def fail_read(_limit):
                raise ConnectionResetError("reset")

            error.read = fail_read
            raise error
        return Response()

    assert (
        push_stories(
            "https://cms.test/cmsImportAroundNj",
            "a" * 48,
            {
                "generatedAt": "2026-09-25T15:00:00+00:00",
                "stories": [
                    {
                        "url": "https://example.com/a",
                        "canonicalUrl": "https://example.com/a",
                        "headline": "Hello",
                        "outlet": "Example",
                        "partner": True,
                        "publishedAt": "2026-09-25T14:00:00+00:00",
                    }
                ],
            },
            opener=opener,
            sleep=lambda _seconds: None,
        )
        == 0
    )
    assert calls["count"] == 2


def test_push_rejects_a_null_required_field_before_posting():
    def opener(_request, _timeout):
        raise AssertionError("posted")

    story = {
        "url": None,
        "canonicalUrl": "https://example.com/a",
        "headline": "Hello",
        "outlet": "Example",
        "partner": True,
        "publishedAt": "2026-09-25T14:00:00+00:00",
    }
    assert (
        push_stories(
            "https://cms.test/cmsImportAroundNj",
            "a" * 48,
            {"generatedAt": "2026-09-25T15:00:00+00:00", "stories": [story]},
            opener=opener,
            sleep=lambda _seconds: None,
        )
        == 1
    )


def test_push_retries_a_dropped_connection():
    calls = {"count": 0}

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self, _limit):
            return b'{"upserted":1}'

    def opener(request, timeout):
        calls["count"] += 1
        if calls["count"] == 1:
            raise urllib.error.URLError("connection reset")
        return Response()

    sleeps = []
    assert (
        push_stories(
            "https://cms.test/cmsImportAroundNj",
            "a" * 48,
            {
                "generatedAt": "2026-09-25T15:00:00+00:00",
                "stories": [
                    {
                        "url": "https://example.com/a",
                        "canonicalUrl": "https://example.com/a",
                        "headline": "Hello",
                        "outlet": "Example",
                        "partner": True,
                        "publishedAt": "2026-09-25T14:00:00+00:00",
                    }
                ],
            },
            opener=opener,
            sleep=sleeps.append,
        )
        == 0
    )
    assert calls["count"] == 2
    assert sleeps == [1]


def test_push_refuses_one_story_over_the_byte_limit():
    def opener(_request, _timeout):
        raise AssertionError("posted")

    story = {
        "url": "https://example.com/a",
        "canonicalUrl": "https://example.com/a",
        "headline": "Hello",
        "outlet": "Example",
        "partner": True,
        "publishedAt": "2026-09-25T14:00:00+00:00",
        "note": "x" * 70000,
    }
    assert (
        push_stories(
            "https://cms.test/cmsImportAroundNj",
            "a" * 48,
            {"generatedAt": "2026-09-25T15:00:00+00:00", "stories": [story]},
            opener=opener,
            sleep=lambda _seconds: None,
        )
        == 1
    )


def test_push_refuses_a_run_with_more_than_40_batches():
    stories = []
    for index in range(41):
        stories.append(
            {
                "url": f"https://example.com/{index}",
                "canonicalUrl": f"https://example.com/{index}",
                "headline": f"Story {index}",
                "outlet": "Example",
                "partner": True,
                "publishedAt": "2026-09-25T14:00:00+00:00",
                "pad": "x" * 60000,
            }
        )

    def opener(_request, _timeout):
        raise AssertionError("posted")

    assert (
        push_stories(
            "https://cms.test/cmsImportAroundNj",
            "a" * 48,
            {"generatedAt": "2026-09-25T15:00:00+00:00", "stories": stories},
            opener=opener,
            sleep=lambda _seconds: None,
        )
        == 1
    )


def test_refresh_script_reads_pass_without_printing_it():
    script = (
        Path(__file__).parents[1] / "scripts" / "run_around_nj_refresh.sh"
    ).read_text(encoding="utf-8")
    assert "njpbs/boardwalk/around-nj-import" in script
    assert "--stories-json" in script
    assert 'echo "$token"' not in script
    assert "echo $token" not in script
