"""The check framework: Finding, registry, scope."""

import dataclasses
import json

import pytest
from checks_helpers import TODAY, U, edit, snapshot_of

from tidyline.checks import (
    CHECK_IDS,
    CHECKS,
    CheckOptions,
    Finding,
    Ref,
    UnknownCheckError,
    run_checks,
    selected,
)
from tidyline.checks.scope import Scope
from tidyline.render.check_out import check_json


def test_registry_order_and_modules():
    # the order of the DESIGN.md 7.3 table
    assert CHECK_IDS == (
        "open_in_trashed_project",
        "unfiled_open",
        "title_hygiene",
        "possible_duplicates",
        "dated_in_someday_project",
        "active_project_no_open_tasks",
        "recurrence_not_recognised",
        "leftover_templates",
        "someday_in_active_project",
        "outside_heading",
    )
    severities = {c: m.SEVERITY for c, m in CHECKS.items()}
    assert [c for c, s in severities.items() if s == "info"] == [
        "leftover_templates",
        "someday_in_active_project",
        "outside_heading",
    ]
    for check_id, module in CHECKS.items():
        assert module.CHECK_ID == check_id
        assert module.SEVERITY in ("warning", "info")
        assert callable(module.run)


def test_finding_is_frozen():
    finding = Finding("x", "warning", "m", (Ref("task", "a"),))
    with pytest.raises(dataclasses.FrozenInstanceError):
        finding.message = "changed"
    hash(finding)


def test_selected_and_unknown():
    assert selected() == CHECK_IDS
    assert selected(["possible_duplicates", "unfiled_open"]) == (
        "unfiled_open",
        "possible_duplicates",
    )
    with pytest.raises(UnknownCheckError, match="unknown check nope"):
        selected(["nope"])


def test_run_all_and_subset(fixture_db):
    snapshot = snapshot_of(fixture_db)
    everything = run_checks(snapshot, TODAY)
    assert [f.check for f in everything] == sorted(
        (f.check for f in everything), key=CHECK_IDS.index
    )
    assert {f.check for f in everything} == set(CHECK_IDS)
    only = run_checks(snapshot, TODAY, only=["unfiled_open"])
    assert only and {f.check for f in only} == {"unfiled_open"}
    assert only == [f for f in everything if f.check == "unfiled_open"]


def test_findings_never_carry_titles(fixture_db):
    snapshot = snapshot_of(fixture_db)
    found = run_checks(snapshot, TODAY)
    text = json.dumps(check_json(found, CHECK_IDS), ensure_ascii=False)
    titles = {t.title.strip() for t in snapshot.tasks if t.title.strip()}
    assert [t for t in titles if t in text] == []
    for finding in found:
        assert all(len(r.id) == 22 for r in finding.refs)


def test_checks_return_data_and_do_not_print(fixture_db, capsys):
    run_checks(snapshot_of(fixture_db), TODAY, options=CheckOptions())
    assert capsys.readouterr() == ("", "")


# --- scope -------------------------------------------------------------------------


def test_in_scope_excludes_closed_trashed_templates_and_trashed_projects(fixture_db):
    scope = Scope(snapshot_of(fixture_db))
    in_scope = {t.uuid for t in scope.in_scope_todos()}
    for key in ("t_done", "t_cancelled", "t_trashed", "t_in_trashed_project"):
        assert U(key) not in in_scope, key
    assert U("tpl_daily") not in in_scope  # template
    assert U("tpl_daily:instance") in in_scope  # its open instance is in scope
    assert U("t_measure") in in_scope  # under a heading in a live project
    assert len(in_scope) == 29  # FIXTURE_EXPECTATIONS["open_todos"]


def test_trashed_heading_puts_its_to_dos_out_of_scope(fixture_db):
    edit(
        fixture_db, ("UPDATE TMTask SET trashed = 1 WHERE uuid = ?", (U("head_plan"),))
    )
    scope = Scope(snapshot_of(fixture_db))
    in_scope = {t.uuid for t in scope.in_scope_todos()}
    assert U("t_measure") not in in_scope
    assert U("t_bolts") in in_scope  # the other heading


def test_project_through_a_heading(fixture_db):
    scope = Scope(snapshot_of(fixture_db))
    measure = scope.tasks[U("t_measure")]
    assert measure.project_uuid is None
    assert scope.project(measure).uuid == U("proj_garden")
