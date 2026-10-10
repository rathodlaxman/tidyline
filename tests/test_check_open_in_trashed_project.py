from checks_helpers import U, edit, findings, ids

CHECK = "open_in_trashed_project"


def test_hit(fixture_db):
    found = findings(fixture_db, CHECK)
    assert ids(found) == [(U("t_in_trashed_project"), U("proj_trashed"))]
    finding = found[0]
    assert finding.severity == "warning"
    assert finding.message == "open to-do inside a trashed project"
    assert [r.kind for r in finding.refs] == ["task", "project"]


def test_non_hits(fixture_db):
    flagged = {f.refs[0].id for f in findings(fixture_db, CHECK)}
    for key in (
        "t_level",
        "t_measure",
        "t_trashed",
        "t_in_done_project",
        "tpl_leftover",
    ):
        assert U(key) not in flagged, key


def test_closed_to_do_in_a_trashed_project_is_not_flagged(fixture_db):
    edit(
        fixture_db,
        ("UPDATE TMTask SET status = 3 WHERE uuid = ?", (U("t_in_trashed_project"),)),
    )
    assert findings(fixture_db, CHECK) == []


def test_trashed_heading_and_heading_of_a_trashed_project(fixture_db):
    edit(
        fixture_db,
        ("UPDATE TMTask SET trashed = 1 WHERE uuid = ?", (U("head_plan"),)),
        ("UPDATE TMTask SET trashed = 1 WHERE uuid = ?", (U("proj_garden"),)),
    )
    found = {f.refs[0].id: f for f in findings(fixture_db, CHECK)}
    measure = found[U("t_measure")]  # its heading is trashed (checked first)
    assert measure.message == "open to-do inside a trashed heading"
    assert [r.kind for r in measure.refs] == ["task", "heading"]
    bolts = found[U("t_bolts")]  # heading fine, the heading's project trashed
    assert bolts.refs[1].id == U("proj_garden")
    assert found[U("t_level")].message == "open to-do inside a trashed project"
