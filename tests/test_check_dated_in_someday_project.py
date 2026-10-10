from checks_helpers import U, edit, findings, ids

CHECK = "dated_in_someday_project"
PROJECT = U("proj_pottery")


def test_hits(fixture_db):
    found = findings(fixture_db, CHECK)
    # future and past start dates alike
    assert ids(found) == [
        (U("t_clay"), PROJECT),
        (U("t_glaze"), PROJECT),
        (U("t_wheel"), PROJECT),
    ]
    assert {f.message for f in found} == {
        "to-do with a start date inside a Someday project"
    }
    assert [r.kind for r in found[0].refs] == ["task", "project"]


def test_undated_task_in_someday_project_is_not_flagged(fixture_db):
    edit(
        fixture_db,
        ("UPDATE TMTask SET startDate = NULL WHERE uuid = ?", (U("t_clay"),)),
    )
    assert U("t_clay") not in [f.refs[0].id for f in findings(fixture_db, CHECK)]


def test_dated_tasks_in_active_projects_are_not_flagged(fixture_db):
    flagged = {f.refs[0].id for f in findings(fixture_db, CHECK)}
    assert U("t_yesterday") not in flagged  # dated, in an active project
    assert U("t_nextweek") not in flagged  # dated Someday task, area only


def test_through_a_heading(fixture_db):
    edit(
        fixture_db, ("UPDATE TMTask SET start = 2 WHERE uuid = ?", (U("proj_garden"),))
    )
    edit(
        fixture_db,
        (
            "UPDATE TMTask SET startDate = ? WHERE uuid = ?",
            ((2026 << 16) | (11 << 12) | (1 << 7), U("t_bolts")),
        ),
    )
    found = {f.refs[0].id: f for f in findings(fixture_db, CHECK)}
    assert found[U("t_bolts")].refs[1].id == U("proj_garden")


def test_closed_someday_project_is_not_flagged(fixture_db):
    edit(fixture_db, ("UPDATE TMTask SET status = 3 WHERE uuid = ?", (PROJECT,)))
    assert findings(fixture_db, CHECK) == []
