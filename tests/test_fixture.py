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
        "Read a chapter tonight",
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


def template_blobs(path):
    conn = sqlite3.connect(path)
    try:
        return dict(
            conn.execute(
                "SELECT uuid, rt1_recurrenceRule FROM TMTask "
                "WHERE rt1_recurrenceRule IS NOT NULL"
            ).fetchall()
        )
    finally:
        conn.close()


def decoded(path, key):
    return plistlib.loads(template_blobs(path)[bf.make_uuid(key)])


def test_recurrence_rules_decode(built):
    path, _ = built
    blobs = template_blobs(path)
    rules = bf.recurrence_rules(FIXED_TODAY)
    assert len(blobs) == len(rules) + 1 == 26
    for key, rule in rules.items():
        blob = blobs[bf.make_uuid(key)]
        assert blob.startswith(b"bplist00")
        assert plistlib.loads(blob) == rule
        assert isinstance(rule["ia"], float)
        assert isinstance(rule["sr"], float)
        for name in ("rc", "rrv", "ts"):
            assert isinstance(rule[name], int)


def test_every_rule_carries_the_real_extra_keys(built):
    path, _ = built
    for key, rule in bf.recurrence_rules(FIXED_TODAY).items():
        expected = {"fu", "fa", "tp", "of", "ia", "sr", "rc", "rrv", "ts"}
        if key != "tpl_no_ed":
            expected.add("ed")
        if key == "tpl_extra_key":
            expected.add("zz")
        assert set(rule) == expected, key


def test_offset_shapes(built):
    path, _ = built
    expected = {
        "tpl_daily": (16, 1, [{"dy": 0}]),
        "tpl_weekly_sun": (256, 1, [{"wd": 0}]),
        "tpl_weekly_fri": (256, 1, [{"wd": 5}]),
        "tpl_weekly_sat": (256, 1, [{"wd": 6}]),
        "tpl_biweekly_sun": (256, 2, [{"wd": 0}]),
        "tpl_monthly_first": (8, 1, [{"dy": 0}]),
        "tpl_monthly_15": (8, 1, [{"dy": 14}]),
        "tpl_monthly_last": (8, 1, [{"dy": -1}]),
        "tpl_every3_months": (8, 3, [{"dy": 4}]),
        "tpl_every6_months": (8, 6, [{"dy": 13}]),
        "tpl_monthly_first_sun": (8, 1, [{"wd": 0, "wdo": 1}]),
        "tpl_monthly_last_sun": (8, 1, [{"wd": 0, "wdo": -1}]),
        "tpl_yearly_feb28": (4, 1, [{"dy": 27, "mo": 1}]),
        "tpl_yearly_jan1": (4, 1, [{"dy": 0, "mo": 0}]),
    }
    for key, (fu, fa, offsets) in expected.items():
        rule = decoded(path, key)
        assert (rule["fu"], rule["fa"], rule["of"]) == (fu, fa, offsets), key
        assert rule["tp"] == 0
    assert decoded(path, "tpl_after_completion")["tp"] == 1


def test_rule_variants(built):
    path, _ = built
    assert "ed" not in decoded(path, "tpl_no_ed")
    assert decoded(path, "tpl_daily")["ed"] == bf.NEVER_ENDS
    end = decoded(path, "tpl_end_date")["ed"]
    assert end < 6.0e10
    expected_end = dt.datetime.combine(
        FIXED_TODAY + dt.timedelta(days=90), dt.time(0), tzinfo=dt.timezone.utc
    )
    assert end == expected_end.timestamp()
    assert decoded(path, "tpl_repeat_count")["rc"] == 12
    assert decoded(path, "tpl_lead_time")["ts"] == -7
    assert decoded(path, "tpl_rrv5")["rrv"] == 5
    assert decoded(path, "tpl_unknown_unit")["fu"] == 999
    assert decoded(path, "tpl_extra_key")["zz"] == 1
    # Ordinary rules use rrv 4 and the never-ends sentinel for ed.
    assert decoded(path, "tpl_weekly_sun")["rrv"] == 4


def test_one_rule_is_not_a_valid_plist(built):
    path, _ = built
    blob = template_blobs(path)[bf.make_uuid(bf.INVALID_RULE_KEY)]
    with pytest.raises(ValueError):
        plistlib.loads(blob)


def test_dates_depend_on_today_for_the_end_date():
    later = dt.date(2030, 1, 31)
    assert (
        bf.recurrence_rules(later)["tpl_end_date"]["ed"]
        != (bf.recurrence_rules(FIXED_TODAY)["tpl_end_date"]["ed"])
    )
    assert bf.recurrence_rules(later)["tpl_end_date"]["ed"] < 6.0e10


def test_template_rows(built):
    path, _ = built
    conn = sqlite3.connect(path)
    try:
        rows = {
            uuid: (paused, trashed, project, status)
            for uuid, paused, trashed, project, status in conn.execute(
                "SELECT uuid, rt1_instanceCreationPaused, trashed, project, status "
                "FROM TMTask WHERE rt1_recurrenceRule IS NOT NULL"
            )
        }
        paused_keys = [
            key
            for key in [*bf.recurrence_rules(FIXED_TODAY), bf.INVALID_RULE_KEY]
            if rows[bf.make_uuid(key)][0] == 1
        ]
    finally:
        conn.close()
    assert paused_keys == ["tpl_paused"]
    paused, trashed, project, _ = rows[bf.make_uuid("tpl_trashed")]
    assert trashed == 1 and project is None and paused == 0  # not a leftover
    leftover = rows[bf.make_uuid("tpl_leftover")]
    assert leftover[1] == 0 and leftover[2] == bf.make_uuid("proj_trashed")
    assert all(row[3] == 0 for row in rows.values())


def test_instances_three_open_two_completed(built):
    path, _ = built
    conn = sqlite3.connect(path)
    try:
        rows = conn.execute(
            "SELECT rt1_repeatingTemplate, status FROM TMTask "
            "WHERE rt1_repeatingTemplate IS NOT NULL"
        ).fetchall()
    finally:
        conn.close()
    open_templates = {t for t, status in rows if status == 0}
    done_templates = {t for t, status in rows if status == 3}
    assert open_templates == {
        bf.make_uuid(k) for k in ("tpl_daily", "tpl_weekly_sun", "tpl_monthly_15")
    }
    assert done_templates == {
        bf.make_uuid(k) for k in ("tpl_biweekly_sun", "tpl_yearly_feb28")
    }
    assert len(rows) == 5


def test_this_evening_task_and_start_bucket(built, database):
    path, _ = built
    conn = sqlite3.connect(path)
    try:
        buckets = dict(
            conn.execute("SELECT title, startBucket FROM TMTask WHERE startBucket != 0")
        )
        (row,) = conn.execute(
            "SELECT start, startBucket, startDate FROM TMTask WHERE title = ?",
            ("Read a chapter tonight",),
        ).fetchall()
    finally:
        conn.close()
    assert buckets == {"Read a chapter tonight": 1}
    assert row == (1, 1, bf.pack_date(FIXED_TODAY))
    # things.py ignores startBucket, so the task is in today() like any dated task
    titles = {task["title"] for task in things.today(database=database)}
    assert "Read a chapter tonight" in titles


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
