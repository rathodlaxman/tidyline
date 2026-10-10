"""`tidyline check`, against the synthetic fixture only."""

import json

import pytest
from checks_helpers import U, edit

from tidyline import cli
from tidyline.checks import CHECK_IDS


@pytest.fixture(autouse=True)
def no_real_app(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "THINGS_INFO_PLIST", tmp_path / "missing.plist")


def run(fixture_db, *args):
    return cli.main(["--db", str(fixture_db), "check", *args])


def test_text_output_groups_by_check_and_shows_titles(fixture_db, capsys):
    assert run(fixture_db) == 1
    out = capsys.readouterr().out
    assert out.startswith("tidyline check: 4 checks, 7 findings (7 warnings, 0 info)")
    headers = [
        line.split(" (")[0] for line in out.splitlines() if " (warning): " in line
    ]
    assert headers == list(CHECK_IDS)
    assert '      to-do    "Pay the electricity bill"' in out
    assert '      to-do    "Reconcile  receipts ·"' in out  # whitespace kept
    assert '      project  "Old Newsletter"' in out


def test_json_output_has_ids_and_no_titles(fixture_db, capsys):
    assert run(fixture_db, "--json") == 1
    out = capsys.readouterr().out
    data = json.loads(out)
    assert list(data) == ["check_schema_version", "checks", "summary", "findings"]
    assert data["check_schema_version"] == "1"
    assert data["checks"] == list(CHECK_IDS)
    assert data["summary"] == {"warning": 7, "info": 0}
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
    assert "possible_duplicates (warning): 0\n  none" in out


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
    assert cli.main(["--db", str(tmp_path / "none.sqlite"), "check"]) == 1
    assert "error:" in capsys.readouterr().err


def test_help_lists_check_and_its_options(capsys):
    with pytest.raises(SystemExit):
        cli.main(["--help"])
    assert "check" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        cli.main(["check", "--help"])
    out = capsys.readouterr().out
    for option in ("--only", "--pattern", "--json"):
        assert option in out
    assert "--db" not in out  # no extra options on check
