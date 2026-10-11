"""Readable decoded answers (DESIGN.md 7.5): bare codes, long titles, "|" in
tables, quotes and locations for shared titles.

The label maps here are made by hand; codes use the label alphabet (a-z, 2-7).
"""

import pytest
from checks_helpers import edit, snapshot_of
from fixtures import build_fixture as bf

from tidyline import cli
from tidyline.decode import (
    DecodeResult,
    Item,
    decode_text,
    label_items,
    label_map,
)

U = bf.make_uuid
LABELS = {
    "Task k3f7az": "Call the bank",
    "Task p2q3rs": "Pay the rent",
    "Project m4n5op": "Garden",
    "Area h6j7kl": "Household",
}


def decoded(text, labels=LABELS, items=None):
    return decode_text(text, labels, items).text


# --- bare codes ----


def test_bare_code_in_a_table_cell():
    result = decode_text("| k3f7az | MOVE |", LABELS)
    assert result.text == '| "Call the bank" | MOVE |'
    assert (result.replaced, result.bare_replaced, result.distinct) == (0, 1, 1)


def test_bare_code_in_a_bullet_list():
    assert decoded("- k3f7az\n- p2q3rs\n") == '- "Call the bank"\n- "Pay the rent"\n'


def test_bare_codes_in_a_comma_separated_list():
    assert decoded("Do k3f7az, p2q3rs and m4n5op.") == (
        'Do "Call the bank", "Pay the rent" and "Garden".'
    )


@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        ("**k3f7az**", '**"Call the bank"**'),
        ("*k3f7az*", '*"Call the bank"*'),
        ("_k3f7az_", '_"Call the bank"_'),
        ("__k3f7az__", '__"Call the bank"__'),
        ("`k3f7az`", "`Call the bank`"),
        ("**Task k3f7az**", '**"Call the bank"**'),
        ("`Task k3f7az`", "`Call the bank`"),
    ],
)
def test_markdown_around_codes_and_labels(answer, expected):
    assert decoded(answer) == expected


def test_code_inside_a_longer_word_does_not_match():
    for answer in ("xk3f7azx", "xk3f7az", "k3f7azx", "k3f7az2", "2k3f7az"):
        result = decode_text(answer, LABELS)
        assert result.text == answer
        assert result.bare_replaced == 0


def test_uppercase_does_not_match():
    for answer in ("K3F7AZ", "Task K3F7AZ", "K3f7az", "k3F7az", "Task k3f7aZ"):
        result = decode_text(answer, LABELS)
        assert result.text == answer
        assert (result.replaced, result.bare_replaced) == (0, 0)


def test_unknown_six_letter_words_are_left_alone_and_not_counted():
    result = decode_text("Plant the garden before winter.", LABELS)
    assert result.text == "Plant the garden before winter."
    assert (result.bare_replaced, result.ambiguous, result.unmatched) == (0, (), ())


def test_ambiguous_bare_code_is_left_and_counted():
    labels = {"Task q2w3er": "Call the bank", "Project q2w3er": "Garden"}
    result = decode_text("Start q2w3er, then Project q2w3er; q2w3er again.", labels)
    assert result.text == 'Start q2w3er, then "Garden"; q2w3er again.'
    assert result.ambiguous == ("q2w3er",)
    assert (result.replaced, result.bare_replaced) == (1, 0)


def test_bare_collision_form():
    labels = {"Task abcdef-ghij": "First", "Task abcdef-klmn": "Second"}
    result = decode_text("abcdef-ghij and abcdef-klmn, not abcdef", labels)
    assert result.text == '"First" and "Second", not abcdef'
    assert result.bare_replaced == 2


def test_code_followed_by_a_hyphenated_word():
    assert decoded("k3f7az-done") == '"Call the bank"-done'


def test_title_holding_another_code_is_not_replaced_again():
    labels = {"Task k3f7az": "Ring p2q3rs today", "Task p2q3rs": "Pay the rent"}
    result = decode_text("k3f7az and Task k3f7az", labels)
    assert result.text == '"Ring p2q3rs today" and "Ring p2q3rs today"'
    assert (result.replaced, result.bare_replaced, result.distinct) == (1, 1, 1)


def test_several_labels_in_one_table_cell():
    answer = "| k3f7az, Task p2q3rs; Project m4n5op | Area h6j7kl |"
    assert decoded(answer) == (
        '| "Call the bank", "Pay the rent"; "Garden" | "Household" |'
    )


# --- long titles and whitespace ----


def test_long_title_is_shortened_to_80_characters():
    title = "Write " + "very " * 30 + "long notes"
    result = decoded("k3f7az", {"Task k3f7az": title})
    inner = result[1:-1]
    assert len(inner) == 80
    assert inner == title[:79] + "…"


def test_title_of_exactly_80_characters_is_kept():
    title = "x" * 80
    assert decoded("Task k3f7az", {"Task k3f7az": title}) == f'"{title}"'


def test_whitespace_in_titles_is_collapsed():
    labels = {"Task k3f7az": "Call\n the   bank\t now "}
    assert decoded("k3f7az", labels) == '"Call the bank now"'


# --- "|" in tables ----


def test_pipe_in_a_title_is_escaped_only_on_table_lines():
    labels = {"Task k3f7az": "Compare A|B plans"}
    answer = "| k3f7az | MOVE |\n  | Task k3f7az |\nIn prose: k3f7az | not a table\n"
    assert decoded(answer, labels) == (
        '| "Compare A\\|B plans" | MOVE |\n'
        '  | "Compare A\\|B plans" |\n'
        'In prose: "Compare A|B plans" | not a table\n'
    )


# --- quotes ----


@pytest.mark.parametrize(
    "answer",
    ['"k3f7az"', '"Task k3f7az"', "“k3f7az”", "'Task k3f7az'", "`k3f7az`"],
)
def test_label_already_in_quotes_is_not_wrapped_again(answer):
    assert decoded(answer) == answer[0] + "Call the bank" + answer[-1]


def test_quote_on_one_side_only_still_wraps():
    assert decoded('"k3f7az is next') == '""Call the bank" is next'


# --- shared titles ----

SHARED = {
    "Task a2b3cd": "Sort the mail",
    "Task e4f5gh": "Sort the mail",
    "Task i6j7kl": "Sort the mail",
}


def test_two_open_items_with_one_title_both_get_a_location():
    items = {
        "Task a2b3cd": Item(parent="Household"),
        "Task e4f5gh": Item(parent="Side Studio"),
    }
    labels = {k: v for k, v in SHARED.items() if k in items}
    assert decoded("a2b3cd then Task e4f5gh", labels, items) == (
        '"Sort the mail (in Household)" then "Sort the mail (in Side Studio)"'
    )


def test_a_completed_twin_adds_no_location():
    items = {
        "Task a2b3cd": Item(parent="Household"),
        "Task e4f5gh": Item(parent="Side Studio", in_scope=False),
    }
    labels = {k: v for k, v in SHARED.items() if k in items}
    assert decoded("a2b3cd and e4f5gh", labels, items) == (
        '"Sort the mail" and "Sort the mail"'
    )


def test_location_goes_inside_existing_quotes_and_parent_is_shortened():
    parent = "A project with a rather long name that keeps going on"
    items = {
        "Task a2b3cd": Item(parent=parent),
        "Task e4f5gh": Item(parent="Household"),
        "Task i6j7kl": Item(parent=None),  # no project and no area
    }
    text = decoded('"a2b3cd" / `e4f5gh` / i6j7kl', SHARED, items)
    assert text == (
        f'"Sort the mail (in {parent[:39]}…)" / '
        "`Sort the mail (in Household)` / "
        '"Sort the mail"'
    )


def test_location_pipe_is_escaped_in_a_table():
    items = {
        "Task a2b3cd": Item(parent="Home|Garden"),
        "Task e4f5gh": Item(parent="Studio"),
    }
    labels = {k: v for k, v in SHARED.items() if k in items}
    assert decoded("| a2b3cd |", labels, items) == (
        '| "Sort the mail (in Home\\|Garden)" |'
    )


def test_label_items_scope_on_the_fixture(fixture_db):
    """A completed twin in the database adds no location; an open one does."""
    title = "Buy a spirit level"  # t_level, open, in proj_garden
    edit(fixture_db, (
        "UPDATE TMTask SET title = ? WHERE uuid = ?", (title, U("t_done")),
    ))  # fmt: skip
    snapshot = snapshot_of(fixture_db)
    labels, items = label_map(snapshot), label_items(snapshot)
    level = next(k for k, v in labels.items() if v == title and items[k].in_scope)
    assert decoded(level, labels, items) == f'"{title}"'

    edit(fixture_db, (
        "UPDATE TMTask SET title = ? WHERE uuid = ?", (title, U("t_inbox")),
    ))  # fmt: skip
    snapshot = snapshot_of(fixture_db)
    labels, items = label_map(snapshot), label_items(snapshot)
    assert decoded(level, labels, items) == f'"{title} (in Garden Shed Rebuild)"'


# --- the summary ----


def test_summary_has_counts_only():
    result = DecodeResult(
        text="",
        replaced=3,
        distinct=4,
        unmatched=("Task aaaaaa",),
        bare_replaced=2,
        ambiguous=("q2w3er",),
    )
    summary = cli._decode_summary(result)
    assert summary == (
        "Decoded: 3 labels replaced, 2 bare codes replaced (4 distinct items).\n"
        "1 distinct bare codes were ambiguous (each matches several items) and "
        "were left as they are.\n"
        "1 distinct label-like strings matched nothing in this database and were "
        "left as they are."
    )
    assert "q2w3er" not in summary and "aaaaaa" not in summary
