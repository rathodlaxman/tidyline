from checks_helpers import U, findings, ids

CHECK = "recurrence_not_recognised"


def test_hits(fixture_db):
    found = findings(fixture_db, CHECK)
    assert ids(found) == [
        (U("tpl_rrv5"),),
        (U("tpl_unknown_unit"),),
        (U("tpl_invalid_plist"),),
    ]
    assert [f.message for f in found] == [
        "recurrence rule not recognised",
        "recurrence rule not recognised",
        "recurrence rule could not be read",
    ]
    assert all(f.refs[0].kind == "template" for f in found)
    assert all(f.severity == "warning" for f in found)


def test_recognised_and_assumed_rules_are_not_flagged(fixture_db):
    flagged = {f.refs[0].id for f in findings(fixture_db, CHECK)}
    for key in ("tpl_daily", "tpl_monthly_last", "tpl_extra_key", "tpl_leftover"):
        assert U(key) not in flagged, key


def test_trashed_template_is_ignored(fixture_db):
    import sqlite3

    conn = sqlite3.connect(fixture_db)
    conn.execute(
        "UPDATE TMTask SET rt1_recurrenceRule = X'00' WHERE uuid = ?",
        (U("tpl_trashed"),),
    )
    conn.commit()
    conn.close()
    assert U("tpl_trashed") not in {f.refs[0].id for f in findings(fixture_db, CHECK)}
