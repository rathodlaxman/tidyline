import re

import pytest
from checks_helpers import U, findings, first_ids, set_title

from tidyline.checks.title_hygiene import problems

CHECK = "title_hygiene"


def test_fixture_hits(fixture_db):
    found = {f.refs[0].id: f for f in findings(fixture_db, CHECK)}
    assert list(found) == [U("t_receipts"), U("t_portfolio")]
    assert found[U("t_receipts")].message == (
        "stray middle dot at the end; doubled spaces"
    )
    assert found[U("t_portfolio")].message == "leading whitespace"


def test_tidy_titles_are_not_flagged(fixture_db):
    flagged = set(first_ids(findings(fixture_db, CHECK)))
    for key in ("t_lease", "t_card", "t_ja", "proj_garden", "t_es"):
        assert U(key) not in flagged, key


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("· Plan", ["stray middle dot at the start"]),
        ("Plan ·", ["stray middle dot at the end"]),
        ("  Plan", ["leading whitespace"]),
        ("Plan\t", ["trailing whitespace"]),
        ("Plan ", ["trailing whitespace"]),
        ("Plan  the  day", ["doubled spaces"]),
        ("Plan　　day", ["doubled spaces"]),
        (" · Plan  it · ", [
            "stray middle dot at the start",
            "stray middle dot at the end",
            "leading whitespace",
            "trailing whitespace",
            "doubled spaces",
        ]),
        ("Plan · the day", []),
        ("Plan the day", []),
        ("·", ["stray middle dot at the start"]),
        ("", []),
    ],
)  # fmt: skip
def test_problems(title, expected):
    assert problems(title) == expected


def test_user_patterns_are_numbered_and_never_quoted(fixture_db):
    patterns = [re.compile(r"^Paint"), re.compile(r"(?i)LEVEL")]
    found = {f.refs[0].id: f for f in findings(fixture_db, CHECK, patterns)}
    assert found[U("t_door")].message == "matches user pattern 1"
    assert found[U("t_level")].message == "matches user pattern 2"
    for finding in found.values():
        assert "Paint" not in finding.message and "LEVEL" not in finding.message


def test_no_patterns_by_default(fixture_db):
    assert U("t_door") not in first_ids(findings(fixture_db, CHECK))


def test_open_projects_are_checked_closed_ones_not(fixture_db):
    set_title(fixture_db, "proj_photos", "Photo  Archive")
    set_title(fixture_db, "proj_done", "Spring Move ·")
    found = {f.refs[0].id: f for f in findings(fixture_db, CHECK)}
    assert found[U("proj_photos")].refs[0].kind == "project"
    assert found[U("proj_photos")].message == "doubled spaces"
    assert U("proj_done") not in found


def test_out_of_scope_to_dos_are_not_checked(fixture_db):
    set_title(fixture_db, "t_done", " Done  ·")
    set_title(fixture_db, "t_in_trashed_project", " Draft  ·")
    set_title(fixture_db, "tpl_daily", " Template  ·")
    flagged = set(first_ids(findings(fixture_db, CHECK)))
    for key in ("t_done", "t_in_trashed_project", "tpl_daily"):
        assert U(key) not in flagged, key
