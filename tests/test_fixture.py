import builtins
import datetime as dt
import plistlib
import sqlite3
from pathlib import Path

import pytest
import things
from fixtures import build_fixture as bf

FIXED_TODAY = dt.date(2026, 10, 10)


def pin_clock(database: things.Database, today: dt.date) -> None:
    """Make the SQL `date('now', 'localtime')` used by things.py return `today`.

    things.py reads the clock inside SQL, so without this the Today and Upcoming
    counts would change as real time passes.
    """
    reference = sqlite3.connect(":memory:")
    iso = today.isoformat()

    def pinned_date(*args):
        if args == ("now", "localtime"):
            return iso
        marks = ", ".join("?" for _ in args)
        return reference.execute(f"SELECT date({marks})", args).fetchone()[0]

    database.connection.create_function("date", -1, pinned_date)


@pytest.fixture
def built(tmp_path):
    path = tmp_path / "fixture.sqlite"
    ids = bf.build_fixture(path, FIXED_TODAY)
    return path, ids


@pytest.fixture
def database(built):
    path, _ = built
    db = things.Database(filepath=str(path))
    pin_clock(db, FIXED_TODAY)
    return db


def test_pack_date_matches_things_py():
    packed = bf.pack_date(dt.date(2021, 3, 28))
    assert packed == 132464128
    assert packed == things.database.isodate_to_yyyyyyyyyyymmmmddddd("2021-03-28")


def test_build_is_deterministic(tmp_path):
    first, second = tmp_path / "a.sqlite", tmp_path / "b.sqlite"
    bf.build_fixture(first, FIXED_TODAY)
    bf.build_fixture(second, FIXED_TODAY)

    def dump(path):
        conn = sqlite3.connect(path)
        try:
            return list(conn.iterdump())
        finally:
            conn.close()

    assert dump(first) == dump(second)


def test_dates_follow_today_argument(tmp_path):
    path = tmp_path / "later.sqlite"
    bf.build_fixture(path, dt.date(2030, 1, 31))
    conn = sqlite3.connect(path)
    try:
        (nextweek,) = conn.execute(
            "SELECT startDate FROM TMTask WHERE uuid = ?",
            (bf.make_uuid("t_nextweek"),),
        ).fetchone()
    finally:
        conn.close()
    assert nextweek == bf.pack_date(dt.date(2030, 2, 7))


def test_database_version_is_xml_plist_29(built):
    path, _ = built
    conn = sqlite3.connect(path)
    try:
        (value,) = conn.execute(
            "SELECT value FROM Meta WHERE key = 'databaseVersion'"
        ).fetchone()
        (tokens,) = conn.execute(
            "SELECT COUNT(uriSchemeAuthenticationToken) FROM TMSettings"
        ).fetchone()
    finally:
        conn.close()
    assert value.startswith("<?xml")
    assert plistlib.loads(value.encode()) == 29
    assert tokens == 0


def test_things_py_opens_fixture(database):
    assert database.get_version() == 29


def test_counts_match_expectations(database):
    expected = bf.FIXTURE_EXPECTATIONS
    assert things.areas(database=database, count_only=True) == expected["areas"]
    assert things.projects(database=database, count_only=True) == expected["projects"]
    assert (
        things.tasks(database=database, type="to-do", count_only=True)
        == expected["open_todos"]
    )
    assert things.inbox(database=database, count_only=True) == expected["inbox"]
    assert things.upcoming(database=database, count_only=True) == expected["upcoming"]
    assert len(things.today(database=database)) == expected["today"]


def test_today_contents(database):
    titles = {task["title"] for task in things.today(database=database)}
    assert titles == {
        "Water the ferns",
        "Renew library card",
        "Take out the recycling",
        "Book wheel class",
        "Send the invoice",
    }


def test_duplicate_project_names_and_headings(database):
    projects = things.projects(database=database)
    admins = [p for p in projects if p["title"] == "Admin"]
    assert len(admins) == 2
    assert {p["area_title"] for p in admins} == {"Household", "Side Studio"}
    headings = things.tasks(database=database, type="heading")
    assert {h["title"] for h in headings} == {"Planning", "Build"}
    under_heading = things.tasks(database=database, type="to-do", heading=True)
    assert {t["title"] for t in under_heading} == {
        "Measure the plot",
        "Price out timber",
        "Order bolts",
    }


def test_closed_and_trashed_items_are_not_open(database):
    titles = {t["title"] for t in things.tasks(database=database, type="to-do")}
    for hidden in (
        "Hang the curtains",
        "Replace the doorbell",
        "Throw away the old paint",
        "Draft newsletter issue 3",
        "Pack the kitchen",
        "Send the newsletter",
    ):
        assert hidden not in titles
    project_titles = {p["title"] for p in things.projects(database=database)}
    assert {"Old Newsletter", "Spring Move"}.isdisjoint(project_titles)
    assert "Photo Archive Cleanup" in project_titles


def test_tags_checklists_notes(database):
    task = things.tasks(
        database=database, include_items=True, search_query="Measure the plot"
    )[0]
    assert set(task["tags"]) == {"errand", "waiting"}
    assert [i["title"] for i in task["checklist"]] == ["Front edge", "Back edge"]
    assert "5 m tape" in task["notes"]


def test_non_english_titles(database):
    titles = {t["title"] for t in things.tasks(database=database, type="to-do")}
    assert "Comprar pimentón y azafrán" in titles
    assert "Müll rausbringen und Gelbe Säcke holen" in titles
    assert "請求書の写真を整理する" in titles


def test_recurrence_rules_decode(built):
    path, ids = built
    conn = sqlite3.connect(path)
    try:
        rows = conn.execute(
            "SELECT uuid, rt1_recurrenceRule FROM TMTask "
            "WHERE rt1_recurrenceRule IS NOT NULL"
        ).fetchall()
        instances = dict(
            conn.execute(
                "SELECT rt1_repeatingTemplate, title FROM TMTask "
                "WHERE rt1_repeatingTemplate IS NOT NULL"
            ).fetchall()
        )
    finally:
        conn.close()
    by_uuid = {uuid: blob for uuid, blob in rows}
    assert len(by_uuid) == len(bf.RECURRENCE_RULES) == 9
    for key, rule in bf.RECURRENCE_RULES.items():
        blob = by_uuid[bf.make_uuid(key)]
        assert blob.startswith(b"bplist00")
        decoded = plistlib.loads(blob)
        assert decoded == rule
        assert decoded["fu"] in (16, 256, 8, 4)
        assert decoded["tp"] in (0, 1)
    assert plistlib.loads(by_uuid[ids["tpl_monthly_last"]])["of"] == [{"dy": -1}]
    assert plistlib.loads(by_uuid[ids["tpl_after_completion"]])["tp"] == 1
    assert "zz" in plistlib.loads(by_uuid[ids["tpl_unrecognised"]])
    assert set(instances) == {
        bf.make_uuid(k) for k in bf.RECURRENCE_RULES if k != "tpl_leftover"
    }


def test_leftover_template_is_in_trashed_project(built):
    path, _ = built
    conn = sqlite3.connect(path)
    try:
        (trashed,) = conn.execute(
            "SELECT p.trashed FROM TMTask t JOIN TMTask p ON t.project = p.uuid "
            "WHERE t.uuid = ?",
            (bf.make_uuid("tpl_leftover"),),
        ).fetchone()
    finally:
        conn.close()
    assert trashed == 1


def test_builder_never_touches_the_real_things_path(tmp_path, monkeypatch):
    opened = []
    real_connect, real_open = sqlite3.connect, builtins.open

    def spy_connect(database, *args, **kwargs):
        opened.append(str(database))
        return real_connect(database, *args, **kwargs)

    def spy_open(file, *args, **kwargs):
        opened.append(str(file))
        return real_open(file, *args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", spy_connect)
    monkeypatch.setattr(builtins, "open", spy_open)

    path = tmp_path / "fixture.sqlite"
    bf.build_fixture(path, FIXED_TODAY)
    things.areas(filepath=str(path), count_only=True)

    assert opened
    library = str(Path.home() / "Library")
    for name in opened:
        assert library not in name
        assert "ThingsData" not in name
        assert "culturedcode" not in name.lower()
    assert str(path) in opened
    assert "Library" not in Path(bf.__file__).read_text(encoding="utf-8")
