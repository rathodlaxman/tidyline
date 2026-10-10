from checks_helpers import U, edit, findings, ids

CHECK = "active_project_no_open_tasks"


def test_hit(fixture_db):
    found = findings(fixture_db, CHECK)
    # Photo Archive Cleanup holds only a completed to-do
    assert ids(found) == [(U("proj_photos"),)]
    assert found[0].message == "active project with no open to-dos"
    assert found[0].refs[0].kind == "project"


def test_non_hits(fixture_db):
    flagged = {f.refs[0].id for f in findings(fixture_db, CHECK)}
    for key in ("proj_admin_home", "proj_garden", "proj_pottery", "proj_done",
                "proj_trashed"):  # fmt: skip
        assert U(key) not in flagged, key


def test_a_live_template_counts_as_open_work(fixture_db):
    edit(fixture_db, (
        "UPDATE TMTask SET project = ?, area = NULL WHERE uuid = ?",
        (U("proj_photos"), U("tpl_weekly_sat")),
    ))  # fmt: skip
    assert findings(fixture_db, CHECK) == []


def test_a_trashed_template_does_not_count(fixture_db):
    edit(fixture_db, (
        "UPDATE TMTask SET project = ?, area = NULL WHERE uuid = ?",
        (U("proj_photos"), U("tpl_trashed")),
    ))  # fmt: skip
    assert ids(findings(fixture_db, CHECK)) == [(U("proj_photos"),)]


def test_to_do_under_a_heading_counts(fixture_db):
    edit(
        fixture_db,
        ("UPDATE TMTask SET status = 3 WHERE uuid IN (?, ?)",
         (U("t_level"), U("t_door"))),
    )  # fmt: skip
    # Garden still has open to-dos under its headings
    assert U("proj_garden") not in {f.refs[0].id for f in findings(fixture_db, CHECK)}
    edit(
        fixture_db,
        ("UPDATE TMTask SET status = 3 WHERE heading IN (?, ?)",
         (U("head_plan"), U("head_build"))),
    )  # fmt: skip
    assert U("proj_garden") in {f.refs[0].id for f in findings(fixture_db, CHECK)}


def test_someday_project_is_not_flagged(fixture_db):
    edit(
        fixture_db, ("UPDATE TMTask SET start = 2 WHERE uuid = ?", (U("proj_photos"),))
    )
    assert findings(fixture_db, CHECK) == []
