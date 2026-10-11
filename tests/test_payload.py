"""The `prompt` payload (llm/payload.py, DESIGN.md 7.6), against the synthetic
fixture only.

Expected numbers are counted here straight from the fixture's SQLite rows, with
their own rules, not through tidyline's reader, status or check code.
"""

import datetime as dt
import json
import sqlite3
import unicodedata

import pytest
from checks_helpers import edit
from fixtures import build_fixture as bf

from tidyline.anonymise import WITHHELD_RULE_FIELDS
from tidyline.db.snapshot import open_snapshot
from tidyline.decode import decode_text, label_map
from tidyline.llm.payload import build_payload
from tidyline.llm.prompt import build_prompt, load_template
from tidyline.read import read_snapshot

U = bf.make_uuid
TODAY = dt.date(2026, 10, 10)
EXPORTED_AT = dt.datetime(2026, 10, 10, 12, tzinfo=dt.timezone.utc)
STATUSES = ("inbox", "today", "this_evening", "upcoming", "anytime", "someday")


def snapshot_of(path):
    with open_snapshot(path) as copy:
        return read_snapshot(copy)


def payload_of(path, level="light"):
    data = build_payload(
        snapshot_of(path), today=TODAY, exported_at=EXPORTED_AT, level=level
    )
    return json.loads(json.dumps(data, ensure_ascii=False))


def by_id(rows):
    return {row["id"]: row for row in rows}


# --- an independent count from the fixture rows ----


def packed(day):
    return (day.year << 16) | (day.month << 12) | (day.day << 7)


def midnight(day):
    return dt.datetime.combine(day, dt.time(0), tzinfo=dt.timezone.utc).timestamp()


class Rows:
    """The fixture's rows, read with plain SQL. EXPORTED_AT is UTC, so local
    dates are UTC dates here."""

    def __init__(self, path):
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        try:
            self.todos = [dict(r) for r in conn.execute("""
                SELECT t.uuid, t.status, t.trashed, t.start, t.startDate,
                       t.startBucket, t.deadline, t.deadlineSuppressionDate,
                       t.stopDate, t.area, h.trashed AS heading_trashed,
                       p.uuid AS project, p.trashed AS project_trashed,
                       p.start AS project_start, p.area AS project_area,
                       (SELECT COUNT(*) FROM TMTaskTag g WHERE g.tasks = t.uuid)
                           AS tag_count
                FROM TMTask t
                LEFT JOIN TMTask h ON h.uuid = t.heading AND h.type = 2
                LEFT JOIN TMTask p ON p.uuid = COALESCE(t.project, h.project)
                                  AND p.type = 1
                WHERE t.type = 0 AND t.rt1_recurrenceRule IS NULL
            """)]  # fmt: skip
            self.projects = [dict(r) for r in conn.execute(
                "SELECT uuid, status, trashed, start, area FROM TMTask WHERE type = 1"
            )]  # fmt: skip
            self.templates = [dict(r) for r in conn.execute("""
                SELECT t.uuid, p.uuid AS project, p.trashed AS project_trashed,
                       COALESCE(t.project, h.project) AS project_ref
                FROM TMTask t
                LEFT JOIN TMTask h ON h.uuid = t.heading
                LEFT JOIN TMTask p ON p.uuid = COALESCE(t.project, h.project)
                WHERE t.rt1_recurrenceRule IS NOT NULL AND t.trashed = 0
            """)]  # fmt: skip
            self.tag_links = [tuple(r) for r in conn.execute(
                "SELECT tasks, tags FROM TMTaskTag"
            )]  # fmt: skip
            self.area_count = conn.execute("SELECT COUNT(*) FROM TMArea").fetchone()[0]
        finally:
            conn.close()

    def open(self):
        return [t for t in self.todos if t["status"] == 0 and t["trashed"] == 0]

    def live(self):
        return [
            t
            for t in self.open()
            if not t["heading_trashed"] and not t["project_trashed"]
        ]

    def in_trash(self):
        return [t for t in self.open() if t["heading_trashed"] or t["project_trashed"]]

    def completed(self):
        return [t for t in self.todos if t["status"] == 3 and t["trashed"] == 0]

    @staticmethod
    def status(t):
        today = packed(TODAY)
        if t["start"] == 0:
            return "inbox"
        if t["project_start"] == 2:
            return "someday"
        if t["startDate"] is not None:
            if t["startDate"] > today:
                return "upcoming"
            return "this_evening" if t["startBucket"] == 1 else "today"
        if (
            t["deadline"] is not None
            and t["deadline"] <= today
            and t["deadlineSuppressionDate"] is None
        ):
            return "today"
        return "someday" if t["start"] == 2 else "anytime"

    def by_status(self, todos):
        return {s: sum(self.status(t) == s for t in todos) for s in STATUSES}

    @staticmethod
    def within(t, days):
        first = midnight(TODAY - dt.timedelta(days=days - 1))
        return first <= t["stopDate"] < midnight(TODAY + dt.timedelta(days=1))

    @staticmethod
    def area_of(t):
        return t["area"] or t["project_area"]


@pytest.fixture
def spread_db(fixture_db):
    """Completion dates spread over the windows: 13 days ago is inside 14 days,
    14 days ago is not; 29 days ago is inside 30 days, 30 is not."""
    noon = dt.datetime.combine(TODAY, dt.time(12), tzinfo=dt.timezone.utc)
    for key, days in (
        ("t_done", 13),
        ("t_in_done_project", 14),
        ("t_photos_done", 29),
    ):
        stamp = (noon - dt.timedelta(days=days)).timestamp()
        edit(
            fixture_db,
            ("UPDATE TMTask SET stopDate = ? WHERE uuid = ?", (stamp, U(key))),
        )
    edit(fixture_db, (
        "UPDATE TMTask SET stopDate = ? WHERE uuid = "
        "(SELECT uuid FROM TMTask WHERE type = 0 AND status = 3 AND trashed = 0 "
        "AND uuid NOT IN (?, ?, ?) ORDER BY uuid LIMIT 1)",
        ((noon - dt.timedelta(days=30)).timestamp(),
         U("t_done"), U("t_in_done_project"), U("t_photos_done")),
    ))  # fmt: skip
    return fixture_db


# --- summary ----


def test_summary_equals_an_independent_count(spread_db):
    rows = Rows(spread_db)
    summary = payload_of(spread_db)["summary"]
    live, completed = rows.live(), rows.completed()
    projects = [p for p in rows.projects if p["trashed"] == 0]
    open_projects = [p for p in projects if p["status"] == 0]
    leftover = [t for t in rows.templates if not t["project"] and t["project_ref"]]
    leftover += [t for t in rows.templates if t["project_trashed"]]
    expected = {
        "open_todos": len(live),
        "by_status": rows.by_status(live),
        "open_in_trashed_project": len(rows.in_trash()),
        "areas": rows.area_count,
        "projects": {
            "open": len(open_projects),
            "someday": sum(p["start"] == 2 for p in open_projects),
            "active": sum(p["start"] != 2 for p in open_projects),
            "completed": sum(p["status"] == 3 for p in projects),
            "trashed": sum(p["trashed"] == 1 for p in rows.projects),
        },
        "completed_todos": {
            "total": len(completed),
            "last_14_days": sum(rows.within(t, 14) for t in completed),
            "last_30_days": sum(rows.within(t, 30) for t in completed),
        },
        "recurring_templates": {
            "live": len(rows.templates) - len(leftover),
            "leftover": len(leftover),
        },
        "tagged_open_todos": sum(t["tag_count"] > 0 for t in live),
    }
    assert summary == expected
    # the fixture really exercises every number
    assert (
        expected["completed_todos"]["last_14_days"]
        < (expected["completed_todos"]["last_30_days"])
        < expected["completed_todos"]["total"]
    )
    assert all(expected["by_status"].values())
    assert expected["open_in_trashed_project"] and expected["tagged_open_todos"]
    assert expected["recurring_templates"]["leftover"]


def test_area_rows_equal_an_independent_count(spread_db):
    rows = Rows(spread_db)
    areas = payload_of(spread_db)["areas"]
    assert len(areas) == rows.area_count
    for area in areas:
        live = [t for t in rows.live() if rows.area_of(t) == area["id"]]
        done = [t for t in rows.completed() if rows.area_of(t) == area["id"]]
        assert area == {
            "id": area["id"],
            "title": area["title"],
            "open_projects": sum(
                p["area"] == area["id"] and p["status"] == 0 and p["trashed"] == 0
                for p in rows.projects
            ),
            "open_todos": len(live),
            "by_status": rows.by_status(live),
            "completed_last_14_days": sum(rows.within(t, 14) for t in done),
            "completed_last_30_days": sum(rows.within(t, 30) for t in done),
            "completed_total": len(done),
        }


def test_project_rows_equal_an_independent_count(spread_db):
    rows = Rows(spread_db)
    projects = by_id(payload_of(spread_db)["projects"])
    holding = {t["project"] for t in rows.open()}
    expected_ids = {
        p["uuid"]
        for p in rows.projects
        if (p["status"] == 0 and p["trashed"] == 0) or p["uuid"] in holding
    }
    assert set(projects) == expected_ids
    for uuid, project in projects.items():
        todos = [t for t in rows.open() if t["project"] == uuid]
        done = [t for t in rows.completed() if t["project"] == uuid]
        assert project["open_todos"] == len(todos), uuid
        assert project["by_status"] == rows.by_status(todos), uuid
        assert project["completed_total"] == len(done), uuid
        assert project["completed_last_30_days"] == sum(
            rows.within(t, 30) for t in done
        )
    assert projects[U("proj_trashed")]["trashed"] is True
    assert projects[U("proj_pottery")]["state"] == "someday"
    assert projects[U("proj_garden")]["state"] == "active"
    assert projects[U("proj_garden")]["headings"] == 2
    assert U("proj_done") not in projects  # completed, holds no open to-do


def test_tag_rows_equal_an_independent_count(fixture_db):
    rows = Rows(fixture_db)
    live = {t["uuid"] for t in rows.live()}
    done = {t["uuid"] for t in rows.completed()}
    tags = payload_of(fixture_db)["tags"]
    assert {t["title"] for t in tags} == {"errand", "waiting"}
    for tag in tags:
        tasks = {task for task, t in rows.tag_links if t == tag["id"]}
        assert tag["open_todos"] == len(tasks & live)
        assert tag["completed_total"] == len(tasks & done)


# --- open work only ----


def test_no_completed_cancelled_or_trashed_to_do_rows(fixture_db):
    rows = Rows(fixture_db)
    payload = payload_of(fixture_db)
    open_ids = {t["uuid"] for t in rows.open()}
    assert {t["id"] for t in payload["tasks"]} == open_ids
    closed = {t["uuid"] for t in rows.todos} - open_ids
    assert {U("t_done"), U("t_cancelled"), U("t_trashed")} <= closed
    text = json.dumps(payload)
    assert [uuid for uuid in closed if uuid in text] == []


def test_task_rows(fixture_db):
    tasks = by_id(payload_of(fixture_db)["tasks"])
    measure = tasks[U("t_measure")]
    assert list(measure) == [
        "id", "title", "notes", "area", "project", "heading", "effective_status",
        "start_date", "deadline", "created", "modified", "tags", "checklist_count",
        "recurrence", "in_trashed_project",
    ]  # fmt: skip
    assert measure["tags"] == [
        {"id": U("tag_errand"), "title": "errand"},
        {"id": U("tag_waiting"), "title": "waiting"},
    ]
    assert measure["checklist_count"] == 2
    assert (measure["created"], measure["modified"]) == ("2026-09-10", "2026-10-09")
    trashed = [t for t in tasks.values() if t["in_trashed_project"]]
    assert [t["project"]["id"] for t in trashed] == [U("proj_trashed")]


def test_headings_only_for_listed_projects(fixture_db):
    payload = payload_of(fixture_db)
    project_ids = {p["id"] for p in payload["projects"]}
    assert payload["headings"]
    for heading in payload["headings"]:
        assert heading["project"]["id"] in project_ids
    assert U("head_done") not in {h["id"] for h in payload["headings"]}


def test_template_instances_are_open_ones_only(fixture_db):
    payload = payload_of(fixture_db)
    task_ids = {t["id"] for t in payload["tasks"]}
    for template in payload["recurring_templates"]:
        assert "notes" not in template
        assert set(template["instances"]) <= task_ids


def test_top_level_keys(fixture_db):
    payload = payload_of(fixture_db, "strict")
    assert list(payload) == [
        "payload_schema_version", "anonymisation", "exported_at", "scope",
        "summary", "areas", "projects", "headings", "tasks", "tags",
        "recurring_templates", "checks_run", "findings", "data_read_warnings",
    ]  # fmt: skip
    assert payload["payload_schema_version"] == "1"
    assert payload["anonymisation"] == "strict"
    assert payload["scope"].startswith("Open work only")
    assert len(payload["checks_run"]) == 10


def test_none_level_is_refused(fixture_db):
    with pytest.raises(ValueError, match="light or strict"):
        payload_of(fixture_db, "none")


# --- anonymisation ----


def fold(text):
    return unicodedata.normalize("NFKC", text).casefold()


def test_strict_payload_has_no_stored_text_or_rule_timestamps(fixture_db):
    payload = payload_of(fixture_db, "strict")
    text = fold(json.dumps(payload, ensure_ascii=False))
    conn = sqlite3.connect(fixture_db)
    try:
        strings = [
            row[0]
            for sql in (
                "SELECT title FROM TMTask",
                "SELECT notes FROM TMTask",
                "SELECT title FROM TMArea",
                "SELECT title FROM TMTag",
                "SELECT title FROM TMChecklistItem",
            )
            for row in conn.execute(sql)
            if row[0]
        ]
    finally:
        conn.close()
    assert [s for s in strings if fold(s).strip() and fold(s).strip() in text] == []
    for entry in payload["tasks"] + payload["recurring_templates"]:
        raw = (entry["recurrence"] or {}).get("raw") or {}
        for key in WITHHELD_RULE_FIELDS:
            assert raw.get(key) is None, entry["id"]
    assert all(t["title"].startswith("Tag ") for t in payload["tags"])


def test_light_payload_drops_notes_and_checklists(fixture_db):
    payload = payload_of(fixture_db, "light")
    for task in payload["tasks"]:
        assert task["notes"] is None
        assert "checklist" not in task


def test_strict_labels_decode_to_real_titles(fixture_db):
    snapshot = snapshot_of(fixture_db)
    payload = payload_of(fixture_db, "strict")
    labels = label_map(snapshot)
    titles = {t.uuid: t.title for t in snapshot.tasks}
    titles |= {a.uuid: a.title for a in snapshot.areas}
    titles |= {t.uuid: t.title for t in snapshot.tags}
    for key in ("areas", "projects", "headings", "tasks", "tags"):
        for row in payload[key]:
            assert labels[row["title"]] == titles[row["id"]]
    answer = " / ".join(t["title"] for t in payload["tasks"])
    result = decode_text(answer, labels)
    assert result.unmatched == ()
    assert result.replaced == len(payload["tasks"])


def test_strict_prompt_has_no_stored_text(fixture_db):
    text = fold(build_prompt(payload_of(fixture_db, "strict")).text)
    template = fold(load_template())
    titles = [t.title for t in snapshot_of(fixture_db).tasks]
    leaked = [t for t in titles if fold(t).strip() in text]
    assert [t for t in leaked if fold(t).strip() not in template] == []


# --- the revised template ----

TEMPLATE_RULES = (
    '1. **Start here.** Begin your answer with a section called "Start here": the '
    "five most important actions, in order.",
    "3. **Full names, always.** Refer to every item by its complete name exactly "
    "as given in the data, in text and in tables.",
    "4. **One item per row.** In every table, put one item per row and never "
    "several items in one cell.",
    "5. **Everything in this answer.** Do not refer to downloads, CSV ledgers, "
    "spreadsheets or attachments.",
    "6. **Use only numbers from the data.** When you calculate something (a rate, "
    "days left, a share), show the calculation in brackets.",
    "7. **Only what is here.** Use only this prompt and the data.",
    "8. **Keep it short.** Aim for under 4,000 words in total.",
)


@pytest.mark.parametrize("rule", TEMPLATE_RULES)
def test_template_rules_reach_the_prompt(fixture_db, rule):
    assert rule in load_template()
    assert rule in build_prompt(payload_of(fixture_db, "strict")).text


def test_template_describes_this_payload():
    template = load_template()
    for key in ("summary", "checks_run", "data_read_warnings", "in_trashed_project"):
        assert f"`{key}`" in template
