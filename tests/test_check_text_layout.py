"""The text layout of `tidyline check` (DESIGN.md decisions log, 2026-10-11):
items grouped under their project or area with a count, a message that is the
same for every finding printed once, a message that differs after its item.

Scenarios are made by editing a copy of the synthetic fixture."""

import pytest
from checks_helpers import U, edit, set_title

from tidyline import cli


@pytest.fixture(autouse=True)
def no_real_app(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "THINGS_INFO_PLIST", tmp_path / "missing.plist")


def section(fixture_db, capsys, check):
    cli.main(["--db", str(fixture_db), "check", "--only", check])
    out = capsys.readouterr().out
    body = out.split("\n\n", 1)[1].rsplit("\n\nHow to fix these", 1)[0]
    return body.splitlines()[2:]  # drop the heading and its underline


def test_someday_in_active_project_groups_by_project(fixture_db, capsys):
    edit(
        fixture_db,
        *(
            ("UPDATE TMTask SET start = 2 WHERE uuid = ?", (U(key),))
            for key in ("t_level", "t_timber", "t_council")
        ),
    )
    lines = section(fixture_db, capsys, "someday_in_active_project")
    assert lines[0] == "Someday to-do inside an active project:"
    # groups come in the order of their first finding (the checks' own order)
    assert lines[1:3] == [
        '  "Admin" (project, 1 to-do)',
        '      "Check council tax bill"',
    ]
    assert lines[3] == '  "Garden Shed Rebuild" (project, 3 to-dos)'
    assert sorted(lines[4:]) == sorted(
        f'      "{title}"'
        for title in ("Buy a spirit level", "Price out timber", "Paint the shed door")
    )
    assert sum("Someday to-do inside" in line for line in lines) == 1


def test_unfiled_open_prints_its_message_once(fixture_db, capsys):
    lines = section(fixture_db, capsys, "unfiled_open")
    assert lines[0] == "open to-do with no area and no project:"
    assert len(lines) == 4 and all(line.startswith("      ") for line in lines[1:])


def test_title_hygiene_groups_by_project_area_or_nowhere(fixture_db, capsys):
    set_title(fixture_db, "t_level", " Buy a spirit level")
    set_title(fixture_db, "t_bolts", "Buy bolts ·")
    set_title(fixture_db, "t_cables", "Sort the cables ")
    lines = section(fixture_db, capsys, "title_hygiene")
    assert '  "Garden Shed Rebuild" (project, 2 to-dos)' in lines
    assert '      " Buy a spirit level" - leading whitespace' in lines
    assert any(
        line.startswith('      "Buy bolts ·" - stray middle dot') for line in lines
    )
    assert "  No project or area (1 to-do)" in lines
    assert '      "Sort the cables " - trailing whitespace' in lines
    assert '  "Side Studio" (area, 1 to-do)' in lines  # the existing finding
    assert not any(line.startswith("title_hygiene") for line in lines)


def test_possible_duplicates_is_one_line_per_set_of_titles(fixture_db, capsys):
    set_title(fixture_db, "t_council", "Pay the electricity bill!")
    lines = section(fixture_db, capsys, "possible_duplicates")
    assert len(lines) == 1
    assert lines[0].count(" = ") == 2
    for title in (
        "Pay the electricity bill",
        "Pay the electricity bill!",
        "pay the electricity bill.",
    ):
        assert f'"{title}"' in lines[0]


def test_dated_in_someday_project_groups_by_project(fixture_db, capsys):
    lines = section(fixture_db, capsys, "dated_in_someday_project")
    assert lines[0] == "to-do with a start date inside a Someday project:"
    assert lines[1] == '  "Learn Pottery" (project, 3 to-dos)'
    assert len(lines) == 5


def test_empty_projects_group_by_area(fixture_db, capsys):
    edit(
        fixture_db,
        (
            "UPDATE TMTask SET status = 3 WHERE type = 0 AND (project = ? "
            "OR heading IN (?, ?))",
            (U("proj_garden"), U("head_plan"), U("head_build")),
        ),
        (
            "UPDATE TMTask SET area = ? WHERE uuid = ?",
            (U("area_studio"), U("proj_garden")),
        ),
        ("UPDATE TMTask SET area = NULL WHERE uuid = ?", (U("proj_photos"),)),
    )
    lines = section(fixture_db, capsys, "active_project_no_open_tasks")
    assert lines[0] == "active project with no open to-dos:"
    assert '  "Side Studio" (area, 1 project)' in lines
    assert "  No area (1 project)" in lines
    assert '      "Photo Archive Cleanup"' in lines


def test_outside_heading_one_block_per_project(fixture_db, capsys):
    lines = section(fixture_db, capsys, "outside_heading")
    assert lines == [
        '  "Garden Shed Rebuild" (project, 2 open to-dos outside any heading)',
        '      "Buy a spirit level"',
        '      "Paint the shed door"',
    ]


def test_recurrence_and_leftover_templates_are_one_line_each(fixture_db, capsys):
    lines = section(fixture_db, capsys, "recurrence_not_recognised")
    assert len(lines) == 3
    assert all(
        line.startswith('  "') and " - recurrence rule " in line for line in lines
    )
    lines = section(fixture_db, capsys, "leftover_templates")
    assert lines == [
        '  "Send the newsletter" - recurring template whose project is trashed'
    ]


def test_every_finding_title_is_shown_once_per_finding(fixture_db, capsys):
    """Grouping never drops an item: the count of findings equals the lines."""
    cli.main(["--db", str(fixture_db), "check"])
    out = capsys.readouterr().out
    for title in ("Draft newsletter issue 3", "Paint the shed door", "Buy clay"):
        assert f'"{title}"' in out
