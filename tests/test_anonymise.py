"""Anonymisation (DESIGN.md 7.5), against the synthetic fixture only.

To regenerate the light and strict golden files after an intended change:
    TIDYLINE_UPDATE_GOLDEN=1 uv run pytest tests/test_anonymise.py
and review the diff before committing.
"""

import datetime as dt
import json
import os
import re
import sqlite3
import stat
import unicodedata
from pathlib import Path

import pytest
from fixtures import build_fixture as bf

from tidyline import anonymise as anon
from tidyline import cli
from tidyline.anonymise import anonymise, make_labels, scrub
from tidyline.db.snapshot import open_snapshot
from tidyline.read import read_snapshot
from tidyline.render.json_out import build_export

FIXTURES = Path(__file__).parent / "fixtures"
TODAY = dt.date(2026, 10, 10)
U = bf.make_uuid
FAKE_PII = (
    "landlord@example.com",
    "www.example.com",
    "+91 98765 43210",
    "555-010-4477",
    "25000000",
    "12345678",
    "1,500",
    "$1,200.00",
)


def export_of(path):
    with open_snapshot(path) as copy:
        snapshot = read_snapshot(copy)
    return build_export(
        snapshot,
        today=TODAY,
        exported_at=dt.datetime(2026, 10, 10, 12, tzinfo=dt.timezone.utc),
        tool_version="test",
        environment={"macos": "27.0.1", "arch": "arm64", "things_version": "3.24.1",
                     "database_version": 29},
    )  # fmt: skip


def dumped(data):
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


@pytest.fixture
def plain(fixture_db):
    return export_of(fixture_db)


@pytest.fixture
def light(plain):
    return json.loads(dumped(anonymise(plain, "light")))


@pytest.fixture
def strict(plain):
    return json.loads(dumped(anonymise(plain, "strict")))


def fold(text):
    return unicodedata.normalize("NFKC", text).casefold()


def every_stored_string(path):
    """Every title, name, note and checklist string in the fixture database."""
    conn = sqlite3.connect(path)
    try:
        found = []
        for sql in (
            "SELECT title FROM TMTask",
            "SELECT notes FROM TMTask",
            "SELECT title FROM TMArea",
            "SELECT title FROM TMTag",
            "SELECT title FROM TMChecklistItem",
        ):
            found += [row[0] for row in conn.execute(sql) if row[0]]
    finally:
        conn.close()
    return found


# --- golden files ----


@pytest.mark.parametrize("level", ["light", "strict"])
def test_matches_the_golden_file(plain, level):
    golden = FIXTURES / f"export_golden_{level}.json"
    text = dumped(anonymise(plain, level))
    if os.environ.get("TIDYLINE_UPDATE_GOLDEN"):
        golden.write_text(text, encoding="utf-8")
    assert text == golden.read_text(encoding="utf-8")


# --- the required strict test ----


def test_strict_contains_no_stored_text(fixture_db, plain):
    strings = every_stored_string(fixture_db)
    assert len(strings) > 80
    # sanity: the fixture really has the hard cases
    assert any(fold(s) != s.casefold() for s in strings)  # changes under NFKC
    assert any(ord(c) > 0x3000 for s in strings for c in s)  # non-Latin
    text = fold(dumped(anonymise(plain, "strict")))
    leaked = [s for s in strings if fold(s).strip() and fold(s).strip() in text]
    assert leaked == []


def test_strict_contains_no_fake_pii(strict):
    text = dumped(strict)
    for value in FAKE_PII:
        assert value not in text, value


def test_none_export_still_contains_everything(plain):
    # proves the strict test above would catch a leak
    text = dumped(anonymise(plain, "none"))
    for value in FAKE_PII:
        assert value in text, value


# --- strict ----


def test_strict_structure(strict, plain):
    assert strict["anonymisation"] == "strict"
    assert strict["export_schema_version"] == "1.1"
    assert list(strict) == list(plain)
    tasks = {t["id"]: t for t in strict["tasks"]}
    lease = tasks[U("t_lease")]
    assert re.fullmatch(r"Task [a-z2-7]{6}", lease["title"])
    assert lease["notes"] is None
    assert lease["checklist"] is None
    assert lease["checklist_count"] == 2
    assert lease["area"]["title"].startswith("Area ")
    plain_lease = {t["id"]: t for t in plain["tasks"]}[U("t_lease")]
    for key in ("start", "start_code", "status", "status_code", "effective_status",
                "start_date", "deadline", "completion_date", "trashed"):  # fmt: skip
        assert lease[key] == plain_lease[key], key
    assert strict["findings"] == plain["findings"]


def test_strict_keys_are_the_same_at_every_level(plain, light, strict):
    lists = ("areas", "projects", "headings", "tasks", "recurring_templates")

    def keys(data):
        return {key: {tuple(sorted(e)) for e in data[key]} for key in lists}

    assert keys(plain) == keys(light) == keys(strict)


def test_strict_labels_use_the_same_label_for_an_id_everywhere(strict):
    labels = {}

    def record(entry_id, title):
        assert labels.setdefault(entry_id, title) == title, entry_id

    for area in strict["areas"]:
        record(area["id"], area["title"])
    for key in ("projects", "headings", "tasks", "recurring_templates"):
        for entry in strict[key]:
            record(entry["id"], entry["title"])
            for ref_key in ("area", "project", "heading", "recurring_template"):
                ref = entry.get(ref_key)
                if ref and ref["title"] is not None:
                    record(ref["id"], ref["title"])
            for tag in entry.get("tags") or []:
                record(tag["id"], tag["title"])
    garden = labels[U("proj_garden")]
    assert garden.startswith("Project ")
    measure = {t["id"]: t for t in strict["tasks"]}[U("t_measure")]
    assert measure["project"]["title"] == garden
    assert measure["tags"][0]["title"].startswith("Tag ")
    instance = {t["id"]: t for t in strict["tasks"]}[U("tpl_monthly_15:instance")]
    assert instance["recurring_template"]["title"].startswith("Template ")


def test_strict_labels_are_stable_across_exports(fixture_db, strict):
    again = json.loads(dumped(anonymise(export_of(fixture_db), "strict")))
    assert dumped(again) == dumped(strict)


def test_label_depends_on_the_id_alone():
    ids = [U(f"x{n}") for n in range(50)]
    full = make_labels("task", ids)
    assert make_labels("task", list(reversed(ids))) == full  # order
    fewer = make_labels("task", ids[10:])  # others removed
    assert all(fewer[i] == full[i] for i in ids[10:])
    more = make_labels("task", ids + [U("new one")])  # another added
    assert all(more[i] == full[i] for i in ids)


def test_adding_and_removing_rows_keeps_other_labels(fixture_db, strict):
    conn = sqlite3.connect(fixture_db)
    conn.execute(
        'INSERT INTO TMTask (uuid, type, status, trashed, title, start, "index", '
        "startBucket) VALUES (?, 0, 0, 0, 'A brand new task', 1, 999, 0)",
        (U("t_brand_new"),),
    )
    conn.execute("DELETE FROM TMTask WHERE uuid = ?", (U("t_cables"),))
    conn.commit()
    conn.close()
    changed = json.loads(dumped(anonymise(export_of(fixture_db), "strict")))
    before = {t["id"]: t["title"] for t in strict["tasks"]}
    after = {t["id"]: t["title"] for t in changed["tasks"]}
    assert U("t_brand_new") in after and U("t_cables") not in after
    for task_id, label in before.items():
        if task_id != U("t_cables"):
            assert after[task_id] == label


def test_a_forced_collision_is_resolved_deterministically():
    ids = [U(f"collide{n}") for n in range(40)]
    first = make_labels("tag", ids, length=1)  # 32 codes for 40 ids: collisions
    assert len(set(first.values())) == len(ids)
    assert make_labels("tag", list(reversed(ids)), length=1) == first
    colliding = [label for label in first.values() if "-" in label]
    assert colliding
    assert all(re.fullmatch(r"Tag [a-z2-7]-[a-z2-7]{4,}", label) for label in colliding)


def test_label_codes_come_from_sha256_base32():
    code = anon._code("abc")
    assert len(code) == 52 and code == code.lower()
    assert make_labels("area", ["abc"]) == {"abc": f"Area {code[:6]}"}


# --- light ----


def test_light_scrubs_each_kind_of_fake_pii(light):
    lease = {t["id"]: t for t in light["tasks"]}[U("t_lease")]
    assert lease["title"] == "Renew the lease at <url>"
    assert lease["notes"] is None
    assert [item["title"] for item in lease["checklist"]] == [
        "Pay <amount> fee by 2026-10-10",
        "Transfer <amount> to account <number>",
    ]
    assert lease["checklist_count"] == 2
    text = dumped(light)
    for value in FAKE_PII:
        assert value not in text, value


def test_light_keeps_ordinary_words_and_structure(light, plain):
    tasks = {t["id"]: t for t in light["tasks"]}
    assert tasks[U("t_measure")]["title"] == "Measure the plot"
    assert tasks[U("t_ja")]["title"] == "請求書の写真を整理する"
    assert tasks[U("t_measure")]["project"]["title"] == "Garden Shed Rebuild"
    assert tasks[U("t_measure")]["tags"][0]["title"] == "errand"
    assert all(t["notes"] is None for t in light["tasks"])
    assert light["anonymisation"] == "light"
    assert light["findings"] == plain["findings"]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Pay by 2026-10-10", "Pay by 2026-10-10"),
        ("Due 10/10/2026 or 10-10-2026", "Due 10/10/2026 or 10-10-2026"),
        ("call 555-010-4477", "call <phone>"),
        ("call (555) 010-4477", "call <phone>"),
        ("+1 555 010 4477", "<phone>"),
        ("+91 98765 43210", "<phone>"),
        ("98765-43210", "<phone>"),
        ("Rs. 1,500 fee", "<amount> fee"),
        ("Rs 500", "<amount>"),
        ("₹2,500", "<amount>"),
        ("INR 300", "<amount>"),
        ("300 INR", "<amount>"),
        ("$1,200.00", "<amount>"),
        ("€12.50 and 12 EUR", "<amount> and <amount>"),
        ("ref 25000000", "ref <number>"),
        ("mail me@example.com", "mail <email>"),
        ("see https://example.com/a?b=1", "see <url>"),
        ("Things 3.24.1", "Things 3.24.1"),
        ("Buy 2 apples and 12 pears", "Buy 2 apples and 12 pears"),
        ("call 555-0123", "call <phone>"),  # 7 digits is enough
    ],
)
def test_scrub(text, expected):
    assert scrub(text) == expected


def test_spaced_twelve_digit_group():
    assert scrub("ID 1234 5678 9012") in ("ID <number>", "ID <phone>")


def test_short_digit_groups_are_not_phones():
    assert scrub("Rooms 12-34") == "Rooms 12-34"  # 4 digits
    assert scrub("Order 123 456") == "Order 123 456"  # 6 digits


# --- technical fields ----


def test_raw_rules_lose_strings_and_the_hex_prefix(plain, light, strict):
    for data in (light, strict):
        templates = {t["id"]: t for t in data["recurring_templates"]}
        unreadable = templates[U("tpl_invalid_plist")]["recurrence"]
        assert "_hex_prefix" not in unreadable["raw"]
        assert unreadable["raw"]["_length"] == len(bf.INVALID_RULE_BLOB)
        assert unreadable["raw"]["_decode_error"] == "<text>"
    plain_daily = {t["id"]: t for t in plain["recurring_templates"]}[U("tpl_daily")][
        "recurrence"
    ]
    light_daily = {t["id"]: t for t in light["recurring_templates"]}[U("tpl_daily")]
    assert light_daily["recurrence"] == plain_daily  # numbers only: unchanged
    strict_daily = {t["id"]: t for t in strict["recurring_templates"]}[U("tpl_daily")]
    assert strict_daily["recurrence"]["text"] == "Daily"
    assert strict_daily["recurrence"]["raw"] == {
        **plain_daily["raw"], "ed": None, "ia": None, "sr": None,
    }  # fmt: skip


def test_recurrence_notes_lose_quoted_values():
    recurrence = {
        "text": "Weekly on Sun",
        "confidence": "verified",
        "notes": ["unfamiliar value: zz='my secret'", "unfamiliar field: zz",
                  "unknown unit: fu=999"],
        "raw": {"fu": 256, "zz": "my secret", "of": [{"wd": 0, "x": "y"}]},
    }  # fmt: skip
    export = {
        "areas": [], "projects": [], "headings": [], "warnings": [],
        "tasks": [], "recurring_templates": [
            {"id": "t", "title": "x", "notes": None, "tags": [],
             "recurrence": recurrence},
        ],
    }  # fmt: skip
    for level in ("light", "strict"):
        cleaned = anonymise(export, level)["recurring_templates"][0]["recurrence"]
        assert cleaned["notes"] == [
            "unfamiliar value: zz=<text>",
            "unfamiliar field: zz",
            "unknown unit: fu=999",
        ]
        assert cleaned["raw"] == {
            "fu": 256,
            "zz": "<text>",
            "of": [{"wd": 0, "x": "<text>"}],
        }
        assert cleaned["text"] == "Weekly on Sun"
    assert anonymise(export, "none")["recurring_templates"][0]["recurrence"] == (
        recurrence
    )


@pytest.mark.parametrize(
    ("warning", "expected"),
    [
        ("TMTask abc: startDate 132788096 could not be decoded; treated as missing",
         "TMTask abc: startDate 132788096 could not be decoded; treated as missing"),
        ("TMTask abc: creationDate 1e+20 could not be decoded; treated as missing",
         "TMTask abc: creationDate 1e+20 could not be decoded; treated as missing"),
        ("TMTask abc: startDate 'Dentist 3pm' could not be decoded; treated as missing",
         "TMTask abc: startDate <value> could not be decoded; treated as missing"),
        ("TMTask abc: unknown status 1", "TMTask abc: unknown status 1"),
        ("TMTask abc: unknown start 'x'", "TMTask abc: unknown start <value>"),
        ("TMTask abc: unknown type 'y'; skipped",
         "TMTask abc: unknown type <value>; skipped"),
        ("TMTask abc: area gone does not exist; ignored",
         "TMTask abc: area <value> does not exist; ignored"),
        ("TMTask abc: listed by things.py but not found",
         "TMTask abc: listed by things.py but not found"),
        ("something new about Dentist", "warning: <warning text withheld>"),
    ],
)  # fmt: skip
def test_warning_values(warning, expected):
    export = {
        "areas": [], "projects": [], "headings": [], "tasks": [],
        "recurring_templates": [], "warnings": [warning],
    }  # fmt: skip
    for level in ("light", "strict"):
        assert anonymise(export, level)["warnings"] == [expected]
    assert anonymise(export, "none")["warnings"] == [warning]


def test_input_is_not_changed(plain):
    before = dumped(plain)
    anonymise(plain, "strict")
    anonymise(plain, "light")
    assert dumped(plain) == before


def test_unknown_level():
    with pytest.raises(ValueError):
        anonymise({}, "medium")


# --- CLI ------------------------------------------------------------------------------


@pytest.fixture
def no_real_app(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "THINGS_INFO_PLIST", tmp_path / "missing.plist")


@pytest.mark.parametrize("level", ["none", "light", "strict"])
def test_cli_each_level(fixture_db, tmp_path, capsys, no_real_app, level):
    out = tmp_path / f"{level}.json"
    old = os.umask(0)
    try:
        code = cli.main(
            ["--db", str(fixture_db), "export", "--out", str(out), "--anonymise", level]
        )
    finally:
        os.umask(old)
    assert code == 0
    assert stat.S_IMODE(out.stat().st_mode) == 0o600
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["anonymisation"] == level
    err = capsys.readouterr().err
    if level == "strict":
        assert "structure and dates still reveal how you work" in err
        assert "personal task data" not in err
        assert "landlord@example.com" not in out.read_text(encoding="utf-8")
    else:
        assert "personal task data" in err


@pytest.mark.parametrize("level", ["light", "strict"])
def test_cli_overwrite_still_refused(fixture_db, tmp_path, capsys, no_real_app, level):
    out = tmp_path / "export.json"
    out.write_text("keep me", encoding="utf-8")
    code = cli.main(
        ["--db", str(fixture_db), "export", "--out", str(out), "--anonymise", level]
    )
    assert code == 2
    assert out.read_text(encoding="utf-8") == "keep me"


def test_cli_rejects_an_unknown_level(fixture_db, tmp_path, capsys):
    with pytest.raises(SystemExit) as error:
        cli.main(["--db", str(fixture_db), "export", "--out", str(tmp_path / "x"),
                  "--anonymise", "medium"])  # fmt: skip
    assert error.value.code == 2


# --- raw rule timestamps at strict ----


def raw_timestamps(data):
    """Every ed, ia and sr value in the raw rules of an export or payload."""
    found = set()
    for entry in data["tasks"] + data["recurring_templates"]:
        raw = (entry.get("recurrence") or {}).get("raw") or {}
        found.update(raw[key] for key in anon.WITHHELD_RULE_FIELDS if key in raw)
    return found


def test_strict_withholds_rule_timestamps(plain, light, strict):
    values = raw_timestamps(plain) - {None}
    assert len(values) > 10  # the fixture really has them
    assert raw_timestamps(light) == raw_timestamps(plain)
    assert raw_timestamps(strict) == {None}
    text = dumped(strict)
    for value in values:
        assert json.dumps(value) not in text, value


def test_withheld_rule_timestamps_break_nothing(fixture_db, plain, strict):
    """A rule with null ed, ia and sr still parses and renders, and decode and
    the checks never read the anonymised rule."""
    from dataclasses import replace

    from tidyline.checks import run_checks
    from tidyline.decode import decode_text, label_map
    from tidyline.recurrence import parse_rule
    from tidyline.render.recurrence_out import render_recurrence

    plain_rules = {t["id"]: t["recurrence"] for t in plain["recurring_templates"]}
    with open_snapshot(fixture_db) as copy:
        snapshot = read_snapshot(copy)
    stripped = {}
    for template in strict["recurring_templates"]:
        rule = parse_rule(template["recurrence"]["raw"])
        original = plain_rules[template["id"]]
        if original["confidence"] != "unrecognised":
            assert rule.recognised, template["id"]
        stripped[template["id"]] = rule
    tasks = tuple(
        replace(t, recurrence=stripped[t.uuid]) if t.uuid in stripped else t
        for t in snapshot.tasks
    )
    nulled = replace(snapshot, tasks=tasks)
    assert "fields in the rule" in render_recurrence(nulled, raw=True)
    assert render_recurrence(nulled)
    run_checks(nulled, TODAY)
    label = strict["tasks"][0]["title"]
    assert decode_text(label, label_map(snapshot)).replaced == 1
