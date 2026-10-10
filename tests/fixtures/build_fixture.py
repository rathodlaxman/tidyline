"""Deterministic builder for a SYNTHETIC Things-style database.

Everything here is invented. The database is built from tests/fixtures/schema.sql
(DDL only) and never reads a real Things database. All relative dates are
computed from the ``today`` argument, so the output is identical for the same
``today``.

ASSUMPTIONS (column meanings that are not documented and that I could not
confirm from things.py or the schema; revisit them when the real database is
compared in step 8):

 1. TMTask.type: 0 to-do, 1 project, 2 heading (from things.py).
 2. TMTask.status: 0 open, 2 cancelled, 3 completed (from things.py).
 3. TMTask.start: 0 Inbox, 1 Anytime, 2 Someday (from things.py). Upcoming is
    Someday with a future startDate (from things.py `upcoming()`).
 4. A to-do under a heading has `heading` set and `project` NULL; the heading
    row carries the `project` (from the things.py comment and joins).
 5. A to-do directly in a project has `project` set and `heading` NULL. A
    project or to-do in an area has `area` set; unfiled rows have all three
    NULL.
 6. Open projects and headings use status 0 and trashed 0. A Someday project is
    a project with start = 2.
 7. A to-do inside a trashed project is not itself trashed (trashed = 0); only
    its context is. things.py documents this case.
 8. Recurring template rows (the hidden ones) have rt1_recurrenceRule set,
    type 0, status 0, trashed 0, start 2 and no startDate. things.py hides
    them only because rt1_recurrenceRule is not NULL; the other values are my
    guess. A leftover template is one whose `project` is a trashed project.
 9. Visible instances have rt1_recurrenceRule NULL and rt1_repeatingTemplate set
    to the template uuid. rt1_instanceCreationStartDate and
    rt1_nextInstanceStartDate on templates are packed dates; the values are
    invented.
10. Recurrence plist: a top-level dict with fu, fa, tp and `of`, where `of` is
    a list holding ONE dict of offsets (wd, dy, mo). I assume an empty dict
    for a daily rule. Offsets are zero-based as in DESIGN.md 7.2, so "day 15"
    is dy = 14 and "Feb 28" is mo = 1, dy = 27. Real rules carry more keys
    that DESIGN.md does not document; none are invented here. The
    "unrecognised" rule adds one made-up top-level key, `zz`.
11. deadlineSuppressionDate is a packed date when the deadline is suppressed
    (things.py only tests for NULL / not NULL).
12. Timestamps (creationDate, userModificationDate, stopDate) are Unix seconds
    in UTC (from things.py). They are built from `today` at 09:00 UTC.
13. Counter columns (untrashedLeafActionsCount, checklistItemsCount, ...) and
    cachedTags are left NULL; the real app maintains them and things.py does
    not read them.
14. Tags live in TMTag and link through TMTaskTag(tasks, tags). Checklist
    status uses the same 0 / 2 / 3 codes as tasks (from things.py).
15. This Evening is NOT in the fixture. The schema has `startBucket` but
    nothing in the schema or things.py says what its values mean (DESIGN.md 11
    lists this as still to verify).
16. TMSettings is left empty, so no URL-scheme auth token exists in the fixture.
17. The `sqlite_sequence` CREATE statement in schema.sql is skipped because
    SQLite creates that table itself for AUTOINCREMENT columns.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import plistlib
import re
import sqlite3
from pathlib import Path

SCHEMA_PATH = Path(__file__).with_name("schema.sql")
DATABASE_VERSION = 29

# fu: 16 day, 256 week, 8 month, 4 year. tp: 0 fixed, 1 after completion.
RECURRENCE_RULES: dict[str, dict] = {
    "tpl_daily": {"fu": 16, "fa": 1, "tp": 0, "of": [{}]},
    "tpl_weekly_sun": {"fu": 256, "fa": 1, "tp": 0, "of": [{"wd": 0}]},
    "tpl_biweekly_sun": {"fu": 256, "fa": 2, "tp": 0, "of": [{"wd": 0}]},
    "tpl_monthly_15": {"fu": 8, "fa": 1, "tp": 0, "of": [{"dy": 14}]},
    "tpl_monthly_last": {"fu": 8, "fa": 1, "tp": 0, "of": [{"dy": -1}]},
    "tpl_yearly_feb28": {"fu": 4, "fa": 1, "tp": 0, "of": [{"mo": 1, "dy": 27}]},
    "tpl_after_completion": {"fu": 4, "fa": 1, "tp": 1, "of": [{"mo": 7, "dy": 0}]},
    "tpl_unrecognised": {"fu": 256, "fa": 1, "tp": 0, "of": [{"wd": 0}], "zz": 1},
    "tpl_leftover": {"fu": 8, "fa": 1, "tp": 0, "of": [{"dy": 0}]},
}

# Hand-derived from the rows below; the tests compare things.py against these.
# `today` is things.today(): Anytime with a start date, Someday with a past
# start date, and undated tasks with an unsuppressed overdue deadline.
FIXTURE_EXPECTATIONS = {
    "areas": 2,
    "projects": 5,  # open projects: not completed, not trashed
    "open_todos": 33,  # open, untrashed, not templates, context not trashed
    "inbox": 1,
    "upcoming": 3,
    "today": 5,
}


def pack_date(day: dt.date) -> int:
    """Pack a date as Things stores it: year << 16 | month << 12 | day << 7."""
    return day.year << 16 | day.month << 12 | day.day << 7


def make_uuid(key: str) -> str:
    """Stable 22-character base62 id derived from a readable key."""
    alphabet = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
    number = int.from_bytes(hashlib.sha256(f"tidyline:{key}".encode()).digest(), "big")
    chars = []
    for _ in range(22):
        number, rest = divmod(number, 62)
        chars.append(alphabet[rest])
    return "".join(chars)


def rule_bytes(rule: dict) -> bytes:
    return plistlib.dumps(rule, fmt=plistlib.FMT_BINARY)


def _insert(conn: sqlite3.Connection, table: str, row: dict) -> None:
    columns = ", ".join(f'"{name}"' for name in row)
    marks = ", ".join("?" for _ in row)
    conn.execute(
        f"INSERT INTO {table} ({columns}) VALUES ({marks})", list(row.values())
    )


def _load_schema(conn: sqlite3.Connection) -> None:
    ddl = SCHEMA_PATH.read_text(encoding="utf-8")
    ddl = re.sub(r"^CREATE TABLE sqlite_sequence\(name,seq\);\n", "", ddl, flags=re.M)
    conn.executescript(ddl)


def build_fixture(path: Path, today: dt.date) -> dict[str, str]:
    """Write the synthetic database to ``path`` and return {key: uuid}."""
    path = Path(path)
    if path.exists():
        path.unlink()

    def day(offset: int) -> int:
        return pack_date(today + dt.timedelta(days=offset))

    base = dt.datetime.combine(today, dt.time(9), tzinfo=dt.timezone.utc).timestamp()

    def stamp(days_ago: int = 0) -> float:
        return base - days_ago * 86400

    counter = {"index": 0}

    def next_index() -> int:
        counter["index"] += 1
        return counter["index"]

    conn = sqlite3.connect(path)
    try:
        _load_schema(conn)
        _insert(
            conn,
            "Meta",
            {
                "key": "databaseVersion",
                "value": plistlib.dumps(
                    DATABASE_VERSION, fmt=plistlib.FMT_XML
                ).decode(),
            },
        )

        # Areas ---------------------------------------------------------
        for key, title in (("area_home", "Household"), ("area_studio", "Side Studio")):
            _insert(
                conn,
                "TMArea",
                {
                    "uuid": make_uuid(key),
                    "title": title,
                    "visible": 1,
                    "index": next_index(),
                },
            )

        # Tags ----------------------------------------------------------
        for key, title in (("tag_errand", "errand"), ("tag_waiting", "waiting")):
            _insert(
                conn,
                "TMTag",
                {"uuid": make_uuid(key), "title": title, "index": next_index()},
            )

        def task_row(key: str, title: str, type_: int, **fields) -> None:
            row = {
                "uuid": make_uuid(key),
                "leavesTombstone": 1,
                "creationDate": stamp(30),
                "userModificationDate": stamp(1),
                "type": type_,
                "status": 0,
                "trashed": 0,
                "title": title,
                "start": 1,
                "index": next_index(),
                "todayIndex": 0,
            }
            for name in ("area", "project", "heading", "rt1_repeatingTemplate"):
                if fields.get(name):
                    fields[name] = make_uuid(fields[name])
            row.update(fields)
            _insert(conn, "TMTask", row)

        def project(key, title, **fields):
            task_row(key, title, 1, **fields)

        def heading(key, title, project_key):
            task_row(key, title, 2, project=project_key)

        def todo(key, title, *, tags=(), checklist=(), **fields):
            if fields.get("status") in (2, 3):
                fields.setdefault("stopDate", stamp(2))
            task_row(key, title, 0, **fields)
            for tag in tags:
                _insert(
                    conn,
                    "TMTaskTag",
                    {"tasks": make_uuid(key), "tags": make_uuid(tag)},
                )
            for position, (item, status) in enumerate(checklist):
                _insert(
                    conn,
                    "TMChecklistItem",
                    {
                        "uuid": make_uuid(f"{key}:check:{position}"),
                        "userModificationDate": stamp(1),
                        "creationDate": stamp(30),
                        "title": item,
                        "status": status,
                        "stopDate": stamp(2) if status == 3 else None,
                        "index": position,
                        "task": make_uuid(key),
                        "leavesTombstone": 1,
                    },
                )

        # Projects and headings ----------------------------------------
        project("proj_admin_home", "Admin", area="area_home")
        project("proj_admin_studio", "Admin", area="area_studio")
        project("proj_garden", "Garden Shed Rebuild", area="area_home")
        heading("head_plan", "Planning", "proj_garden")
        heading("head_build", "Build", "proj_garden")
        project("proj_pottery", "Learn Pottery", area="area_studio", start=2)
        project("proj_photos", "Photo Archive Cleanup", area="area_studio")
        project("proj_trashed", "Old Newsletter", area="area_studio", trashed=1)
        project(
            "proj_done",
            "Spring Move",
            area="area_home",
            status=3,
            stopDate=stamp(40),
        )

        # Inbox, Today, Upcoming, deadlines -----------------------------
        todo("t_inbox", "Call the plumber", start=0)
        todo("t_today", "Water the ferns", area="area_home", startDate=day(0))
        todo(
            "t_yesterday",
            "Renew library card",
            project="proj_admin_home",
            startDate=day(-1),
        )
        todo(
            "t_nextweek",
            "Book dentist visit",
            area="area_home",
            start=2,
            startDate=day(7),
            notes="Ask about the evening slots. Bring the insurance card.",
            checklist=(
                ("Find the insurance card", 3),
                ("Check opening hours", 0),
                ("Pick a date", 0),
            ),
        )
        todo(
            "t_overdue",
            "Send the invoice",
            project="proj_admin_studio",
            deadline=day(-5),
        )
        todo(
            "t_suppressed",
            "File the warranty claim",
            project="proj_admin_studio",
            deadline=day(-3),
            deadlineSuppressionDate=day(0),
        )

        # Duplicate titles (differ only by case and punctuation) ---------
        todo("t_dup_a", "Pay the electricity bill", project="proj_admin_home")
        todo("t_dup_b", "pay the electricity bill.", project="proj_admin_studio")
        todo("t_council", "Check council tax bill", project="proj_admin_home")
        todo("t_receipts", "Reconcile receipts", project="proj_admin_studio")

        # Project with headings -----------------------------------------
        todo(
            "t_measure",
            "Measure the plot",
            heading="head_plan",
            notes="Use the 5 m tape; write sizes on the back of the plan.",
            tags=("tag_errand", "tag_waiting"),
            checklist=(("Front edge", 0), ("Back edge", 0)),
        )
        todo("t_timber", "Price out timber", heading="head_plan")
        todo("t_bolts", "Order bolts", heading="head_build")
        todo("t_level", "Buy a spirit level", project="proj_garden")
        todo(
            "t_door",
            "Paint the shed door",
            project="proj_garden",
            start=2,
        )  # Someday task inside an active project

        # Someday project whose tasks carry start dates ------------------
        todo(
            "t_clay",
            "Buy clay",
            project="proj_pottery",
            start=2,
            startDate=day(12),
        )
        todo(
            "t_glaze",
            "Choose a glaze palette",
            project="proj_pottery",
            start=2,
            startDate=day(30),
        )
        todo(
            "t_wheel",
            "Book wheel class",
            project="proj_pottery",
            start=2,
            startDate=day(-10),
        )  # things.today() ignores the parent Someday project

        # Area-level and unfiled tasks ----------------------------------
        todo("t_lease", "Renew the lease", area="area_home")
        todo("t_portfolio", "Update portfolio site", area="area_studio")
        todo("t_cables", "Sort the loose cables")
        todo("t_card", "Buy birthday card")

        # Non-English titles --------------------------------------------
        todo(
            "t_es",
            "Comprar pimentón y azafrán",
            area="area_home",
            notes="Mercado del sábado: ¿hay también cúrcuma?",
            tags=("tag_errand",),
        )
        todo("t_de", "Müll rausbringen und Gelbe Säcke holen")
        todo("t_ja", "請求書の写真を整理する", area="area_studio")

        # Completed, cancelled and trashed (never counted as open) -------
        todo("t_done", "Hang the curtains", area="area_home", status=3)
        todo("t_cancelled", "Replace the doorbell", area="area_home", status=2)
        todo("t_trashed", "Throw away the old paint", area="area_home", trashed=1)
        todo(
            "t_in_trashed_project",
            "Draft newsletter issue 3",
            project="proj_trashed",
        )
        todo("t_in_done_project", "Pack the kitchen", project="proj_done", status=3)
        todo("t_photos_done", "Sort 2019 folder", project="proj_photos", status=3)

        # Recurring templates (hidden) and visible instances --------------
        templates = (
            ("tpl_daily", "Take out the recycling", "area_home", day(0)),
            ("tpl_weekly_sun", "Plan the week ahead", "area_home", None),
            ("tpl_biweekly_sun", "Wash the bedding", "area_home", None),
            ("tpl_monthly_15", "Pay the rent", "area_home", None),
            ("tpl_monthly_last", "Back up the laptop", "area_studio", None),
            ("tpl_yearly_feb28", "Renew the domain name", "area_studio", None),
            ("tpl_after_completion", "Descale the kettle", "area_home", None),
            ("tpl_unrecognised", "Review the garden plan", "area_home", None),
        )
        for key, title, area, instance_date in templates:
            todo(
                key,
                title,
                area=area,
                start=2,
                rt1_recurrenceRule=rule_bytes(RECURRENCE_RULES[key]),
                rt1_instanceCreationStartDate=day(-60),
                rt1_nextInstanceStartDate=day(7),
                rt1_instanceCreationPaused=0,
                rt1_instanceCreationCount=3,
            )
            instance = {"area": area, "rt1_repeatingTemplate": key}
            if instance_date is not None:
                instance["startDate"] = instance_date
            todo(f"{key}:instance", title, **instance)
        todo(
            "tpl_leftover",
            "Send the newsletter",
            project="proj_trashed",
            start=2,
            rt1_recurrenceRule=rule_bytes(RECURRENCE_RULES["tpl_leftover"]),
            rt1_instanceCreationStartDate=day(-90),
            rt1_instanceCreationPaused=0,
            rt1_instanceCreationCount=1,
        )

        conn.commit()
    finally:
        conn.close()

    return {
        key: make_uuid(key)
        for key in (
            *RECURRENCE_RULES,
            "area_home",
            "area_studio",
            "proj_admin_home",
            "proj_admin_studio",
        )
    }
