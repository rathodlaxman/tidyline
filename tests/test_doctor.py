import os
import sqlite3

import pytest

from tidyline import cli
from tidyline.cli import main


@pytest.fixture
def tested_env(tmp_path, monkeypatch):
    """Pretend to run on the tested macOS and Things versions, with a fake HOME."""
    import plistlib

    plist = tmp_path / "Info.plist"
    plist.write_bytes(plistlib.dumps({"CFBundleShortVersionString": "3.24.1"}))
    monkeypatch.setattr(cli, "THINGS_INFO_PLIST", plist)
    monkeypatch.setattr(cli, "_macos_version", lambda: "27.0.1")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("THINGSDB", raising=False)
    monkeypatch.delenv("TERM_PROGRAM", raising=False)
    return tmp_path


def fields(out):
    """Parse 'Label:   value' lines of doctor output into a dict."""
    pairs = (line.split(":", 1) for line in out.splitlines() if ":" in line)
    return {label.strip(): value.strip() for label, value in pairs}


def run(capsys, *argv):
    code = main(list(argv))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_healthy_fixture(tested_env, fixture_db, capsys):
    code, out, err = run(capsys, "--db", str(fixture_db), "doctor")
    assert code == 0
    assert "~/fixture.sqlite" in out
    assert str(tested_env) not in out
    shown = fields(out)
    assert shown["Snapshot copy"] == "ok"
    assert shown["Database version"] == "29"
    assert shown["Things app"] == "3.24.1"
    assert shown["macOS"] == "27.0.1"
    assert shown["Architecture"]
    assert shown["Tested"] == "yes"
    assert err == ""


def test_db_option_after_the_command(tested_env, fixture_db, capsys):
    code, out, _ = run(capsys, "doctor", "--db", str(fixture_db))
    assert code == 0
    assert "~/fixture.sqlite" in out


def test_uses_thingsdb_variable(tested_env, fixture_db, monkeypatch, capsys):
    monkeypatch.setenv("THINGSDB", str(fixture_db))
    code, out, _ = run(capsys, "doctor")
    assert code == 0
    assert "~/fixture.sqlite" in out


def test_untested_versions_warn_but_exit_zero(
    tested_env, fixture_db, monkeypatch, capsys
):
    monkeypatch.setattr(cli, "_macos_version", lambda: "99.0")
    monkeypatch.setattr(cli, "THINGS_INFO_PLIST", tested_env / "missing.plist")
    code, out, err = run(capsys, "--db", str(fixture_db), "doctor")
    assert code == 0
    shown = fields(out)
    assert shown["Things app"] == "unknown"
    assert shown["Tested"].startswith("no.")
    assert "macOS 27.0.1" in out
    assert "warning: macOS version 99.0 is untested." in err


def test_no_database_found_exits_one(tested_env, capsys):
    code, out, err = run(capsys, "doctor")
    assert code == 1
    assert fields(out)["Database"] == "not found"
    assert "THINGSDB" in err
    assert "--db" in err


def test_missing_db_path_exits_one(tested_env, capsys):
    code, _, err = run(capsys, "--db", str(tested_env / "nope.sqlite"), "doctor")
    assert code == 1
    assert "nope.sqlite" in err


def test_missing_column_exits_one_with_versions(tested_env, fixture_db, capsys):
    conn = sqlite3.connect(fixture_db)
    conn.execute("ALTER TABLE TMTask RENAME COLUMN rt1_recurrenceRule TO renamed")
    conn.commit()
    conn.close()
    code, out, err = run(capsys, "--db", str(fixture_db), "doctor")
    assert code == 1
    assert fields(out)["Schema"] == "failed"
    assert "rt1_recurrenceRule" in err
    assert "database version 29" in err


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores file permissions")
def test_permission_problem_explains_full_disk_access(
    tested_env, fixture_db, monkeypatch, capsys
):
    monkeypatch.setenv("TERM_PROGRAM", "iTerm.app")
    fixture_db.chmod(0)
    try:
        code, out, err = run(capsys, "--db", str(fixture_db), "doctor")
    finally:
        fixture_db.chmod(0o600)
    assert code == 1
    assert fields(out)["Snapshot copy"] == "failed"
    assert "Full Disk Access" in err
    assert "System Settings > Privacy & Security" in err
    assert "iTerm" in err


def test_permission_error_while_locating(tested_env, monkeypatch, capsys):
    def deny(*args, **kwargs):
        raise PermissionError(1, "Operation not permitted")

    monkeypatch.setattr(cli, "locate_database", deny)
    code, out, err = run(capsys, "doctor")
    assert code == 1
    assert "permission denied" in fields(out)["Database"]
    assert "Full Disk Access" in err
