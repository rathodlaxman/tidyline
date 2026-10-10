"""Deterministic builder for a SYNTHETIC Things-style database.

Everything here is invented. The database is built from tests/fixtures/schema.sql
(DDL only) and never reads a real Things database. All relative dates are
computed from the ``today`` argument, so the output is identical for the same
``today``.

VERIFIED against a real database (DESIGN.md 7.1, 7.2 and 11; recorded there
without personal values):

 V1. Template row shape. This builder still gives templates type 0, status 0,
     start 2 and no startDate; I have not re-checked that wording against the
     design doc beyond its "verified" note.
 V2. Real recurrence rules also carry ia (float), sr (float), rc (int),
     rrv (int, 4), ts (int) and usually ed (float). Every rule here has them.
 V3. Daily rules use of = [{"dy": 0}]. Weekly rules use wd 0, 5 and 6. Monthly
     rules use dy 0, 4, 13, 14 and the ordinal form [{"wd", "wdo"}]. Yearly rules
     use [{"dy", "mo"}]. Offsets are zero-based.
 V4. This Evening is an open to-do with start 1, startBucket 1 and a start date
     of today. Every other row has startBucket 0. things.py ignores startBucket,
     so such a task still appears in things.today().

 V5. Rules are XML plists, verified on a real database; binary plists are also
     accepted. The fixture writes XML, except BINARY_RULE_KEYS (binary).

UNVERIFIED (invented or assumed; revisit against real data):

 U1. dy = -1 (last day of the month) has never been seen in real data.
 U2. wdo: 1 to 4 = first to fourth, -1 = last. Only 1 and -1 were seen.
 U3. ed: a value at or above 6.0e10 means "never ends"; 64092211200.0 is used
     as that sentinel and its unit is unknown. A missing ed means no end date.
     An ordinary ed is treated as an end date, built here as Unix seconds.
 U4. rt1_instanceCreationPaused = 1 means paused (0 otherwise).
 U5. rc and ts have unknown meaning; the values 12 and -7 are invented.
 U6. An evening task with a past date, or inside a Someday project, is not
     covered because it has not been seen.
 U7. The "not a valid plist" blob and the unknown unit fu = 999 are invented
     error cases, as is the extra key `zz`.

TAKEN FROM things.py source or the schema, not independently verified:

 1. TMTask.type: 0 to-do, 1 project, 2 heading. TMTask.status: 0 open,
    2 cancelled, 3 completed. TMTask.start: 0 Inbox, 1 Anytime, 2 Someday.
    Upcoming is Someday with a future startDate (`upcoming()`).
 2. A to-do under a heading has `heading` set and `project` NULL; the heading
    row carries the `project`. A to-do directly in a project has `project` set
    and `heading` NULL. In an area, `area` is set; unfiled rows have all three
    NULL.
 3. Open projects and headings use status 0 and trashed 0. A Someday project is
    a project with start = 2.
 4. A to-do inside a trashed project has trashed = 0; only its context is
    trashed. A leftover template is one whose `project` is a trashed project; a
    deleted recurring task is a template with trashed = 1 and is not a leftover.
 5. Visible instances have rt1_recurrenceRule NULL and rt1_repeatingTemplate set
    to the template uuid. rt1_instanceCreationStartDate and
    rt1_nextInstanceStartDate on templates are packed dates with invented values.
 6. deadlineSuppressionDate is a packed date when the deadline is suppressed
    (things.py only tests for NULL / not NULL).
 7. Timestamps are Unix seconds in UTC, built from `today` at 09:00 UTC.
 8. Counter columns and cachedTags are left NULL; things.py does not read them.
 9. Tags link through TMTaskTag(tasks, tags). Checklist status uses the same
    0 / 2 / 3 codes as tasks.
10. TMSettings is left empty, so no URL-scheme auth token exists in the fixture.
11. The `sqlite_sequence` CREATE statement in schema.sql is skipped because
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

NEVER_ENDS = 64092211200.0  # unverified sentinel for "no end date" (U3)
END_DATE = "END_DATE"  # placeholder replaced by a date computed from `today`
DROP_ED = "DROP_ED"  # placeholder: leave the ed key out

# fu: 16 day, 256 week, 8 month, 4 year. tp: 0 fixed, 1 after completion.
# (key, title, area, fu, fa, tp, of, overrides). A key beginning "tpl_" is a
# template row; every one of them gets a rule blob.
RULE_SPECS = (
    ("tpl_daily", "Take out the recycling", "area_home", 16, 1, 0, [{"dy": 0}], {}),
    ("tpl_weekly_sun", "Plan the week ahead", "area_home", 256, 1, 0, [{"wd": 0}], {}),
    (
        "tpl_weekly_fri",
        "Water the balcony herbs",
        "area_home",
        256,
        1,
        0,
        [{"wd": 5}],
        {},
    ),
    (
        "tpl_weekly_sat",
        "Check the tyre pressure",
        "area_studio",
        256,
        1,
        0,
        [{"wd": 6}],
        {},
    ),
    ("tpl_biweekly_sun", "Wash the bedding", "area_home", 256, 2, 0, [{"wd": 0}], {}),
    (
        "tpl_monthly_first",
        "Review the budget sheet",
        "area_studio",
        8,
        1,
        0,
        [{"dy": 0}],
        {},
    ),
    ("tpl_monthly_15", "Pay the rent", "area_home", 8, 1, 0, [{"dy": 14}], {}),
    # dy = -1 has not been seen in real data (U1)
    (
        "tpl_monthly_last",
        "Back up the laptop",
        "area_studio",
        8,
        1,
        0,
        [{"dy": -1}],
        {},
    ),
    ("tpl_every3_months", "Clean the oven", "area_home", 8, 3, 0, [{"dy": 4}], {}),
    (
        "tpl_every6_months",
        "Service the bicycle",
        "area_home",
        8,
        6,
        0,
        [{"dy": 13}],
        {},
    ),
    (
        "tpl_monthly_first_sun",
        "Call the family",
        "area_home",
        8,
        1,
        0,
        [{"wd": 0, "wdo": 1}],
        {},
    ),
    (
        "tpl_monthly_last_sun",
        "Tidy the workshop",
        "area_studio",
        8,
        1,
        0,
        [{"wd": 0, "wdo": -1}],
        {},
    ),
    (
        "tpl_yearly_feb28",
        "Renew the domain name",
        "area_studio",
        4,
        1,
        0,
        [{"dy": 27, "mo": 1}],
        {},
    ),
    (
        "tpl_yearly_jan1",
        "Set the year's goals",
        "area_home",
        4,
        1,
        0,
        [{"dy": 0, "mo": 0}],
        {},
    ),
    (
        "tpl_after_completion",
        "Descale the kettle",
        "area_home",
        4,
        1,
        1,
        [{"dy": 0, "mo": 7}],
        {},
    ),
    # Rule variants
    (
        "tpl_no_ed",
        "Rotate the pantry stock",
        "area_home",
        256,
        1,
        0,
        [{"wd": 0}],
        {"ed": DROP_ED},
    ),
    (
        "tpl_end_date",
        "Send the course invoice",
        "area_studio",
        8,
        1,
        0,
        [{"dy": 0}],
        {"ed": END_DATE},
    ),
    (
        "tpl_repeat_count",
        "Practise the scales",
        "area_studio",
        256,
        1,
        0,
        [{"wd": 6}],
        {"rc": 12},
    ),
    (
        "tpl_lead_time",
        "Order printer ink",
        "area_studio",
        8,
        1,
        0,
        [{"dy": 13}],
        {"ts": -7},
    ),
    (
        "tpl_rrv5",
        "Check the smoke alarms",
        "area_home",
        8,
        1,
        0,
        [{"dy": 0}],
        {"rrv": 5},
    ),
    (
        "tpl_unknown_unit",
        "Empty the dehumidifier",
        "area_home",
        999,
        1,
        0,
        [{"dy": 0}],
        {},
    ),
    (
        "tpl_extra_key",
        "Review the garden plan",
        "area_home",
        256,
        1,
        0,
        [{"wd": 0}],
        {"zz": 1},
    ),
    # Template row variants
    ("tpl_paused", "Mow the lawn", "area_home", 256, 1, 0, [{"wd": 6}], {}),
    ("tpl_trashed", "Defrost the freezer", "area_home", 8, 1, 0, [{"dy": 13}], {}),
    ("tpl_leftover", "Send the newsletter", None, 8, 1, 0, [{"dy": 0}], {}),
)
BINARY_RULE_KEYS = frozenset({"tpl_weekly_fri"})  # the rest are written as XML
INVALID_RULE_KEY = "tpl_invalid_plist"
INVALID_RULE_BLOB = b"this is not a plist"
INVALID_RULE_TITLE = "Rinse the compost caddy"

# Templates that have a visible instance, and the instance's start date offset.
OPEN_INSTANCES = {"tpl_daily": 0, "tpl_weekly_sun": None, "tpl_monthly_15": None}
COMPLETED_INSTANCES = ("tpl_biweekly_sun", "tpl_yearly_feb28")

# Hand-derived from the rows below; the tests compare things.py against these.
# `today` is things.today(): Anytime with a start date, Someday with a past
# start date, and undated tasks with an unsuppressed overdue deadline. It
# includes the This Evening task, because things.py ignores startBucket.
FIXTURE_EXPECTATIONS = {
    "areas": 2,
    "projects": 5,  # open projects: not completed, not trashed
    # open, untrashed, not templates, context not trashed:
    # 25 ordinary tasks + 3 open instances + 1 This Evening task
    "open_todos": 29,
    "inbox": 1,
    "upcoming": 3,
    # Water the ferns, Renew library card, Take out the recycling (instance),
    # Read a chapter tonight (This Evening), Book wheel class, Send the invoice
    "today": 6,
}


def recurrence_rules(today: dt.date) -> dict[str, dict]:
    """The decoded rule for every template that has a valid plist, by key."""
    end = dt.datetime.combine(
        today + dt.timedelta(days=90), dt.time(0), tzinfo=dt.timezone.utc
    ).timestamp()
    rules = {}
    for number, (key, _t, _a, fu, fa, tp, offsets, overrides) in enumerate(RULE_SPECS):
        rule = {
            "fu": fu,
            "fa": fa,
            "tp": tp,
            "of": offsets,
            "ia": 700000000.0 + 86400.0 * number,  # invented
            "sr": 700000000.0 + 86400.0 * number + 3600.0,  # invented
            "rc": 0,
            "rrv": 4,
            "ts": 0,
            "ed": NEVER_ENDS,
        }
        for name, value in overrides.items():
            if value == DROP_ED:
                del rule[name]
            else:
                rule[name] = float(end) if value == END_DATE else value
        rules[key] = rule
    return rules


def rule_blobs(today: dt.date) -> dict[str, bytes]:
    """The raw rt1_recurrenceRule bytes for every template, including the bad one."""
    blobs = {
        key: rule_bytes(rule, binary=key in BINARY_RULE_KEYS)
        for key, rule in recurrence_rules(today).items()
    }
    blobs[INVALID_RULE_KEY] = INVALID_RULE_BLOB
    return blobs


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


def rule_bytes(rule: dict, binary: bool = False) -> bytes:
    fmt = plistlib.FMT_BINARY if binary else plistlib.FMT_XML
    return plistlib.dumps(rule, fmt=fmt)


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
                "startBucket": 0,
            }
            for name in ("area", "project", "heading", "rt1_repeatingTemplate"):
                if fields.get(name):
                    fields[name] = make_uuid(fields[name])
            row.update(fields)
            _insert(conn, "TMTask", row)

        def project(key, title, **fields):
            task_row(key, title, 1, **fields)

        def heading(key, title, project_key, **fields):
            task_row(key, title, 2, project=project_key, **fields)

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
        # A completed heading inside a completed project; its only child is
        # completed too (t_in_done_project, below).
        heading("head_done", "Boxes", "proj_done", status=3, stopDate=stamp(40))

        # Inbox, Today, Upcoming, deadlines -----------------------------
        todo("t_inbox", "Call the plumber", start=0)
        todo("t_today", "Water the ferns", area="area_home", startDate=day(0))
        todo(
            "t_evening",
            "Read a chapter tonight",
            area="area_home",
            startDate=day(0),
            startBucket=1,  # This Evening; things.py ignores this column
        )
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
        # Untidy titles for title_hygiene: a doubled space and a stray middle dot;
        # a leading space on t_portfolio below.
        todo("t_receipts", "Reconcile  receipts \u00b7", project="proj_admin_studio")

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
        todo("t_portfolio", " Update portfolio site", area="area_studio")
        todo("t_cables", "Sort the loose cables")
        # Needs NFKC: a full-width B, an fi ligature and a decomposed accent
        todo("t_card", "\uff22uy a \ufb01rst-birthday card for Zoe\u0301")

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
        todo("t_in_done_project", "Pack the kitchen", heading="head_done", status=3)
        todo("t_photos_done", "Sort 2019 folder", project="proj_photos", status=3)

        # Recurring templates (hidden) and visible instances --------------
        blobs = rule_blobs(today)
        template_rows = [(key, title, area) for key, title, area, *_ in RULE_SPECS]
        template_rows.append((INVALID_RULE_KEY, INVALID_RULE_TITLE, "area_home"))
        for key, title, area in template_rows:
            extras = {}
            if key == "tpl_paused":
                extras["rt1_instanceCreationPaused"] = 1
            if key == "tpl_trashed":
                extras["trashed"] = 1  # a deleted recurring task, not a leftover
            if key == "tpl_leftover":
                extras["project"] = "proj_trashed"
            row = {
                "start": 2,
                "rt1_recurrenceRule": blobs[key],
                "rt1_instanceCreationStartDate": day(-60),
                "rt1_nextInstanceStartDate": day(7),
                "rt1_instanceCreationPaused": 0,
                "rt1_instanceCreationCount": 3,
            }
            if area:
                row["area"] = area
            row.update(extras)
            todo(key, title, **row)

        titles = {key: title for key, title, _ in template_rows}
        areas = {key: area for key, _, area in template_rows}
        for key, offset in OPEN_INSTANCES.items():
            instance = {"area": areas[key], "rt1_repeatingTemplate": key}
            if offset is not None:
                instance["startDate"] = day(offset)
            todo(f"{key}:instance", titles[key], **instance)
        for key in COMPLETED_INSTANCES:
            todo(
                f"{key}:instance",
                titles[key],
                area=areas[key],
                rt1_repeatingTemplate=key,
                status=3,
            )

        conn.commit()
    finally:
        conn.close()

    return {
        key: make_uuid(key)
        for key in (
            *(spec[0] for spec in RULE_SPECS),
            INVALID_RULE_KEY,
            "area_home",
            "area_studio",
            "proj_admin_home",
            "proj_admin_studio",
        )
    }
