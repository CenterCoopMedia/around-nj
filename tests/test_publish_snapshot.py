"""Publish script must target gh-pages and fast-forward before push."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "publish_around_nj_snapshot.sh"


def _run(cmd, cwd=None, check=True, env=None):
    return subprocess.run(
        cmd,
        cwd=cwd,
        check=check,
        capture_output=True,
        text=True,
        env=env,
    )


def _git(cwd, *args, check=True):
    return _run(
        [
            "git",
            "-c",
            "user.email=test@example.com",
            "-c",
            "user.name=Test",
            "-c",
            "core.hooksPath=/dev/null",
            *args,
        ],
        cwd=cwd,
        check=check,
    )


def _script_env(tmp_path: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["GIT_CONFIG_GLOBAL"] = str(tmp_path / "gitconfig")
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["AROUND_NJ_PAGES"] = str(tmp_path / "pages")
    return env


def _init_pages_remote(tmp_path: Path) -> tuple[Path, Path]:
    remote = tmp_path / "remote.git"
    pages = tmp_path / "pages"
    _run(["git", "init", "--bare", str(remote)])
    pages.mkdir()
    _git(pages, "init", "-b", "gh-pages")
    _git(pages, "config", "core.hooksPath", "/dev/null")
    _git(pages, "remote", "add", "origin", str(remote))
    (pages / "index.html").write_text("desk\n", encoding="utf-8")
    (pages / "snapshot.html").write_text("old snapshot\n", encoding="utf-8")
    _git(pages, "add", "index.html", "snapshot.html")
    _git(pages, "commit", "-m", "seed")
    _git(pages, "push", "-u", "origin", "gh-pages")
    return remote, pages


def _publish(tmp_path: Path, snapshot: Path, pages: Path | None = None):
    env = _script_env(tmp_path)
    if pages is not None:
        env["AROUND_NJ_PAGES"] = str(pages)
    return _run([str(SCRIPT), str(snapshot)], check=False, env=env)


def _remote_file(remote: Path, path: str) -> str:
    result = _run(
        ["git", "--git-dir", str(remote), "show", f"gh-pages:{path}"],
    )
    return result.stdout


def test_refuses_non_gh_pages_worktree(tmp_path):
    remote, pages = _init_pages_remote(tmp_path)
    _git(pages, "checkout", "-b", "joe/skip-snapshot-ci")
    snapshot = tmp_path / "new.html"
    snapshot.write_text("new snapshot\n", encoding="utf-8")

    result = _publish(tmp_path, snapshot)

    assert result.returncode == 1
    assert "must be checked out on gh-pages" in result.stderr
    assert _remote_file(remote, "snapshot.html") == "old snapshot\n"
    assert (pages / "index.html").read_text(encoding="utf-8") == "desk\n"


def test_fast_forwards_then_publishes_snapshot_only(tmp_path):
    remote, pages = _init_pages_remote(tmp_path)
    other = tmp_path / "other"
    _git(tmp_path, "clone", str(remote), str(other))
    _git(other, "checkout", "gh-pages")
    _git(other, "config", "core.hooksPath", "/dev/null")
    (other / "README.md").write_text("skip ci\n", encoding="utf-8")
    _git(other, "add", "README.md")
    _git(other, "commit", "-m", "docs")
    _git(other, "push", "origin", "gh-pages")

    snapshot = tmp_path / "new.html"
    snapshot.write_text("new snapshot\n", encoding="utf-8")
    result = _publish(tmp_path, snapshot)

    assert result.returncode == 0, result.stderr
    assert _remote_file(remote, "snapshot.html") == "new snapshot\n"
    assert _remote_file(remote, "index.html") == "desk\n"
    assert _remote_file(remote, "README.md") == "skip ci\n"


def test_no_snapshot_changes_exits_zero(tmp_path):
    _init_pages_remote(tmp_path)
    snapshot = tmp_path / "same.html"
    snapshot.write_text("old snapshot\n", encoding="utf-8")

    result = _publish(tmp_path, snapshot)

    assert result.returncode == 0, result.stderr
    assert "no snapshot changes" in result.stdout
