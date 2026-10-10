"""`tidyline recurrence`, against the synthetic fixture only.

To regenerate the golden file after an intended change:
    TIDYLINE_UPDATE_GOLDEN=1 uv run pytest tests/test_recurrence_command.py
and review the diff before committing.
"""

import datetime as dt
import os
import re
import sqlite3
from pathlib import Path

import pytest
from fixtures import build_fixture as bf

from tidyline import cli
from tidyline.db.snapshot import open_snapshot
from tidyline.read import read_snapshot
from tidyline.render.recurrence_out import RAW_WARNING, render_recurrence

GOLDEN = Path(__file__).parent / "fixtures" / "recurrence_golden.txt"
U = bf.make_uuid
SUMMARY = "25 templates, 21 live, 1 leftover, 3 not recognised"


@pytest.fixture(autouse=True)
def no_real_app(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "THINGS_INFO_PLIST", tmp_path / "missing.plist")


def run(fixture_db, capsys, *args):
    code = cli.main(["--db", str(fixture_db), "recurrence", *args])
    return code, capsys.readouterr()


def blocks(text):
    return [b for b in text.rstrip("\n").split("\n\n") if not b.startswith("warning:")]


def block_of(text, title):
    (found,) = [b for b in blocks(text) if f"title:  {title}\n" in b + "\n"]
    return found


# --- default output --------------------------------------------------------------


def test_lists_all_templates_in_stable_order(fixture_db, capsys):
    code, first = run(fixture_db, capsys)
    assert code == 0
    assert first.err == ""
    assert first.out.rstrip("\n").endswith(SUMMARY)
    template_blocks = blocks(first.out)[:-1]
    assert len(template_blocks) == 25 == len(re.findall(r"^  title:", first.out, re.M))
    _, second = run(fixture_db, capsys)
    assert second.out == first.out


def test_order_is_state_then_rule_text_then_id(fixture_db, capsys):
    _, out = run(fixture_db, capsys)
    states = re.findall(r"^  state:  (\S+)", out.out, re.M)
    assert states == ["live"] * 21 + ["leftover"] + ["not"] * 3
    live_headlines = [b.split("\n")[0] for b in blocks(out.out)[:21]]
    assert live_headlines == sorted(live_headlines)


def test_the_three_states(fixture_db, capsys):
    _, out = run(fixture_db, capsys)
    assert "  state:  live" in block_of(out.out, "Pay the rent")
    assert "  state:  leftover" in block_of(out.out, "Send the newsletter")
    assert "  state:  not recognised" in block_of(out.out, "Check the smoke alarms")


def test_a_not_recognised_rule_is_never_described(fixture_db, capsys):
    _, out = run(fixture_db, capsys)
    for title in ("Check the smoke alarms", "Empty the dehumidifier",
                  "Rinse the compost caddy"):  # fmt: skip
        block = block_of(out.out, title)
        assert block.startswith("not recognised\n")
        assert not re.search(
            r"Weekly|Monthly|Daily|Yearly|Every|after completion", block
        )


def test_where_it_lives(fixture_db, capsys):
    _, out = run(fixture_db, capsys)
    assert "  in:     area Household" in block_of(out.out, "Pay the rent")
    assert "  in:     project Old Newsletter (trashed)" in block_of(
        out.out, "Send the newsletter"
    )
    assert "(paused)" in block_of(out.out, "Mow the lawn").split("\n")[0]


def test_where_it_lives_through_a_heading_and_missing_cases(fixture_db, capsys):
    conn = sqlite3.connect(fixture_db)
    conn.execute(
        "UPDATE TMTask SET heading = ?, area = NULL WHERE uuid = ?",
        (U("head_plan"), U("tpl_daily")),
    )
    conn.execute("UPDATE TMTask SET area = NULL WHERE uuid = ?", (U("tpl_weekly_sun"),))
    conn.execute(
        "UPDATE TMTask SET project = 'gone', area = NULL WHERE uuid = ?",
        (U("tpl_monthly_15"),),
    )
    conn.commit()
    conn.close()
    _, out = run(fixture_db, capsys)
    assert "  in:     project Garden Shed Rebuild" in block_of(
        out.out, "Take out the recycling"
    )
    assert "  in:     no project or area" in block_of(out.out, "Plan the week ahead")
    assert "  in:     project (not found)" in block_of(out.out, "Pay the rent")
    assert "state:  leftover" in block_of(out.out, "Pay the rent")


def test_no_next_start_date_line(fixture_db, capsys):
    _, out = run(fixture_db, capsys)
    assert "next" not in out.out.lower()  # the model does not carry one


def test_no_raw_rule_text_without_raw(fixture_db, capsys):
    _, out = run(fixture_db, capsys)
    for marker in ("<?xml", "<plist", "<key>", "bplist", "hex:", "raw rule", "decoded:",
                   "ia =", "sr =", "warning:"):  # fmt: skip
        assert marker not in out.out, marker


def test_matches_the_golden_file(fixture_db, capsys):
    _, out = run(fixture_db, capsys)
    if os.environ.get("TIDYLINE_UPDATE_GOLDEN"):
        GOLDEN.write_text(out.out, encoding="utf-8")
    assert out.out == GOLDEN.read_text(encoding="utf-8")


# --- --raw -------------------------------------------------------------------------


def test_raw_starts_with_the_warning(fixture_db, capsys):
    code, out = run(fixture_db, capsys, "--raw")
    assert code == 0
    assert out.out.startswith(f"warning: {RAW_WARNING}\n\n")
    assert out.out.count("warning:") == 1
    assert out.out.rstrip("\n").endswith(SUMMARY)


def test_raw_shows_the_rule_as_stored_and_the_decoded_fields(fixture_db, capsys):
    _, out = run(fixture_db, capsys, "--raw")
    xml = block_of(out.out, "Pay the rent")
    assert '    <?xml version="1.0" encoding="UTF-8"?>' in xml
    assert "    \t<key>fu</key>" in xml  # as stored, tabs kept
    assert "    unit = month" in xml
    assert "    interval = 1" in xml
    assert "    confidence = verified" in xml
    assert "    of = [{'dy': 14}]" in xml
    assert "    fu = 8" in xml
    # a binary plist is shown as hex with its length
    binary = block_of(out.out, "Water the balcony herbs")
    stored = bf.rule_blobs(dt.date(2026, 10, 10))["tpl_weekly_fri"]
    assert f"    hex: {stored.hex()}" in binary
    assert f"    [{len(stored)} bytes]" in binary


def test_raw_fields_are_in_a_stable_order(fixture_db, capsys):
    _, out = run(fixture_db, capsys, "--raw")
    block = block_of(out.out, "Pay the rent")
    keys = re.findall(r"^    (\w+) = ", block.split("fields in the rule:")[1], re.M)
    assert keys == sorted(keys) and "fu" in keys
    _, again = run(fixture_db, capsys, "--raw")
    assert again.out == out.out


def test_raw_gives_the_reason_for_an_unrecognised_rule(fixture_db, capsys):
    _, out = run(fixture_db, capsys, "--raw")
    unknown_unit = block_of(out.out, "Empty the dehumidifier")
    assert "  reason:\n    unknown unit: fu=999" in unknown_unit
    version = block_of(out.out, "Check the smoke alarms")
    assert "  reason:\n    unknown rule version: rrv=5" in version
    unreadable = block_of(out.out, "Rinse the compost caddy")
    assert "    this is not a plist" in unreadable  # stored text, shown as it is
    assert "  reason:\n    not a readable plist" in unreadable
    recognised = block_of(out.out, "Pay the rent")
    assert "reason:" not in recognised


def test_raw_shows_notes_of_assumed_rules(fixture_db, capsys):
    _, out = run(fixture_db, capsys, "--raw")
    block = block_of(out.out, "Back up the laptop")
    assert "  notes:\n    assumed convention: dy -1" in block


def test_raw_blob_that_is_not_text_is_shown_as_hex(fixture_db, capsys):
    conn = sqlite3.connect(fixture_db)
    junk = b"\xff\xfe\x00junk" + b"\x01" * 20
    conn.execute(
        "UPDATE TMTask SET rt1_recurrenceRule = ? WHERE uuid = ?",
        (junk, U("tpl_daily")),
    )
    conn.commit()
    conn.close()
    _, out = run(fixture_db, capsys, "--raw")
    block = block_of(out.out, "Take out the recycling")
    assert f"    hex: {junk.hex()}" in block
    assert f"    [{len(junk)} bytes]" in block


def test_control_characters_in_titles_are_replaced(fixture_db, capsys):
    conn = sqlite3.connect(fixture_db)
    conn.execute(
        "UPDATE TMTask SET title = ? WHERE uuid = ?",
        ("Bad\x1b[31m title\x07", U("tpl_daily")),
    )
    conn.commit()
    conn.close()
    _, out = run(fixture_db, capsys)
    assert "\x1b" not in out.out and "\x07" not in out.out
    assert "  title:  Bad?[31m title?" in out.out


# --- options and edge cases -------------------------------------------------------


def test_db_after_the_command(fixture_db, capsys):
    assert cli.main(["recurrence", "--db", str(fixture_db)]) == 0
    assert capsys.readouterr().out.rstrip("\n").endswith(SUMMARY)


def test_no_templates(fixture_db, capsys):
    conn = sqlite3.connect(fixture_db)
    conn.execute("DELETE FROM TMTask WHERE rt1_recurrenceRule IS NOT NULL")
    conn.commit()
    conn.close()
    code, out = run(fixture_db, capsys)
    assert code == 0
    assert out.out == "0 templates, 0 live, 0 leftover, 0 not recognised\n"
    code, raw = run(fixture_db, capsys, "--raw")
    assert code == 0 and raw.out.startswith("warning:")
    assert raw.out.rstrip("\n").endswith(
        "0 templates, 0 live, 0 leftover, 0 not recognised"
    )


def test_empty_database(fixture_db, capsys):
    conn = sqlite3.connect(fixture_db)
    for table in ("TMTask", "TMArea", "TMTag", "TMTaskTag", "TMChecklistItem"):
        conn.execute(f"DELETE FROM {table}")
    conn.commit()
    conn.close()
    code, out = run(fixture_db, capsys)
    assert code == 0
    assert out.out.startswith("0 templates")


def test_unrecognised_rules_still_exit_0(fixture_db, capsys):
    code, out = run(fixture_db, capsys)
    assert code == 0 and "3 not recognised" in out.out


def test_missing_database_exits_3(tmp_path, capsys):
    assert cli.main(["--db", str(tmp_path / "none.sqlite"), "recurrence"]) == 3
    assert "error:" in capsys.readouterr().err


def test_never_writes_to_the_database(fixture_db, capsys):
    before = fixture_db.read_bytes()
    run(fixture_db, capsys, "--raw")
    assert fixture_db.read_bytes() == before


def test_unknown_option_is_a_usage_error(fixture_db, capsys):
    with pytest.raises(SystemExit) as error:
        cli.main(["--db", str(fixture_db), "recurrence", "--json"])
    assert error.value.code == 2


def test_render_is_pure(fixture_db):
    with open_snapshot(fixture_db) as copy:
        snapshot = read_snapshot(copy)
    assert render_recurrence(snapshot) == render_recurrence(snapshot)
    assert isinstance(render_recurrence(snapshot, raw=True), str)


def test_help_lists_recurrence(capsys):
    with pytest.raises(SystemExit):
        cli.main(["--help"])
    assert "recurrence" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        cli.main(["recurrence", "--help"])
    out = capsys.readouterr().out
    assert "--raw" in out and "--db" in out
