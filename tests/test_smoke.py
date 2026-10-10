"""End to end: the installed `tidyline` entry point, fixture data only.

The subprocess gets an empty HOME, so nothing under the real ~/Library is
listed, and a sitecustomize that makes opening a socket fail, so a network
call anywhere would break these tests (as pytest-socket does in-process).
"""

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

BLOCK_SOCKETS = (
    "import socket\n"
    "def _blocked(*args, **kwargs):\n"
    "    raise RuntimeError('network access is blocked in tests')\n"
    "socket.socket = _blocked\n"
    "socket.create_connection = _blocked\n"
)


@pytest.fixture
def entry_point():
    path = Path(sys.executable).parent / "tidyline"
    assert path.exists(), "the tidyline entry point is not installed; run uv sync"
    return path


@pytest.fixture
def env(tmp_path):
    guard = tmp_path / "guard"
    guard.mkdir()
    (guard / "sitecustomize.py").write_text(BLOCK_SOCKETS, encoding="utf-8")
    home = tmp_path / "home"
    home.mkdir()
    clean = {
        key: value
        for key, value in os.environ.items()
        if key not in {"THINGSDB", "PYTHONPATH", "PYTHONSTARTUP"}
    }
    clean.update(HOME=str(home), PYTHONPATH=str(guard), NO_COLOR="1")
    return clean


def run(entry_point, env, *args):
    return subprocess.run(
        [str(entry_point), *args], capture_output=True, text=True, env=env, timeout=60
    )


def test_the_socket_guard_works(env):
    result = subprocess.run(
        [sys.executable, "-c", "import socket; socket.socket()"],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode != 0
    assert "network access is blocked" in result.stderr


def test_version(entry_point, env):
    result = run(entry_point, env, "--version")
    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith("tidyline ")


def test_help_lists_the_commands(entry_point, env):
    result = run(entry_point, env, "--help")
    assert result.returncode == 0, result.stderr
    for command in ("doctor", "report", "export"):
        assert command in result.stdout


def test_doctor(entry_point, env, fixture_db):
    result = run(entry_point, env, "--db", str(fixture_db), "doctor")
    assert result.returncode == 0, result.stderr
    assert "Schema:" in result.stdout and "ok" in result.stdout
    assert "Database version:" in result.stdout


def test_report_to_the_terminal(entry_point, env, fixture_db):
    result = run(entry_point, env, "--db", str(fixture_db), "report")
    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith("tidyline report\n")
    assert "Health checks arrive in v0.2." in result.stdout
    assert "\x1b" not in result.stdout


def test_report_to_a_file(entry_point, env, fixture_db, tmp_path):
    out = tmp_path / "report.txt"
    result = run(entry_point, env, "--db", str(fixture_db), "report", "--out", str(out))
    assert result.returncode == 0, result.stderr
    assert stat.S_IMODE(out.stat().st_mode) == 0o600
    assert out.read_text(encoding="utf-8").startswith("tidyline report\n")
    assert "recurring tasks" in result.stderr


def test_export(entry_point, env, fixture_db, tmp_path):
    out = tmp_path / "export.json"
    result = run(entry_point, env, "--db", str(fixture_db), "export", "--out", str(out))
    assert result.returncode == 0, result.stderr
    assert stat.S_IMODE(out.stat().st_mode) == 0o600
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["export_schema_version"] == "1"
    assert len(data["tasks"]) == 37
    assert "personal task data" in result.stderr


def test_second_export_to_the_same_file_is_refused(
    entry_point, env, fixture_db, tmp_path
):
    out = tmp_path / "export.json"
    args = ("--db", str(fixture_db), "export", "--out", str(out))
    assert run(entry_point, env, *args).returncode == 0
    before = out.read_bytes()
    again = run(entry_point, env, *args)
    assert again.returncode == 1
    assert "already exists" in again.stderr
    assert out.read_bytes() == before


def test_missing_database_is_a_clear_failure(entry_point, env, tmp_path):
    result = run(entry_point, env, "--db", str(tmp_path / "none.sqlite"), "doctor")
    assert result.returncode == 1
    assert "error:" in result.stderr
