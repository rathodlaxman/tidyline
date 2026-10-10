import datetime as dt
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from fixtures import build_fixture as bf

from tidyline import read as read_module
from tidyline.db.schema import SchemaError
from tidyline.db.snapshot import open_snapshot
from tidyline.model import Snapshot, TaskKind
from tidyline.read import ReadError, read_snapshot
from tidyline.recurrence import parse_rule

FIXED_TODAY = dt.date(2026, 10, 10)
U = bf.make_uuid


def edit(path, *statements):
    conn = sqlite3.connect(path)
    try:
        for statement, *params in statements:
            conn.execute(statement, *params)
        conn.commit()
    finally:
        conn.close()


def read_fixture(path) -> Snapshot:
    with open_snapshot(path) as copy:
        return read_snapshot(copy)


@pytest.fixture
def snapshot(fixture_db) -> Snapshot:
    return read_fixture(fixture_db)


def by_uuid(snapshot):
    return {task.uuid: task for task in snapshot.tasks}


# --- counts -----------------------------------------------------------------


def test_counts_match_the_fixture(snapshot):
    assert len(snapshot.areas) == 2
    assert len(snapshot.tags) == 2
    # Admin x2, Garden, Pottery, Photos, trashed Newsletter, done Spring Move
    assert len(snapshot.projects) == 7
    assert len(snapshot.headings) == 2
    assert len(snapshot.checklist_items) == 5
    # 26 rows carry a rule; the trashed template is ignored
    assert len(snapshot.templates) == 25
    assert len(snapshot.instances) == 5  # 3 open, 2 completed
    # 29 open (FIXTURE_EXPECTATIONS), 1 in the trashed project, 7 closed or trashed
    assert len(snapshot.todos) == bf.FIXTURE_EXPECTATIONS["open_todos"] + 1 + 7 == 37
    assert snapshot.warnings == ()


def test_todo_count_matches_the_database(fixture_db, snapshot):
    conn = sqlite3.connect(fixture_db)
    try:
        (expected,) = conn.execute(
            "SELECT COUNT(*) FROM TMTask WHERE type = 0 AND rt1_recurrenceRule IS NULL"
        ).fetchone()
    finally:
        conn.close()
    assert len(snapshot.todos) == expected


def test_snapshot_is_frozen_with_tuples(snapshot):
    for name in ("areas", "tags", "tasks", "checklist_items", "warnings"):
        assert isinstance(getattr(snapshot, name), tuple), name
    with pytest.raises(AttributeError):
        snapshot.tasks = ()


def test_closed_and_trashed_rows_are_kept(snapshot):
    tasks = by_uuid(snapshot)
    assert tasks[U("t_done")].status == 3
    assert tasks[U("t_cancelled")].status == 2
    assert tasks[U("t_trashed")].trashed
    assert tasks[U("proj_trashed")].trashed
    assert tasks[U("proj_done")].status == 3
    # its project is trashed, the task itself is not
    assert not tasks[U("t_in_trashed_project")].trashed


def test_kinds_and_references(snapshot):
    tasks = by_uuid(snapshot)
    assert tasks[U("proj_garden")].kind is TaskKind.PROJECT
    assert tasks[U("head_plan")].kind is TaskKind.HEADING
    assert tasks[U("head_plan")].project_uuid == U("proj_garden")
    measure = tasks[U("t_measure")]
    assert measure.heading_uuid == U("head_plan")
    assert measure.project_uuid is None
    assert measure.tag_uuids == (U("tag_errand"), U("tag_waiting"))
    assert tasks[U("t_level")].project_uuid == U("proj_garden")
    assert tasks[U("t_lease")].area_uuid == U("area_home")
    assert tasks[U("t_inbox")].start == 0
    assert tasks[U("t_door")].start == 2


def test_dates_and_raw_values(snapshot):
    tasks = by_uuid(snapshot)
    today = tasks[U("t_today")]
    assert today.start_date == FIXED_TODAY
    assert today.raw_start_date == bf.pack_date(FIXED_TODAY)
    suppressed = tasks[U("t_suppressed")]
    assert suppressed.deadline == FIXED_TODAY - dt.timedelta(days=3)
    assert suppressed.deadline_suppression_date == FIXED_TODAY
    assert suppressed.deadline_suppressed
    assert today.created.tzinfo is not None
    assert today.created == dt.datetime(2026, 9, 10, 9, tzinfo=dt.timezone.utc)
    assert tasks[U("t_done")].stopped is not None
    assert today.stopped is None


def test_checklist_items(snapshot):
    items = [i for i in snapshot.checklist_items if i.task_uuid == U("t_nextweek")]
    assert [i.title for i in items] == [
        "Find the insurance card",
        "Check opening hours",
        "Pick a date",
    ]
    assert [i.status for i in items] == [3, 0, 0]


# --- This Evening -----------------------------------------------------------


def test_this_evening_has_start_bucket_1(snapshot):
    buckets = {t.uuid: t.start_bucket for t in snapshot.tasks}
    assert buckets[U("t_evening")] == 1
    assert {u for u, b in buckets.items() if b != 0} == {U("t_evening")}


# --- recurrence -------------------------------------------------------------


def test_templates_carry_their_rule(snapshot):
    blobs = bf.rule_blobs(FIXED_TODAY)
    templates = {t.uuid: t for t in snapshot.templates}
    for key, blob in blobs.items():
        if key == "tpl_trashed":
            continue
        assert templates[U(key)].recurrence == parse_rule(blob), key
    assert templates[U("tpl_monthly_15")].recurrence.text == "Monthly on day 15"
    assert templates[U("tpl_weekly_fri")].recurrence.text == "Weekly on Fri"
    assert templates[U("tpl_invalid_plist")].recurrence.text == (
        "recurring (rule unreadable)"
    )


def test_templates_read_from_sql_keep_their_fields(snapshot):
    template = by_uuid(snapshot)[U("tpl_monthly_15")]
    assert template.kind is TaskKind.TODO
    assert (template.status, template.start, template.trashed) == (0, 2, False)
    assert template.area_uuid == U("area_home")
    assert template.title == "Pay the rent"
    assert by_uuid(snapshot)[U("tpl_paused")].recurrence_paused
    assert not template.recurrence_paused


def test_trashed_template_is_ignored(snapshot):
    assert U("tpl_trashed") not in by_uuid(snapshot)


def test_leftover_template_is_reported(snapshot):
    assert snapshot.leftover_template_uuids == (U("tpl_leftover"),)
    assert U("tpl_leftover") in {t.uuid for t in snapshot.templates}


def test_leftover_through_a_heading_and_a_missing_project(fixture_db):
    edit(
        fixture_db,
        ("UPDATE TMTask SET heading = ? WHERE uuid = ?", (U("head_x"), U("tpl_daily"))),
        ("UPDATE TMTask SET project = 'gone' WHERE uuid = ?", (U("tpl_weekly_sun"),)),
        (
            "INSERT INTO TMTask (uuid, type, status, trashed, title, start, project, "
            '"index", startBucket) VALUES (?, 2, 0, 0, ?, 1, ?, 99, 0)',
            (U("head_x"), "Under a trashed project", U("proj_trashed")),
        ),
    )
    snapshot = read_fixture(fixture_db)
    assert set(snapshot.leftover_template_uuids) == {
        U("tpl_leftover"),
        U("tpl_daily"),
        U("tpl_weekly_sun"),
    }


def test_template_with_no_open_instance_is_returned(snapshot):
    instance_of = {t.recurrence_template_uuid for t in snapshot.instances}
    assert U("tpl_weekly_fri") not in instance_of
    assert U("tpl_weekly_fri") in {t.uuid for t in snapshot.templates}


def test_instances_link_to_templates(snapshot):
    templates = {t.uuid for t in snapshot.templates}
    links = {t.recurrence_template_uuid for t in snapshot.instances}
    expected = {U(k) for k in (*bf.OPEN_INSTANCES, *bf.COMPLETED_INSTANCES)}
    assert links == expected
    assert links <= templates
    for instance in snapshot.instances:
        assert instance.recurrence is None


# --- joins by UUID ------------------------------------------------------------


def test_identical_titles_are_not_confused(snapshot):
    tasks = by_uuid(snapshot)
    home, studio = tasks[U("proj_admin_home")], tasks[U("proj_admin_studio")]
    assert home.title == studio.title == "Admin"
    assert home.area_uuid == U("area_home")
    assert studio.area_uuid == U("area_studio")
    assert tasks[U("t_dup_a")].project_uuid == U("proj_admin_home")
    assert tasks[U("t_dup_b")].project_uuid == U("proj_admin_studio")
    assert tasks[U("t_overdue")].project_uuid == U("proj_admin_studio")


def test_same_title_on_two_tasks_keeps_each_ones_fields(fixture_db):
    edit(
        fixture_db,
        ("UPDATE TMTask SET title = 'Same' WHERE uuid IN (?, ?)",
         (U("t_today"), U("t_nextweek"))),
    )  # fmt: skip
    tasks = by_uuid(read_fixture(fixture_db))
    assert tasks[U("t_today")].start_date == FIXED_TODAY
    assert tasks[U("t_nextweek")].start_date == FIXED_TODAY + dt.timedelta(days=7)
    assert tasks[U("t_nextweek")].tag_uuids == ()


# --- bad values -------------------------------------------------------------


def test_undecodable_values_give_none_and_a_warning(fixture_db):
    bad_date = 2026 << 16 | 13 << 12 | 1 << 7  # month 13
    edit(
        fixture_db,
        ("UPDATE TMTask SET startDate = ? WHERE uuid = ?", (bad_date, U("t_today"))),
        (
            "UPDATE TMTask SET deadlineSuppressionDate = ? WHERE uuid = ?",
            (bad_date, U("t_suppressed")),
        ),
        ("UPDATE TMTask SET creationDate = 1e20 WHERE uuid = ?", (U("t_level"),)),
        ("UPDATE TMTask SET startDate = ? WHERE uuid = ?", (bad_date, U("tpl_daily"))),
    )
    snapshot = read_fixture(fixture_db)
    tasks = by_uuid(snapshot)
    today = tasks[U("t_today")]
    assert today.start_date is None
    assert today.raw_start_date == bad_date
    suppressed = tasks[U("t_suppressed")]
    assert suppressed.deadline_suppression_date is None
    assert suppressed.deadline_suppressed  # still set, so rule 5 stays off
    assert tasks[U("t_level")].created is None
    assert tasks[U("tpl_daily")].start_date is None
    assert len(snapshot.warnings) == 4
    joined = "\n".join(snapshot.warnings)
    assert f"TMTask {U('t_today')}: startDate {bad_date}" in joined
    assert "deadlineSuppressionDate" in joined
    assert "creationDate 1e+20" in joined
    assert "Water the ferns" not in joined  # warnings carry no titles


def test_dangling_reference_gives_a_warning(fixture_db):
    edit(
        fixture_db, ("UPDATE TMTask SET area = 'gone' WHERE uuid = ?", (U("t_lease"),))
    )
    snapshot = read_fixture(fixture_db)
    assert by_uuid(snapshot)[U("t_lease")].area_uuid is None
    assert snapshot.warnings == (
        f"TMTask {U('t_lease')}: area gone does not exist; ignored",
    )


def test_unknown_status_falls_back_to_the_stored_value(fixture_db):
    edit(fixture_db, ("UPDATE TMTask SET status = 1 WHERE uuid = ?", (U("t_lease"),)))
    snapshot = read_fixture(fixture_db)
    assert by_uuid(snapshot)[U("t_lease")].status == 1
    assert snapshot.warnings == (f"TMTask {U('t_lease')}: unknown status 1",)


# --- Unicode ------------------------------------------------------------------


UNICODE_TITLES = [
    "Comprar pimentón y azafrán",
    "Müll rausbringen und Gelbe Säcke holen",
    "請求書の写真を整理する",
    "ﬁle the ＲＥＰＯＲＴ",  # NFKC would change both the ligature and full-width
    "Café vs Café",  # combining accent next to a precomposed one
    "STRASSE straße ẞ",  # casefold would change these
    "İstanbul ı",
]


def test_unicode_titles_round_trip_unchanged(fixture_db):
    keys = ["t_lease", "t_cables", "t_card", "t_portfolio", "t_level", "t_bolts"]
    edit(
        fixture_db,
        *[
            ("UPDATE TMTask SET title = ? WHERE uuid = ?", (title, U(key)))
            for key, title in zip(keys, UNICODE_TITLES[3:] + ["x"], strict=False)
        ],
    )
    tasks = by_uuid(read_fixture(fixture_db))
    for key, title in zip(keys, UNICODE_TITLES[3:], strict=False):
        assert tasks[U(key)].title == title
    titles = {t.title for t in tasks.values()}
    assert set(UNICODE_TITLES[:3]) <= titles


# --- schema and input -------------------------------------------------------------


def test_missing_start_bucket_gives_the_schema_error(fixture_db):
    edit(fixture_db, ("ALTER TABLE TMTask DROP COLUMN startBucket",))
    with pytest.raises(SchemaError) as error:
        read_fixture(fixture_db)
    assert "startBucket" in str(error.value)
    assert "tidyline doctor" in str(error.value)


def test_missing_path_is_a_clear_error(tmp_path):
    with pytest.raises(ReadError, match="No database copy"):
        read_snapshot(tmp_path / "nothing.sqlite")


# --- guards -------------------------------------------------------------------


def test_importing_read_does_not_import_things():
    code = (
        "import sys, tidyline.read\n"
        "loaded = [m for m in sys.modules if m.split('.')[0] == 'things']\n"
        "sys.exit(1 if loaded else 0)\n"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True)
    assert result.returncode == 0, result.stderr.decode()


FORBIDDEN = (
    "token",
    "complete",
    "show",
    "url",
    "today",
    "upcoming",
    "anytime",
    "someday",
    "inbox",
    "logbook",
    "TMSettings",
)


def test_read_source_has_no_forbidden_names():
    source = Path(read_module.__file__).read_text(encoding="utf-8")
    found = [name for name in FORBIDDEN if re.search(rf"\b{name}\b", source)]
    assert found == []
