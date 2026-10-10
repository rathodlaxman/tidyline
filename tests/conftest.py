import datetime as dt
import os
import sqlite3
from pathlib import Path

import pytest
from fixtures import build_fixture as bf

REAL_LIBRARY = str(Path.home() / "Library")
FIXED_TODAY = dt.date(2026, 10, 10)


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


@pytest.fixture
def fixture_db(tmp_path):
    """A synthetic Things database in tmp_path."""
    path = tmp_path / "fixture.sqlite"
    bf.build_fixture(path, FIXED_TODAY)
    return path
