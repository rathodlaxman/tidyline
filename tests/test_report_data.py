"""Core data behind the text and HTML reports (DESIGN.md 7.7): counts, the
check grouping and "Look at this first", against the synthetic fixture."""

import datetime as dt
import re

from checks_helpers import U, snapshot_of
from fixtures import build_fixture as bf

from tidyline.checks import CHECK_IDS, CheckOptions, run_checks
from tidyline.checks.groups import CheckSection, group_findings
from tidyline.report_data import (
    STATUS_ORDER,
    attention,
    build_report,
    template_rows,
)
from tidyline.status import Status

TODAY = dt.date(2026, 10, 10)
ENVIRONMENT = {"macos": None, "things_version": None, "database_version": 29}


def report_of(fixture_db):
    return build_report(
        snapshot_of(fixture_db),
        today=TODAY,
        tool_version="9.9",
        environment=ENVIRONMENT,
    )


def test_counts_match_the_fixture_expectations(fixture_db):
    counts = report_of(fixture_db).counts
    expected = bf.FIXTURE_EXPECTATIONS
    assert counts.areas == expected["areas"]
    assert counts.open_projects == expected["projects"]
    assert counts.open_todos == expected["open_todos"]
    by_status = dict(counts.by_status)
    assert [state for state, _ in counts.by_status] == [s for s, _ in STATUS_ORDER]
    assert by_status[Status.INBOX] == expected["inbox"]
    # "upcoming" and "today" there are things.py's predictions, which ignore
    # the parent project (DESIGN.md 5), so they are not compared here.


def test_every_check_has_a_section_in_registry_order(fixture_db):
    data = report_of(fixture_db)
    assert [s.check for s in data.checks] == list(CHECK_IDS)
    assert all(isinstance(s, CheckSection) for s in data.checks)


def test_sections_keep_titles_as_stored_and_group_by_place(fixture_db):
    snapshot = snapshot_of(fixture_db)
    found = run_checks(snapshot, TODAY, only=["dated_in_someday_project"])
    (section,) = group_findings(found, ["dated_in_someday_project"], snapshot)
    assert section.layout == "groups"
    assert section.message == "to-do with a start date inside a Someday project"
    (group,) = section.groups
    assert group.place.title == "Learn Pottery" and group.place.kind == "project"
    assert [item.things[0].title for item in group.items] == [
        "Buy clay",
        "Choose a glaze palette",
        "Book wheel class",
    ]


def test_user_pattern_text_goes_into_the_note(fixture_db):
    snapshot = snapshot_of(fixture_db)
    found = run_checks(
        snapshot,
        TODAY,
        only=["title_hygiene"],
        options=CheckOptions(patterns=(re.compile("Water"),)),
    )
    (section,) = group_findings(found, ["title_hygiene"], snapshot, ["Water"])
    notes = [item.note for group in section.groups for item in group.items]
    assert "matches user pattern 1 (/Water/)" in notes


def test_attention_names_the_largest_warning_check_first_on_a_tie():
    def section(check, severity, findings):
        return CheckSection(check, severity, findings, "lines", None)

    result = attention(
        (
            section("a", "warning", 3),
            section("b", "warning", 3),
            section("c", "warning", 0),
            section("d", "info", 2),
        )
    )
    assert (result.warnings, result.warning_checks) == (6, 2)
    assert (result.info, result.info_checks) == (2, 1)
    assert result.largest == ("a", 3)
    assert attention((section("d", "info", 1),)).largest is None


def test_template_rows_follow_the_recurrence_command_order(fixture_db):
    rows = template_rows(snapshot_of(fixture_db))
    states = [row.state.split(",")[0] for row in rows]
    assert states == sorted(states, key=("live", "leftover", "not recognised").index)
    leftover = next(r for r in rows if r.uuid == U("tpl_leftover"))
    assert leftover.place.kind == "project" and leftover.place.trashed
