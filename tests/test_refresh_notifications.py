"""Each refresh sends at most one actionable alert, using local stage stubs."""

import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "run_around_nj_refresh.sh"


@pytest.mark.parametrize(
    "scrape,build,publish,runtime,expected_rc,alert",
    [
        (0, 0, 0, True, 0, None),
        (1, 0, 0, True, 0, "partners without RSS are missing"),
        (1, 7, 0, True, 7, "snapshot build failed"),
        (1, 0, 8, True, 8, "snapshot publish failed"),
        (0, 0, 0, False, 1, "missing venv python"),
    ],
)
def test_refresh_alerts(tmp_path, scrape, build, publish, runtime, expected_rc, alert):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    entry = scripts / SCRIPT.name
    # Relocate only the fixed lock path; exercise the real flock command.
    entry.write_text(
        SCRIPT.read_text().replace(
            'LOCK="/tmp/around-nj-refresh.lock"', f'LOCK="{tmp_path}/refresh.lock"'
        )
    )
    python = tmp_path / "venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.write_text(
        '#!/bin/sh\ncase "$1" in\n'
        '*scrape*) exit "$TEST_SCRAPE";;\n'
        '*build*) exit "$TEST_BUILD";;\nesac\nexit 99\n'
    )
    publisher = scripts / "publish_around_nj_snapshot.sh"
    publisher.write_text('#!/bin/sh\nexit "$TEST_PUBLISH"\n')
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    notifier = bin_dir / "jawn-ops"
    notifier.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$TEST_NOTICES"\n')
    for path in (python, publisher, notifier):
        path.chmod(0o755)
    if not runtime:
        python.chmod(0o644)
    notices = tmp_path / "notices"
    result = subprocess.run(
        ["bash", str(entry)],
        env={
            **os.environ,
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "AROUND_NJ_PUBLISH": "1",
            "TEST_SCRAPE": str(scrape),
            "TEST_BUILD": str(build),
            "TEST_PUBLISH": str(publish),
            "TEST_NOTICES": str(notices),
        },
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == expected_rc, result.stderr
    messages = notices.read_text().splitlines() if notices.exists() else []
    assert len(messages) == (0 if alert is None else 1)
    if alert is not None:
        assert alert in messages[0]
    if scrape and alert is not None:
        assert "partners without RSS are missing" in messages[0]
    if scrape and not build:
        assert "RSS snapshot still built" in result.stderr
