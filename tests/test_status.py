import datetime as dt
import inspect
import re
import sqlite3

import pytest
from fixtures import build_fixture as bf

from tidyline import dates, model, status
from tidyline.model import Task, TaskKind
from tidyline.status import Status, effective_status

TODAY = dt.date(2026, 10, 10)
DAY = dt.timedelta(days=1)
KINDS = {0: TaskKind.TODO, 1: TaskKind.PROJECT, 2: TaskKind.HEADING}


def task(**fields):
    fields.setdefault("uuid", "t")
    fields.setdefault("kind", TaskKind.TODO)
    fields.setdefault("title", "A task")
    return Task(**fields)


def someday_project():
    return task(uuid="p", kind=TaskKind.PROJECT, start=model.START_SOMEDAY)


def active_project():
    return task(uuid="p", kind=TaskKind.PROJECT, start=model.START_ANYTIME)


# --- fixture rows, turned into Tasks without read.py -------------------------


@pytest.fixture
def fixture_tasks(fixture_db):
    """{uuid: Task} for every TMTask row, built straight from the fixture."""
    conn = sqlite3.connect(fixture_db)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("SELECT * FROM TMTask").fetchall()
    finally:
        conn.close()
    tasks = {}
    for row in rows:
        tasks[row["uuid"]] = Task(
            uuid=row["uuid"],
            kind=KINDS[row["type"]],
            title=row["title"],
            status=row["status"],
            trashed=bool(row["trashed"]),
            start=row["start"],
            start_date=dates.unpack_date(row["startDate"]),
            start_bucket=row["startBucket"],
            deadline=dates.unpack_date(row["deadline"]),
            deadline_suppression_date=dates.unpack_date(row["deadlineSuppressionDate"]),
            area_uuid=row["area"],
            project_uuid=row["project"],
            heading_uuid=row["heading"],
        )
    return tasks


def fixture_status(tasks, key, today=TODAY):
    item = tasks[bf.make_uuid(key)]
    owner = item.project_uuid
    if item.heading_uuid:
        owner = tasks[item.heading_uuid].project_uuid
    parent = tasks.get(owner) if owner else None
    return effective_status(item, parent, today)


# --- step 0: closed or trashed ----------------------------------------------


def test_step0_completed_cancelled_and_trashed_are_closed(fixture_tasks):
    for key in ("t_done", "t_cancelled", "t_trashed", "t_in_done_project"):
        assert fixture_status(fixture_tasks, key) is Status.CLOSED, key


@pytest.mark.parametrize("status_code", [2, 3])
def test_step0_beats_every_other_rule(status_code):
    busy = task(
        status=status_code,
        start=model.START_INBOX,
        start_date=TODAY,
        start_bucket=1,
        deadline=TODAY - DAY,
    )
    assert effective_status(busy, someday_project(), TODAY) is Status.CLOSED
    assert effective_status(task(trashed=True, start=0), None, TODAY) is Status.CLOSED


def test_step0_task_in_a_trashed_project_is_not_itself_closed(fixture_tasks):
    # Only the project is trashed (fixture assumption 4); the rules do not look
    # at the parent's trashed flag.
    assert fixture_status(fixture_tasks, "t_in_trashed_project") is Status.ANYTIME


# --- rule 1: Inbox ----------------------------------------------------------


def test_rule1_inbox(fixture_tasks):
    assert fixture_status(fixture_tasks, "t_inbox") is Status.INBOX


def test_rule1_beats_dates_and_someday_parent():
    inbox = task(start=model.START_INBOX, start_date=TODAY - DAY, deadline=TODAY)
    assert effective_status(inbox, someday_project(), TODAY) is Status.INBOX


# --- rule 2: parent project is Someday ---------------------------------------


def test_rule2_someday_project_wins_over_a_future_start_date(fixture_tasks):
    assert fixture_status(fixture_tasks, "t_clay") is Status.SOMEDAY
    assert fixture_status(fixture_tasks, "t_glaze") is Status.SOMEDAY


def test_rule2_someday_project_wins_over_a_past_start_date(fixture_tasks):
    # things.today() would list this task; the app keeps it hidden.
    assert fixture_status(fixture_tasks, "t_wheel") is Status.SOMEDAY


def test_rule2_wins_over_today_this_evening_and_deadline():
    parent = someday_project()
    for fields in (
        {"start_date": TODAY},
        {"start_date": TODAY, "start_bucket": 1},
        {"deadline": TODAY - DAY},
        {"start_date": TODAY + DAY},
    ):
        assert effective_status(task(**fields), parent, TODAY) is Status.SOMEDAY


def test_rule2_applies_to_an_anytime_task_with_no_dates():
    assert effective_status(task(), someday_project(), TODAY) is Status.SOMEDAY


def test_rule2_not_triggered_by_an_active_project():
    assert effective_status(task(), active_project(), TODAY) is Status.ANYTIME


# --- rule 3: start date after today ------------------------------------------


def test_rule3_upcoming(fixture_tasks):
    assert fixture_status(fixture_tasks, "t_nextweek") is Status.UPCOMING


def test_rule3_tomorrow_is_upcoming_and_today_is_not():
    assert (
        effective_status(task(start_date=TODAY + DAY), None, TODAY) is Status.UPCOMING
    )
    assert effective_status(task(start_date=TODAY), None, TODAY) is Status.TODAY


def test_rule3_applies_to_anytime_and_someday_tasks_alike():
    for start in (model.START_ANYTIME, model.START_SOMEDAY):
        future = task(start=start, start_date=TODAY + DAY)
        assert effective_status(future, None, TODAY) is Status.UPCOMING


def test_rule3_beats_a_deadline_that_is_due():
    item = task(start_date=TODAY + DAY, deadline=TODAY - DAY)
    assert effective_status(item, None, TODAY) is Status.UPCOMING


# --- rule 4: start date today or earlier -------------------------------------


def test_rule4_today(fixture_tasks):
    assert fixture_status(fixture_tasks, "t_today") is Status.TODAY
    assert fixture_status(fixture_tasks, "t_yesterday") is Status.TODAY


def test_rule4_this_evening(fixture_tasks):
    # start = 1, startBucket = 1, start date today
    assert fixture_status(fixture_tasks, "t_evening") is Status.THIS_EVENING
    evening = fixture_tasks[bf.make_uuid("t_evening")]
    assert (evening.start, evening.start_bucket, evening.start_date) == (1, 1, TODAY)


def test_rule4_this_evening_with_a_past_date():
    item = task(start_date=TODAY - 3 * DAY, start_bucket=1)
    assert effective_status(item, None, TODAY) is Status.THIS_EVENING


def test_rule4_someday_task_with_a_past_start_date_is_today():
    item = task(start=model.START_SOMEDAY, start_date=TODAY - 10 * DAY)
    assert effective_status(item, None, TODAY) is Status.TODAY
    item = task(start=model.START_SOMEDAY, start_date=TODAY - 10 * DAY, start_bucket=1)
    assert effective_status(item, None, TODAY) is Status.THIS_EVENING


def test_rule4_other_bucket_values_are_not_this_evening():
    assert effective_status(task(start_date=TODAY, start_bucket=0), None, TODAY) is (
        Status.TODAY
    )
    assert effective_status(task(start_date=TODAY, start_bucket=2), None, TODAY) is (
        Status.TODAY
    )


# --- rule 5: overdue deadline, no start date ---------------------------------
# Rule 5 is untested on real data (DESIGN 7.1): these tests cover the fixture
# and constructed tasks only.


def test_rule5_overdue_deadline(fixture_tasks):
    assert fixture_status(fixture_tasks, "t_overdue") is Status.TODAY


def test_rule5_deadline_today_counts():
    assert effective_status(task(deadline=TODAY), None, TODAY) is Status.TODAY


def test_rule5_future_deadline_does_not_count():
    assert effective_status(task(deadline=TODAY + DAY), None, TODAY) is Status.ANYTIME


def test_rule5_suppressed_deadline_does_not_count(fixture_tasks):
    suppressed = fixture_tasks[bf.make_uuid("t_suppressed")]
    assert suppressed.deadline == TODAY - 3 * DAY
    assert suppressed.deadline_suppression_date == TODAY
    assert fixture_status(fixture_tasks, "t_suppressed") is Status.ANYTIME


def test_rule5_needs_no_start_date():
    item = task(deadline=TODAY - DAY, start_date=TODAY - 2 * DAY)
    assert effective_status(item, None, TODAY) is Status.TODAY  # via rule 4
    item = task(deadline=TODAY - DAY, start_date=TODAY + DAY)
    assert effective_status(item, None, TODAY) is Status.UPCOMING  # rule 3 first


def test_rule5_beats_rule6_for_a_someday_task():
    item = task(start=model.START_SOMEDAY, deadline=TODAY - DAY)
    assert effective_status(item, None, TODAY) is Status.TODAY


# --- rule 6: Someday ----------------------------------------------------------


def test_rule6_someday_task_in_an_active_project(fixture_tasks):
    assert fixture_status(fixture_tasks, "t_door") is Status.SOMEDAY


def test_rule6_someday_without_dates():
    assert effective_status(task(start=model.START_SOMEDAY), None, TODAY) is (
        Status.SOMEDAY
    )


def test_rule6_someday_project_itself_with_no_parent():
    assert effective_status(someday_project(), None, TODAY) is Status.SOMEDAY


# --- rule 7: Anytime ---------------------------------------------------------


def test_rule7_anytime(fixture_tasks):
    for key in ("t_level", "t_lease", "t_cables", "t_measure"):
        assert fixture_status(fixture_tasks, key) is Status.ANYTIME, key


# --- today is a parameter ------------------------------------------------------


def test_today_is_a_parameter():
    item = task(start_date=dt.date(2030, 6, 15))
    assert effective_status(item, None, dt.date(2030, 6, 14)) is Status.UPCOMING
    assert effective_status(item, None, dt.date(2030, 6, 15)) is Status.TODAY
    assert effective_status(item, None, dt.date(2031, 1, 1)) is Status.TODAY


def test_fixture_counts_by_status(fixture_tasks):
    """Open to-dos (not templates) by effective status, derived from the rules."""
    counts = {}
    for item in fixture_tasks.values():
        if item.kind is not TaskKind.TODO:
            continue
        if item.uuid in {bf.make_uuid(k) for k in (s[0] for s in bf.RULE_SPECS)}:
            continue
        owner = item.project_uuid
        if item.heading_uuid:
            owner = fixture_tasks[item.heading_uuid].project_uuid
        parent = fixture_tasks.get(owner) if owner else None
        result = effective_status(item, parent, TODAY)
        counts[result] = counts.get(result, 0) + 1
    assert counts[Status.INBOX] == 1
    assert counts[Status.THIS_EVENING] == 1
    # Water the ferns, Renew library card, Send the invoice, Take out the recycling
    assert counts[Status.TODAY] == 4
    assert counts[Status.UPCOMING] == 1
    # done, cancelled, trashed, two in closed projects, two completed instances
    assert counts[Status.CLOSED] == 7


def test_enum_values():
    assert {member.name for member in Status} == {
        "INBOX",
        "TODAY",
        "THIS_EVENING",
        "UPCOMING",
        "ANYTIME",
        "SOMEDAY",
        "CLOSED",
    }


# --- the new modules never read the clock or the network ---------------------

CLOCK = re.compile(r"\b(today|now|utcnow|time|monotonic)\s*\(|import (socket|time)\b")


@pytest.mark.parametrize("module", [dates, model, status])
def test_no_clock_reads(module):
    source = inspect.getsource(module)
    assert not CLOCK.search(source), module.__name__
    assert not re.search(r"^\s*(import|from) things\b", source, re.M)
