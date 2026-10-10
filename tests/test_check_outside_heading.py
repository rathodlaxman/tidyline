from checks_helpers import U, edit, findings, ids

CHECK = "outside_heading"


def test_hit_one_finding_per_project(fixture_db):
    found = findings(fixture_db, CHECK)
    assert ids(found) == [(U("proj_garden"), U("t_level"), U("t_door"))]
    assert [r.kind for r in found[0].refs] == ["project", "task", "task"]
    assert found[0].message == (
        "2 open to-dos outside any heading in a project that uses headings"
    )
    assert found[0].severity == "info"


def test_projects_without_headings_are_not_flagged(fixture_db):
    flagged = {f.refs[0].id for f in findings(fixture_db, CHECK)}
    assert U("proj_admin_home") not in flagged


def test_no_finding_when_every_to_do_is_under_a_heading(fixture_db):
    edit(fixture_db, (
        "UPDATE TMTask SET project = NULL, heading = ? WHERE uuid IN (?, ?)",
        (U("head_build"), U("t_level"), U("t_door")),
    ))  # fmt: skip
    assert findings(fixture_db, CHECK) == []


def test_trashed_headings_do_not_count(fixture_db):
    edit(
        fixture_db,
        ("UPDATE TMTask SET trashed = 1 WHERE uuid IN (?, ?)",
         (U("head_plan"), U("head_build"))),
    )  # fmt: skip
    assert findings(fixture_db, CHECK) == []


def test_closed_project_is_not_eligible(fixture_db):
    edit(
        fixture_db, ("UPDATE TMTask SET status = 3 WHERE uuid = ?", (U("proj_garden"),))
    )
    assert findings(fixture_db, CHECK) == []


def test_closed_and_trashed_loose_to_dos_are_left_out(fixture_db):
    edit(
        fixture_db,
        ("UPDATE TMTask SET status = 3 WHERE uuid = ?", (U("t_level"),)),
    )
    assert ids(findings(fixture_db, CHECK)) == [(U("proj_garden"), U("t_door"))]
