import os
import sqlite3
import stat
import tempfile

import pytest

from tidyline.db import snapshot
from tidyline.db.snapshot import SnapshotError, open_snapshot


def dump(path):
    conn = sqlite3.connect(path)
    try:
        return list(conn.iterdump())
    finally:
        conn.close()


@pytest.fixture
def scratch(tmp_path, monkeypatch):
    """Point the temp directory at an empty folder we can inspect afterwards."""
    folder = tmp_path / "scratch"
    folder.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(folder))
    return folder


def test_copy_matches_source_and_is_private(fixture_db, scratch):
    before = fixture_db.read_bytes()
    with open_snapshot(fixture_db) as copy:
        assert copy != fixture_db
        assert copy.parent.parent == scratch
        assert stat.S_IMODE(os.stat(copy.parent).st_mode) == 0o700
        assert stat.S_IMODE(os.stat(copy).st_mode) == 0o600
        assert dump(copy) == dump(fixture_db)
    assert fixture_db.read_bytes() == before


def test_copy_includes_changes_in_the_wal(tmp_path, scratch):
    source = tmp_path / "wal.sqlite"
    writer = sqlite3.connect(source)
    writer.execute("PRAGMA journal_mode=WAL")
    writer.execute("CREATE TABLE t (x)")
    writer.execute("INSERT INTO t VALUES (1)")
    writer.commit()  # still in the -wal file; the writer stays open
    try:
        with open_snapshot(source) as copy:
            conn = sqlite3.connect(copy)
            try:
                assert conn.execute("SELECT x FROM t").fetchall() == [(1,)]
            finally:
                conn.close()
    finally:
        writer.close()


def test_temp_directory_removed_after_success(fixture_db, scratch):
    with open_snapshot(fixture_db):
        assert list(scratch.iterdir())
    assert list(scratch.iterdir()) == []


def test_temp_directory_removed_after_error_in_body(fixture_db, scratch):
    with pytest.raises(RuntimeError):
        with open_snapshot(fixture_db):
            raise RuntimeError("boom")
    assert list(scratch.iterdir()) == []


def test_temp_directory_removed_when_copy_fails(tmp_path, scratch):
    not_a_database = tmp_path / "text.sqlite"
    not_a_database.write_text("this is not sqlite" * 100)
    with pytest.raises(SnapshotError):
        with open_snapshot(not_a_database):
            pass
    assert list(scratch.iterdir()) == []


def test_missing_source_is_a_clear_error(tmp_path, scratch):
    with pytest.raises(SnapshotError) as error:
        with open_snapshot(tmp_path / "missing.sqlite"):
            pass
    assert "does not exist" in str(error.value)
    assert not error.value.permission_problem


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores file permissions")
def test_unreadable_source_flags_permission_problem(fixture_db, scratch):
    fixture_db.chmod(0)
    try:
        with pytest.raises(SnapshotError) as error:
            with open_snapshot(fixture_db):
                pass
    finally:
        fixture_db.chmod(0o600)
    assert error.value.permission_problem
    assert "Full Disk Access" in str(error.value)
    assert list(scratch.iterdir()) == []


def test_busy_database_is_retried_then_fails(fixture_db, scratch, monkeypatch):
    sleeps = []
    monkeypatch.setattr(snapshot.time, "sleep", sleeps.append)
    locker = sqlite3.connect(fixture_db, isolation_level=None)
    locker.execute("BEGIN EXCLUSIVE")
    try:
        with pytest.raises(SnapshotError) as error:
            with open_snapshot(fixture_db, retries=3, wait=0.01):
                pass
    finally:
        locker.close()
    assert "busy after 3 attempts" in str(error.value)
    assert sleeps == [0.01, 0.01]
    assert list(scratch.iterdir()) == []


def test_busy_then_free_succeeds(fixture_db, scratch, monkeypatch):
    real = snapshot._copy_once
    calls = []

    def flaky(source, copy):
        calls.append(1)
        if len(calls) < 3:
            raise snapshot._Busy
        real(source, copy)

    monkeypatch.setattr(snapshot, "_copy_once", flaky)
    monkeypatch.setattr(snapshot.time, "sleep", lambda _: None)
    with open_snapshot(fixture_db) as copy:
        assert dump(copy) == dump(fixture_db)
    assert len(calls) == 3
