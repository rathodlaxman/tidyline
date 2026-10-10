"""Shared helpers for the check tests (synthetic fixture only)."""

import datetime as dt
import sqlite3

from fixtures import build_fixture as bf

from tidyline.checks import CheckOptions, run_checks
from tidyline.db.snapshot import open_snapshot
from tidyline.read import read_snapshot

TODAY = dt.date(2026, 10, 10)
U = bf.make_uuid


def edit(path, *statements):
    conn = sqlite3.connect(path)
    try:
        for statement, *params in statements:
            conn.execute(statement, *params)
        conn.commit()
    finally:
        conn.close()


def set_title(path, key, title):
    edit(path, ("UPDATE TMTask SET title = ? WHERE uuid = ?", (title, U(key))))


def snapshot_of(path):
    with open_snapshot(path) as copy:
        return read_snapshot(copy)


def findings(path, check, patterns=(), today=TODAY):
    return run_checks(
        snapshot_of(path),
        today,
        only=[check],
        options=CheckOptions(patterns=tuple(patterns)),
    )


def ids(found):
    return [tuple(r.id for r in f.refs) for f in found]


def first_ids(found):
    return [f.refs[0].id for f in found]
