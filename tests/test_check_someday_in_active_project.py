from checks_helpers import U, edit, findings, ids

CHECK = "someday_in_active_project"


def test_hit(fixture_db):
    found = findings(fixture_db, CHECK)
    assert ids(found) == [(U("t_door"), U("proj_garden"))]
    assert found[0].message == "Someday to-do inside an active project"
    assert found[0].severity == "info"


def test_someday_project_and_area_tasks_are_not_flagged(fixture_db):
    flagged = {f.refs[0].id for f in findings(fixture_db, CHECK)}
    assert U("t_clay") not in flagged  # in a Someday project
    assert U("t_nextweek") not in flagged  # area only, no project
    assert U("t_level") not in flagged  # Anytime


def test_someday_task_with_a_future_date_is_upcoming_not_flagged(fixture_db):
    edit(fixture_db, (
        "UPDATE TMTask SET startDate = ? WHERE uuid = ?",
        ((2026 << 16) | (12 << 12) | (1 << 7), U("t_door")),
    ))  # fmt: skip
    assert findings(fixture_db, CHECK) == []


def test_through_a_heading(fixture_db):
    edit(fixture_db, ("UPDATE TMTask SET start = 2 WHERE uuid = ?", (U("t_bolts"),)))
    found = {f.refs[0].id: f for f in findings(fixture_db, CHECK)}
    assert found[U("t_bolts")].refs[1].id == U("proj_garden")
