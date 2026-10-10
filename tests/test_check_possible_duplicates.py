from checks_helpers import U, edit, findings, ids, set_title

from tidyline.checks.possible_duplicates import normalise

CHECK = "possible_duplicates"


def test_fixture_hit(fixture_db):
    found = findings(fixture_db, CHECK)
    assert ids(found) == [(U("t_dup_a"), U("t_dup_b"))]
    assert found[0].message == "2 open to-dos share a normalised title"
    assert found[0].severity == "warning"


def test_near_titles_are_not_grouped(fixture_db):
    flagged = {i for group in ids(findings(fixture_db, CHECK)) for i in group}
    assert U("t_council") not in flagged  # "Check council tax bill"


def test_normalise():
    # punctuation is removed, not replaced, so a hyphen joins the words
    assert normalise("electricity-bill") == "electricitybill"
    assert normalise("Pay the electricity bill") == normalise(
        "pay the electricity bill."
    )
    assert normalise("Ｂuy a ﬁrst card") == "buy a first card"
    assert normalise("Café") == normalise("Café")
    assert normalise("STRASSE") == normalise("straße")
    assert normalise("  a ,  b  ") == "a b"
    assert normalise("Pay €5") != normalise("Pay 5")  # symbols are kept
    assert normalise("...!?") == ""


def test_groups_of_three_reference_every_member(fixture_db):
    set_title(fixture_db, "t_council", "PAY the electricity bill!")
    found = findings(fixture_db, CHECK)
    assert len(found) == 1
    assert set(ids(found)[0]) == {U("t_dup_a"), U("t_dup_b"), U("t_council")}
    assert found[0].message == "3 open to-dos share a normalised title"


def test_titles_that_normalise_to_nothing_are_never_grouped(fixture_db):
    set_title(fixture_db, "t_lease", "...")
    set_title(fixture_db, "t_cables", "!!")
    set_title(fixture_db, "t_level", "")
    assert ids(findings(fixture_db, CHECK)) == [(U("t_dup_a"), U("t_dup_b"))]


def test_instances_of_one_template_are_not_flagged(fixture_db):
    edit(fixture_db, (
        "INSERT INTO TMTask (uuid, type, status, trashed, title, start, area, "
        '"index", startBucket, rt1_repeatingTemplate) '
        "VALUES (?, 0, 0, 0, ?, 1, ?, 500, 0, ?)",
        (U("tpl_daily:instance2"), "Take out the recycling", U("area_home"),
         U("tpl_daily")),
    ))  # fmt: skip
    assert ids(findings(fixture_db, CHECK)) == [(U("t_dup_a"), U("t_dup_b"))]


def test_an_instance_and_an_ordinary_task_are_flagged(fixture_db):
    set_title(fixture_db, "t_lease", "take out the recycling")
    found = ids(findings(fixture_db, CHECK))
    assert (U("tpl_daily:instance"), U("t_lease")) in [
        tuple(sorted(g, key=lambda i: i != U("tpl_daily:instance"))) for g in found
    ]


def test_out_of_scope_to_dos_are_not_compared(fixture_db):
    set_title(fixture_db, "t_done", "Pay the electricity bill")
    set_title(fixture_db, "t_in_trashed_project", "Pay the electricity bill")
    assert ids(findings(fixture_db, CHECK)) == [(U("t_dup_a"), U("t_dup_b"))]
