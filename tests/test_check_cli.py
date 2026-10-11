"""`tidyline check`, against the synthetic fixture only."""

import json
import re

import pytest
from checks_helpers import U, edit

from tidyline import cli
from tidyline.checks import CHECK_IDS
from tidyline.render.check_out import FIXING_GUIDE_URL


@pytest.fixture(autouse=True)
def no_real_app(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "THINGS_INFO_PLIST", tmp_path / "missing.plist")


def run(fixture_db, *args):
    return cli.main(["--db", str(fixture_db), "check", *args])


def test_text_output_groups_by_check_and_shows_titles(fixture_db, capsys):
    assert run(fixture_db) == 1
    out = capsys.readouterr().out
    assert out.startswith(
        "tidyline check: 10 checks, 19 findings (16 warnings, 3 info)"
    )
    headers = re.findall(r"^(\w+) \((?:warning|info), \d+ findings?\)$", out, re.M)
    assert headers == list(CHECK_IDS)
    assert "open_in_trashed_project (warning, 3 findings)\n" in out
    assert "possible_duplicates (warning, 1 finding)\n" in out
    assert out.endswith(f"How to fix these: {FIXING_GUIDE_URL}\n")
    assert '      to-do    "Pay the electricity bill"' in out
    assert '      to-do    "Reconcile  receipts ·"' in out  # whitespace kept
    assert '  "Old Newsletter" (project, 3 open to-dos)' in out


def test_json_output_has_ids_and_no_titles(fixture_db, capsys):
    assert run(fixture_db, "--json") == 1
    out = capsys.readouterr().out
    data = json.loads(out)
    assert list(data) == ["check_schema_version", "checks", "summary", "findings"]
    assert data["check_schema_version"] == "1"
    assert data["checks"] == list(CHECK_IDS)
    assert data["summary"] == {"warning": 16, "info": 3}
    duplicate = [f for f in data["findings"] if f["check"] == "possible_duplicates"]
    assert duplicate == [
        {
            "check": "possible_duplicates",
            "severity": "warning",
            "message": "2 open to-dos share a normalised title",
            "refs": [
                {"kind": "task", "id": U("t_dup_a")},
                {"kind": "task", "id": U("t_dup_b")},
            ],
        }
    ]
    for title in ("electricity", "Reconcile", "Newsletter", "cables"):
        assert title not in out


def test_only(fixture_db, capsys):
    assert (
        run(fixture_db, "--only", "possible_duplicates", "unfiled_open", "--json") == 1
    )
    data = json.loads(capsys.readouterr().out)
    assert data["checks"] == ["unfiled_open", "possible_duplicates"]
    assert {f["check"] for f in data["findings"]} == set(data["checks"])


def test_unknown_only_is_a_usage_error(fixture_db, capsys):
    with pytest.raises(SystemExit) as error:
        run(fixture_db, "--only", "nope")
    assert error.value.code == 2
    assert "invalid choice" in capsys.readouterr().err


def test_exit_0_when_no_warning(fixture_db, capsys):
    edit(fixture_db, ("UPDATE TMTask SET trashed = 1 WHERE uuid = ?", (U("t_dup_b"),)))
    assert run(fixture_db, "--only", "possible_duplicates") == 0
    out = capsys.readouterr().out
    assert "possible_duplicates (warning, 0 findings)\n" in out


def test_patterns_shown_on_screen_but_not_in_json(fixture_db, capsys):
    assert (
        run(fixture_db, "--only", "title_hygiene", "--pattern", "^Paint", "(?i)level")
        == 1
    )
    out = capsys.readouterr().out
    assert "  - matches user pattern 1 (/^Paint/)" in out
    assert "  - matches user pattern 2 (/(?i)level/)" in out
    assert (
        run(fixture_db, "--only", "title_hygiene", "--pattern", "^Paint", "--json") == 1
    )
    out = capsys.readouterr().out
    assert "matches user pattern 1" in out
    assert "^Paint" not in out


def test_bad_regex_is_exit_2(fixture_db, capsys):
    assert run(fixture_db, "--pattern", "ok", "(unclosed") == 2
    err = capsys.readouterr().err
    assert "--pattern 2 is not a valid regular expression" in err


def test_control_characters_in_titles_are_replaced(fixture_db, capsys):
    edit(fixture_db, (
        "UPDATE TMTask SET title = ? WHERE uuid = ?",
        ("Sort\x1b[31m the cables\x07", U("t_cables")),
    ))  # fmt: skip
    run(fixture_db, "--only", "unfiled_open")
    out = capsys.readouterr().out
    assert "\x1b" not in out and "\x07" not in out
    assert '      to-do    "Sort?[31m the cables?"' in out


def test_missing_database(tmp_path, capsys):
    assert cli.main(["--db", str(tmp_path / "none.sqlite"), "check"]) == 3
    assert "error:" in capsys.readouterr().err


def test_help_lists_check_and_its_options(capsys):
    with pytest.raises(SystemExit):
        cli.main(["--help"])
    assert "check" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        cli.main(["check", "--help"])
    out = capsys.readouterr().out
    for option in ("--db", "--only", "--pattern", "--json"):
        assert option in out


def test_db_after_the_command(fixture_db, capsys):
    assert cli.main(["check", "--db", str(fixture_db), "--json"]) == 1
    assert json.loads(capsys.readouterr().out)["check_schema_version"] == "1"


def test_unreadable_database_exits_3(fixture_db, capsys):
    import sqlite3

    conn = sqlite3.connect(fixture_db)
    conn.execute("ALTER TABLE TMTask DROP COLUMN startBucket")
    conn.commit()
    conn.close()
    assert run(fixture_db) == 3
    err = capsys.readouterr().err
    assert "startBucket" in err and "tidyline doctor" in err


def test_info_only_exits_0(fixture_db, capsys):
    only = ["leftover_templates", "someday_in_active_project", "outside_heading"]
    assert run(fixture_db, "--only", *only) == 0
    out = capsys.readouterr().out
    assert out.startswith("tidyline check: 3 checks, 3 findings (0 warnings, 3 info)")
    assert "leftover_templates (info, 1 finding)" in out
    assert '      template "Send the newsletter"' in out
    assert run(fixture_db, "--only", *only, "--json") == 0
    data = json.loads(capsys.readouterr().out)
    assert data["summary"] == {"warning": 0, "info": 3}
    assert {f["severity"] for f in data["findings"]} == {"info"}


def test_outside_heading_json_refs(fixture_db, capsys):
    run(fixture_db, "--only", "outside_heading", "--json")
    (finding,) = json.loads(capsys.readouterr().out)["findings"]
    assert finding["refs"] == [
        {"kind": "project", "id": U("proj_garden")},
        {"kind": "task", "id": U("t_level")},
        {"kind": "task", "id": U("t_door")},
    ]


GUIDE_LINE = (
    "How to fix these: "
    "https://github.com/rathodlaxman/tidyline/blob/main/docs/FIXING_PROBLEMS.md"
)


def test_text_output_ends_with_the_fixing_guide_link(fixture_db, capsys):
    run(fixture_db)
    out = capsys.readouterr().out
    assert out.endswith("\n\n" + GUIDE_LINE + "\n")
    assert out.count(GUIDE_LINE) == 1


def test_text_output_with_no_findings_still_ends_with_the_link(fixture_db, capsys):
    edit(fixture_db, ("UPDATE TMTask SET trashed = 1 WHERE uuid = ?", (U("t_dup_b"),)))
    assert run(fixture_db, "--only", "possible_duplicates") == 0
    assert capsys.readouterr().out.endswith("  none\n\n" + GUIDE_LINE + "\n")


def test_json_output_is_unchanged_by_the_link(fixture_db, capsys):
    run(fixture_db, "--json")
    out = capsys.readouterr().out
    assert "How to fix" not in out and "FIXING_PROBLEMS" not in out
    assert list(json.loads(out)) == [
        "check_schema_version",
        "checks",
        "summary",
        "findings",
    ]
    assert out == json.dumps(json.loads(out), indent=2, ensure_ascii=False) + "\n"


def test_text_groups_open_to_dos_under_their_trashed_project(fixture_db, capsys):
    run(fixture_db)
    out = capsys.readouterr().out
    block = out.split("open_in_trashed_project (warning, 3 findings)\n")[1]
    block = block.split("\n\n")[0].splitlines()[1:]  # skip the underline
    assert block == [
        '  "Old Newsletter" (project, 3 open to-dos)',
        '      "Draft newsletter issue 3"',
        '      "Plan newsletter issue 4"',
        '      "Send the proofs for review"',
    ]
    assert out.count('"Old Newsletter"') == 1


def test_text_groups_by_heading_when_the_heading_is_trashed(fixture_db, capsys):
    edit(
        fixture_db,
        ("UPDATE TMTask SET trashed = 1 WHERE uuid = ?", (U("head_plan"),)),
    )
    run(fixture_db)
    out = capsys.readouterr().out
    assert "(heading, 2 open to-dos)\n" in out
    assert "(project, 3 open to-dos)\n" in out


def test_text_output_with_one_check_and_no_findings(fixture_db, capsys):
    edit(
        fixture_db,
        *(
            ("UPDATE TMTask SET status = 3 WHERE uuid = ?", (U(key),))
            for key in (
                "t_in_trashed_project",
                "t_in_trashed_two",
                "t_in_trashed_three",
            )
        ),
    )
    run(fixture_db, "--only", "open_in_trashed_project")
    out = capsys.readouterr().out
    assert "open_in_trashed_project (warning, 0 findings)\n" in out
    assert "  none\n" in out
