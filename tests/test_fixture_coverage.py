"""The synthetic fixture covers everything DESIGN.md section 9 lists for v0.1.

One test per item. A failure says which item the fixture is missing, so a
change to build_fixture.py cannot silently drop coverage.
"""

import datetime as dt
import json
import re
import unicodedata

import pytest
from fixtures import build_fixture as bf

from tidyline.db.snapshot import open_snapshot
from tidyline.model import START_SOMEDAY, STATUS_COMPLETED, Task, TaskKind
from tidyline.read import read_snapshot
from tidyline.recurrence import NOT_RECOGNISED_TEXT, UNREADABLE_TEXT
from tidyline.render.json_out import build_export
from tidyline.status import Status, effective_status

TODAY = dt.date(2026, 10, 10)
U = bf.make_uuid


@pytest.fixture
def snapshot(fixture_db):
    with open_snapshot(fixture_db) as copy:
        return read_snapshot(copy)


@pytest.fixture
def exported(snapshot):
    data = build_export(
        snapshot,
        today=TODAY,
        exported_at=dt.datetime(2026, 10, 10, 12, tzinfo=dt.timezone.utc),
        tool_version="test",
        environment={},
    )
    return json.loads(json.dumps(data, ensure_ascii=False))


def need(items, what):
    items = list(items)
    assert items, f"fixture is missing: {what}"
    return items


def is_live_todo(task: Task) -> bool:
    return task.status == 0 and not task.trashed


def status_of(snapshot, task: Task) -> Status:
    tasks = {t.uuid: t for t in snapshot.tasks}
    owner = task.project_uuid
    if owner is None and task.heading_uuid:
        owner = tasks[task.heading_uuid].project_uuid
    return effective_status(task, tasks.get(owner) if owner else None, TODAY)


# --- section 9 list ---------------------------------------------------------------


def test_headings(snapshot):
    headings = need(snapshot.headings, "headings")
    assert all(h.project_uuid for h in headings)
    children = [t for t in snapshot.todos if t.heading_uuid]
    need(children, "to-dos under a heading")


def test_area_level_tasks(snapshot):
    need(
        (
            t
            for t in snapshot.todos
            if is_live_todo(t)
            and t.area_uuid
            and not t.project_uuid
            and not t.heading_uuid
        ),
        "area-level tasks (an area, no project, no heading)",
    )


def test_unfiled_tasks(snapshot):
    need(
        (
            t
            for t in snapshot.todos
            if is_live_todo(t)
            and not (t.area_uuid or t.project_uuid or t.heading_uuid)
            and t.start != 0
        ),
        "unfiled open tasks (no area, no project, not in the Inbox)",
    )


def test_someday_project_with_dated_tasks(snapshot):
    someday = need(
        (p for p in snapshot.projects if p.start == START_SOMEDAY and p.status == 0),
        "a Someday project",
    )
    dated = [
        t
        for t in snapshot.todos
        if t.project_uuid in {p.uuid for p in someday} and t.start_date is not None
    ]
    need(dated, "dated tasks inside a Someday project")


def test_today_tasks(snapshot):
    need(
        (t for t in snapshot.todos if status_of(snapshot, t) is Status.TODAY),
        "Today tasks",
    )


def test_this_evening_tasks(snapshot):
    need(
        (t for t in snapshot.todos if status_of(snapshot, t) is Status.THIS_EVENING),
        "This Evening tasks",
    )


def test_overdue_deadline_task(snapshot):
    overdue = need(
        (
            t
            for t in snapshot.todos
            if is_live_todo(t)
            and t.deadline is not None
            and t.deadline < TODAY
            and t.start_date is None
            and not t.deadline_suppressed
        ),
        "an open task with an overdue deadline and no start date",
    )
    assert all(status_of(snapshot, t) is Status.TODAY for t in overdue)


def test_leftover_template(snapshot):
    need(snapshot.leftover_template_uuids, "a leftover recurring template")


def test_two_projects_with_the_same_title(snapshot):
    titles = [p.title for p in snapshot.projects]
    twins = {t for t in titles if titles.count(t) > 1}
    need(twins, "two projects with the same title")
    for title in twins:
        same = [p for p in snapshot.projects if p.title == title]
        assert len({p.uuid for p in same}) == len(same)


def test_non_latin_title(snapshot):
    def non_latin(text):
        return any(
            ord(c) > 0x24F and unicodedata.category(c).startswith("L") for c in text
        )

    need((t for t in snapshot.tasks if non_latin(t.title)), "a non-Latin title")


def test_title_needing_nfkc_normalisation(snapshot):
    need(
        (
            t
            for t in snapshot.tasks
            if unicodedata.normalize("NFKC", t.title) != t.title
        ),
        "a title that changes under NFKC",
    )


def test_accented_latin_titles(snapshot):
    need(
        (t for t in snapshot.tasks if re.search(r"[À-ÿ]", t.title)),
        "an accented Latin title",
    )


# --- every recurrence type in DESIGN 7.2 -------------------------------------------

RECURRENCE_TYPES = {
    "daily": lambda r: r.unit == "day" and r.interval == 1,
    "weekly": lambda r: r.unit == "week" and r.interval == 1,
    "every N weeks": lambda r: r.unit == "week" and (r.interval or 0) > 1,
    "monthly by day": lambda r: re.fullmatch(r"Monthly on day \d+.*", r.text),
    "monthly on the last day": lambda r: r.text.startswith("Monthly on last day"),
    "monthly on an ordinal weekday": lambda r: re.match(
        r"Monthly on the (first|second|third|fourth|last) \w+", r.text
    ),
    "every N months": lambda r: r.unit == "month" and (r.interval or 0) > 1,
    "yearly": lambda r: r.unit == "year" and not r.after_completion,
    "after completion": lambda r: r.after_completion,
    "ends after N times": lambda r: (r.repeat_limit or 0) > 0,
    "has an end date": lambda r: r.has_end_date,
    "starts N days before deadline": lambda r: r.start_days_before_deadline,
    "unreadable rule": lambda r: r.text == UNREADABLE_TEXT,
    "rule not recognised": lambda r: r.text == NOT_RECOGNISED_TEXT,
    "assumed convention": lambda r: r.confidence == "assumed",
    "unfamiliar field": lambda r: any("unfamiliar field" in n for n in r.notes),
}


@pytest.mark.parametrize("name", list(RECURRENCE_TYPES))
def test_recurrence_type(snapshot, name):
    rules = [t.recurrence for t in snapshot.templates]
    need((r for r in rules if RECURRENCE_TYPES[name](r)), f"recurrence type: {name}")


def test_paused_and_instance_cases(snapshot):
    need((t for t in snapshot.templates if t.recurrence_paused), "a paused template")
    need(snapshot.instances, "recurring instances")
    linked = {t.recurrence_template_uuid for t in snapshot.instances}
    unlinked = [t for t in snapshot.templates if t.uuid not in linked]
    need(unlinked, "a template with no instance")


# --- a completed project with a completed heading ----------------------------


def test_completed_heading_in_a_completed_project(snapshot):
    tasks = {t.uuid: t for t in snapshot.tasks}
    heading = tasks[U("head_done")]
    project = tasks[U("proj_done")]
    assert heading.kind is TaskKind.HEADING
    assert (heading.status, heading.project_uuid) == (STATUS_COMPLETED, project.uuid)
    assert (project.kind, project.status) == (TaskKind.PROJECT, STATUS_COMPLETED)
    children = need(
        (t for t in snapshot.tasks if t.heading_uuid == heading.uuid),
        "a child of the completed heading",
    )
    assert all(c.status == STATUS_COMPLETED for c in children)
    assert not any(t.project_uuid == heading.uuid for t in snapshot.tasks)


def test_completed_heading_is_in_the_export_with_status_and_project(exported):
    headings = {h["id"]: h for h in exported["headings"]}
    heading = headings[U("head_done")]
    assert heading["status"] == "completed"
    assert heading["status_code"] == 3
    assert heading["project"] == {"id": U("proj_done"), "title": "Spring Move"}
    assert heading["effective_status"] == "closed"
    assert heading["trashed"] is False
    assert heading["completion_date"] is not None


def test_completed_heading_is_not_open_anywhere(snapshot, exported):
    heading_id = U("head_done")
    everything = exported["projects"] + exported["headings"] + exported["tasks"]
    open_ids = {e["id"] for e in everything if e["effective_status"] != "closed"}
    assert heading_id not in open_ids
    in_heading = [
        t for t in exported["tasks"] if (t["heading"] or {}).get("id") == heading_id
    ]
    need(in_heading, "an exported to-do under the completed heading")
    assert all(
        t["status"] == "completed" and t["effective_status"] == "closed"
        for t in in_heading
    )
    assert {p["id"]: p["status"] for p in exported["projects"]}[U("proj_done")] == (
        "completed"
    )
    assert heading_id not in {t.uuid for t in snapshot.todos}
    assert not any(
        h["id"] == heading_id and h["status"] == "open" for h in exported["headings"]
    )
