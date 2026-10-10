"""JSON export (DESIGN.md 7.4), against the synthetic fixture only.

To regenerate the golden file after an intended format change:
    TIDYLINE_UPDATE_GOLDEN=1 uv run pytest tests/test_export.py
and review the diff before committing.
"""

import datetime as dt
import json
import os
import sqlite3
import stat
from pathlib import Path

import pytest
from fixtures import build_fixture as bf

from tidyline import cli
from tidyline.db.snapshot import open_snapshot
from tidyline.read import read_snapshot
from tidyline.render.json_out import build_export

GOLDEN = Path(__file__).parent / "fixtures" / "export_golden.json"
FIXED_TODAY = dt.date(2026, 10, 10)
EXPORTED_AT = dt.datetime(2026, 10, 10, 12, 0, tzinfo=dt.timezone.utc)
ENVIRONMENT = {
    "macos": "27.0.1",
    "arch": "arm64",
    "things_version": "3.24.1",
    "database_version": 29,
}
U = bf.make_uuid

TASK_KEYS = {
    "id",
    "title",
    "notes",
    "area",
    "project",
    "heading",
    "effective_status",
    "start",
    "start_code",
    "start_date",
    "deadline",
    "status",
    "status_code",
    "trashed",
    "completion_date",
    "tags",
    "checklist",
    "recurring_template",
    "recurrence",
}


def export_fixture(path):
    with open_snapshot(path) as copy:
        snapshot = read_snapshot(copy)
    data = build_export(
        snapshot,
        today=FIXED_TODAY,
        exported_at=EXPORTED_AT,
        tool_version="test",
        environment=ENVIRONMENT,
    )
    # what the CLI writes, read back
    return json.loads(json.dumps(data, indent=2, ensure_ascii=False))


@pytest.fixture
def exported(fixture_db):
    return export_fixture(fixture_db)


def by_id(entries):
    return {entry["id"]: entry for entry in entries}


# --- structure ----------------------------------------------------------------


def test_matches_the_golden_file(exported):
    text = json.dumps(exported, indent=2, ensure_ascii=False) + "\n"
    if os.environ.get("TIDYLINE_UPDATE_GOLDEN"):
        GOLDEN.write_text(text, encoding="utf-8")
    assert text == GOLDEN.read_text(encoding="utf-8")


def test_top_level_keys(exported):
    assert list(exported) == [
        "export_schema_version",
        "tool",
        "exported_at",
        "environment",
        "anonymisation",
        "areas",
        "projects",
        "headings",
        "tasks",
        "recurring_templates",
        "findings",
        "warnings",
    ]
    assert exported["export_schema_version"] == "1"
    assert exported["anonymisation"] == "none"
    assert exported["findings"] == []
    assert exported["warnings"] == []
    assert exported["exported_at"] == "2026-10-10T12:00:00+00:00"
    assert exported["environment"] == ENVIRONMENT


def test_counts(exported):
    assert len(exported["areas"]) == 2
    assert len(exported["projects"]) == 7
    assert len(exported["headings"]) == 2
    assert len(exported["tasks"]) == 37  # every to-do, open or not; no templates
    assert len(exported["recurring_templates"]) == 25  # trashed one ignored


def test_every_task_has_the_listed_keys(exported):
    for task in exported["tasks"]:
        assert set(task) == TASK_KEYS, task["id"]
    for entry in exported["projects"] + exported["headings"]:
        assert set(entry) == TASK_KEYS - {
            "checklist",
            "recurring_template",
            "recurrence",
        }


def test_task_fields(exported):
    tasks = by_id(exported["tasks"])
    measure = tasks[U("t_measure")]
    assert measure["heading"] == {"id": U("head_plan"), "title": "Planning"}
    # the heading's project is reported
    assert measure["project"] == {
        "id": U("proj_garden"),
        "title": "Garden Shed Rebuild",
    }
    assert measure["tags"] == [
        {"id": U("tag_errand"), "title": "errand"},
        {"id": U("tag_waiting"), "title": "waiting"},
    ]
    assert [item["title"] for item in measure["checklist"]] == [
        "Front edge",
        "Back edge",
    ]
    nextweek = tasks[U("t_nextweek")]
    assert nextweek["start_date"] == "2026-10-17"
    assert (nextweek["start"], nextweek["start_code"]) == ("someday", 2)
    assert nextweek["effective_status"] == "upcoming"
    assert nextweek["checklist"][0] == {
        "id": U("t_nextweek:check:0"),
        "title": "Find the insurance card",
        "status": "completed",
        "status_code": 3,
    }
    assert tasks[U("t_overdue")]["deadline"] == "2026-10-05"
    assert tasks[U("t_evening")]["effective_status"] == "this_evening"
    assert tasks[U("t_inbox")]["area"] is None
    done = tasks[U("t_done")]
    assert (done["status"], done["status_code"]) == ("completed", 3)
    assert done["effective_status"] == "closed"
    assert done["completion_date"] == "2026-10-08T09:00:00+00:00"
    cancelled = tasks[U("t_cancelled")]
    assert cancelled["status"] == "cancelled"
    assert cancelled["completion_date"] is not None
    assert tasks[U("t_trashed")]["trashed"] is True
    assert tasks[U("t_lease")]["completion_date"] is None


def test_instances_carry_their_template_rule(exported):
    instance = by_id(exported["tasks"])[U("tpl_monthly_15:instance")]
    assert instance["recurring_template"] == {
        "id": U("tpl_monthly_15"),
        "title": "Pay the rent",
    }
    assert instance["recurrence"]["text"] == "Monthly on day 15"
    assert by_id(exported["tasks"])[U("t_lease")]["recurrence"] is None


def test_ordering_is_by_index_then_uuid(exported):
    for key in ("projects", "headings", "tasks", "recurring_templates"):
        ids = [entry["id"] for entry in exported[key]]
        assert len(ids) == len(set(ids)), key
    assert [a["title"] for a in exported["areas"]] == ["Household", "Side Studio"]


# --- recurrence -----------------------------------------------------------------


def test_recurring_templates(exported):
    templates = by_id(exported["recurring_templates"])
    leftover = templates[U("tpl_leftover")]
    assert leftover["leftover"] is True
    assert leftover["project"] == {"id": U("proj_trashed"), "title": "Old Newsletter"}
    assert [t["id"] for t in templates.values() if t["leftover"]] == [U("tpl_leftover")]
    assert U("tpl_trashed") not in templates
    assert templates[U("tpl_paused")]["paused"] is True
    monthly = templates[U("tpl_monthly_last")]["recurrence"]
    assert monthly["text"] == "Monthly on last day"
    assert monthly["confidence"] == "assumed"
    assert monthly["notes"]
    assert monthly["raw"]["fu"] == 8
    assert templates[U("tpl_monthly_15")]["instances"] == [U("tpl_monthly_15:instance")]
    assert templates[U("tpl_weekly_fri")]["instances"] == []
    unreadable = templates[U("tpl_invalid_plist")]["recurrence"]
    assert unreadable["text"] == "recurring (rule unreadable)"
    assert "_decode_error" in unreadable["raw"]


# --- UUID joins and Unicode -------------------------------------------------------


def test_same_titled_projects_stay_separate(exported):
    projects = by_id(exported["projects"])
    home, studio = projects[U("proj_admin_home")], projects[U("proj_admin_studio")]
    assert home["title"] == studio["title"] == "Admin"
    assert home["area"]["title"] == "Household"
    assert studio["area"]["title"] == "Side Studio"
    tasks = by_id(exported["tasks"])
    assert tasks[U("t_dup_a")]["project"]["id"] == U("proj_admin_home")
    assert tasks[U("t_dup_b")]["project"]["id"] == U("proj_admin_studio")


def test_non_english_titles_survive_unchanged(exported):
    tasks = by_id(exported["tasks"])
    assert tasks[U("t_es")]["title"] == "Comprar pimentón y azafrán"
    assert tasks[U("t_es")]["notes"] == "Mercado del sábado: ¿hay también cúrcuma?"
    assert tasks[U("t_de")]["title"] == "Müll rausbringen und Gelbe Säcke holen"
    assert tasks[U("t_ja")]["title"] == "請求書の写真を整理する"
    text = GOLDEN.read_text(encoding="utf-8")
    assert "請求書の写真を整理する" in text  # not \\u escaped


def test_warnings_are_exported(fixture_db):
    conn = sqlite3.connect(fixture_db)
    conn.execute(
        "UPDATE TMTask SET startDate = ? WHERE uuid = ?",
        (2026 << 16 | 13 << 12 | 1 << 7, U("t_today")),
    )
    conn.commit()
    conn.close()
    exported = export_fixture(fixture_db)
    assert len(exported["warnings"]) == 1
    assert by_id(exported["tasks"])[U("t_today")]["start_date"] is None


def test_naive_exported_at_is_rejected(fixture_db):
    with open_snapshot(fixture_db) as copy:
        snapshot = read_snapshot(copy)
    with pytest.raises(ValueError):
        build_export(
            snapshot,
            today=FIXED_TODAY,
            exported_at=dt.datetime(2026, 10, 10),
            tool_version="test",
            environment=ENVIRONMENT,
        )


# --- CLI ------------------------------------------------------------------------


@pytest.fixture
def no_real_app(monkeypatch, tmp_path):
    """Keep the CLI away from the installed Things app's Info.plist."""
    monkeypatch.setattr(cli, "THINGS_INFO_PLIST", tmp_path / "missing.plist")


def run_export(fixture_db, out, *extra):
    return cli.main(["--db", str(fixture_db), "export", "--out", str(out), *extra])


def test_cli_writes_the_export(fixture_db, tmp_path, capsys, no_real_app):
    out = tmp_path / "export.json"
    assert run_export(fixture_db, out) == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["export_schema_version"] == "1"
    assert data["environment"]["database_version"] == 29
    assert data["environment"]["things_version"] is None
    assert len(data["tasks"]) == 37
    captured = capsys.readouterr()
    assert "Exported 37 tasks" in captured.out
    assert "personal task data" in captured.err


def test_cli_accepts_db_after_the_command(fixture_db, tmp_path, no_real_app):
    out = tmp_path / "export.json"
    assert cli.main(["export", "--db", str(fixture_db), "--out", str(out)]) == 0


def test_cli_file_mode_is_0600(fixture_db, tmp_path, no_real_app):
    out = tmp_path / "export.json"
    old = os.umask(0)  # even with a permissive umask
    try:
        assert run_export(fixture_db, out) == 0
    finally:
        os.umask(old)
    assert stat.S_IMODE(out.stat().st_mode) == 0o600


def test_cli_refuses_to_overwrite(fixture_db, tmp_path, capsys, no_real_app):
    out = tmp_path / "export.json"
    out.write_text("keep me", encoding="utf-8")
    assert run_export(fixture_db, out) == 1
    assert out.read_text(encoding="utf-8") == "keep me"
    err = capsys.readouterr().err
    assert "already exists" in err
    assert "Choose a new --out path" in err


def test_cli_refuses_a_dangling_symlink(fixture_db, tmp_path, no_real_app):
    out = tmp_path / "link.json"
    out.symlink_to(tmp_path / "nowhere.json")
    assert run_export(fixture_db, out) == 1
    assert not (tmp_path / "nowhere.json").exists()


@pytest.mark.parametrize("level", ["light", "strict"])
def test_cli_anonymise_levels_are_not_available_yet(
    fixture_db, tmp_path, capsys, level, no_real_app
):
    out = tmp_path / "export.json"
    assert run_export(fixture_db, out, "--anonymise", level) == 2
    assert not out.exists()
    assert "arrives in v0.2" in capsys.readouterr().err


def test_cli_stdout_is_not_supported(fixture_db, capsys, no_real_app):
    assert cli.main(["--db", str(fixture_db), "export", "--out", "-"]) == 2
    assert "not supported in v0.1" in capsys.readouterr().err


def test_cli_missing_folder(fixture_db, tmp_path, capsys, no_real_app):
    assert run_export(fixture_db, tmp_path / "no" / "export.json") == 1
    assert "does not exist" in capsys.readouterr().err


def test_cli_out_is_required(capsys):
    with pytest.raises(SystemExit) as error:
        cli.main(["export"])
    assert error.value.code == 2
    assert "--out" in capsys.readouterr().err


def test_cli_missing_database(tmp_path, capsys, no_real_app):
    code = cli.main(
        ["--db", str(tmp_path / "none.sqlite"), "export", "--out", str(tmp_path / "x")]
    )
    assert code == 1
    assert not (tmp_path / "x").exists()


def test_help_lists_export(capsys):
    with pytest.raises(SystemExit):
        cli.main(["--help"])
    assert "export" in capsys.readouterr().out


# --- the auth token can never appear ---------------------------------------------

SECRET = "SECRET-AUTH-TOKEN-0123456789"
FORBIDDEN_KEY_PARTS = ("token", "settings", "urischeme", "auth")


def all_keys(value):
    if isinstance(value, dict):
        for key, inner in value.items():
            yield key
            yield from all_keys(inner)
    elif isinstance(value, list):
        for inner in value:
            yield from all_keys(inner)


def test_no_token_or_settings_in_the_export(fixture_db, tmp_path, no_real_app):
    conn = sqlite3.connect(fixture_db)
    conn.execute(
        "INSERT INTO TMSettings (uuid, uriSchemeAuthenticationToken) VALUES (?, ?)",
        ("settings", SECRET),
    )
    conn.commit()
    conn.close()
    out = tmp_path / "export.json"
    assert run_export(fixture_db, out) == 0
    text = out.read_text(encoding="utf-8")
    assert SECRET not in text
    assert "TMSettings" not in text
    data = json.loads(text)
    keys = [key.casefold() for key in all_keys(data)]
    # the raw recurrence rule is Things' own data; skip its keys
    for template in data["recurring_templates"]:
        if template["recurrence"]:
            raw_keys = {k.casefold() for k in all_keys(template["recurrence"]["raw"])}
            keys = [k for k in keys if k not in raw_keys]
    found = [k for k in keys if any(part in k for part in FORBIDDEN_KEY_PARTS)]
    assert found == []
