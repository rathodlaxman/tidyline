from checks_helpers import U, edit, findings, ids

CHECK = "leftover_templates"


def test_hit(fixture_db):
    found = findings(fixture_db, CHECK)
    assert ids(found) == [(U("tpl_leftover"),)]
    assert found[0].message == "recurring template whose project is trashed"
    assert found[0].severity == "info"
    assert found[0].refs[0].kind == "template"


def test_missing_project(fixture_db):
    edit(fixture_db, (
        "UPDATE TMTask SET project = 'gone', area = NULL WHERE uuid = ?",
        (U("tpl_daily"),),
    ))  # fmt: skip
    found = {f.refs[0].id: f for f in findings(fixture_db, CHECK)}
    assert found[U("tpl_daily")].message == (
        "recurring template whose project is missing"
    )


def test_non_hits(fixture_db):
    flagged = {f.refs[0].id for f in findings(fixture_db, CHECK)}
    # area-only template, and a deleted (trashed) template
    assert U("tpl_daily") not in flagged
    assert U("tpl_trashed") not in flagged
