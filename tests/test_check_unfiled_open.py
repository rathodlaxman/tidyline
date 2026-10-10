import datetime as dt

from checks_helpers import TODAY, U, edit, findings, first_ids, snapshot_of

from tidyline.checks.scope import Scope
from tidyline.status import Status, effective_status

CHECK = "unfiled_open"


def status(path, key):
    task = Scope(snapshot_of(path)).tasks[U(key)]
    return effective_status(task, None, TODAY)


def test_hits(fixture_db):
    found = findings(fixture_db, CHECK)
    assert first_ids(found) == [U("t_cables"), U("t_card"), U("t_de")]
    assert {f.message for f in found} == {"open to-do with no area and no project"}
    assert all(f.severity == "warning" for f in found)


def test_inbox_task_is_not_flagged(fixture_db):
    assert status(fixture_db, "t_inbox") is Status.INBOX
    assert U("t_inbox") not in first_ids(findings(fixture_db, CHECK))


def test_unfiled_today_task_is_flagged(fixture_db):
    edit(fixture_db, (
        "UPDATE TMTask SET start = 1, startDate = ? WHERE uuid = ?",
        ((2026 << 16) | (10 << 12) | (10 << 7), U("t_cables")),
    ))  # fmt: skip
    assert status(fixture_db, "t_cables") is Status.TODAY
    assert U("t_cables") in first_ids(findings(fixture_db, CHECK))


def test_unfiled_dated_upcoming_task_is_flagged(fixture_db):
    future = dt.date(2026, 11, 1)
    edit(fixture_db, (
        "UPDATE TMTask SET start = 2, startDate = ? WHERE uuid = ?",
        ((future.year << 16) | (future.month << 12) | (future.day << 7), U("t_card")),
    ))  # fmt: skip
    assert status(fixture_db, "t_card") is Status.UPCOMING
    assert U("t_card") in first_ids(findings(fixture_db, CHECK))


def test_inbox_task_with_a_date_is_still_inbox_and_not_flagged(fixture_db):
    edit(fixture_db, (
        "UPDATE TMTask SET startDate = ? WHERE uuid = ?",
        ((2026 << 16) | (10 << 12) | (10 << 7), U("t_inbox")),
    ))  # fmt: skip
    assert status(fixture_db, "t_inbox") is Status.INBOX
    assert U("t_inbox") not in first_ids(findings(fixture_db, CHECK))


def test_filed_tasks_are_not_flagged(fixture_db):
    flagged = set(first_ids(findings(fixture_db, CHECK)))
    # area only, project only, heading only (project through the heading)
    for key in ("t_lease", "t_level", "t_measure", "tpl_daily:instance"):
        assert U(key) not in flagged, key


def test_closed_and_trashed_unfiled_are_not_flagged(fixture_db):
    edit(
        fixture_db,
        ("UPDATE TMTask SET status = 3 WHERE uuid = ?", (U("t_cables"),)),
        ("UPDATE TMTask SET trashed = 1 WHERE uuid = ?", (U("t_card"),)),
    )
    assert first_ids(findings(fixture_db, CHECK)) == [U("t_de")]
