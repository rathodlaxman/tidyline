import datetime as dt
import os
import sqlite3
import tempfile
import time
from pathlib import Path

import pytest
from fixtures import build_fixture as bf

REAL_LIBRARY = str(Path.home() / "Library")
FIXED_TODAY = dt.date(2026, 10, 10)


def _import_things_with_an_empty_home():
    """Import things.py once with HOME pointing at an empty directory.

    Importing things.py globs ~/Library/Group Containers to find a default
    path (DESIGN.md 5). Tests must not list the real directory, so the first
    import happens here, before any test module imports it.
    """
    saved = os.environ.get("HOME")
    with tempfile.TemporaryDirectory() as empty:
        os.environ["HOME"] = empty
        try:
            import things  # noqa: F401
        finally:
            if saved is None:
                del os.environ["HOME"]
            else:
                os.environ["HOME"] = saved


_import_things_with_an_empty_home()


@pytest.fixture(autouse=True)
def never_touch_library(monkeypatch):
    """Fail any test that opens a database or lists a directory under ~/Library."""
    touched = []
    real_connect, real_scandir = sqlite3.connect, os.scandir

    def spy_connect(database, *args, **kwargs):
        touched.append(str(database))
        return real_connect(database, *args, **kwargs)

    def spy_scandir(path=None):
        touched.append(str(path))
        return real_scandir(path) if path is not None else real_scandir()

    monkeypatch.setattr(sqlite3, "connect", spy_connect)
    monkeypatch.setattr(os, "scandir", spy_scandir)
    yield
    assert [t for t in touched if REAL_LIBRARY in t] == []


def set_timezone(name):
    """Set the process timezone (a POSIX TZ string such as "IST-5:30")."""
    os.environ["TZ"] = name
    time.tzset()


@pytest.fixture(autouse=True)
def pinned_timezone():
    """Run every test in UTC unless it sets another zone, so local-time results
    never depend on the machine running the tests."""
    saved = os.environ.get("TZ")
    set_timezone("UTC0")
    yield set_timezone
    if saved is None:
        del os.environ["TZ"]
    else:
        os.environ["TZ"] = saved
    time.tzset()


@pytest.fixture
def fixture_db(tmp_path):
    """A synthetic Things database in tmp_path."""
    path = tmp_path / "fixture.sqlite"
    bf.build_fixture(path, FIXED_TODAY)
    return path
