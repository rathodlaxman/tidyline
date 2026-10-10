"""Text report (DESIGN.md 9), against the synthetic fixture only."""

import datetime as dt
import os
import re
import sqlite3
import stat

import pytest
from fixtures import build_fixture as bf

from tidyline import cli
from tidyline.db.snapshot import open_snapshot
from tidyline.read import read_snapshot
from tidyline.render.text import ReportOptions, render_report

FIXED_TODAY = dt.date(2026, 10, 10)
ENVIRONMENT = {
    "macos": "27.0.1",
    "things_version": "3.24.1",
    "database_version": 29,
    "tested": True,
}
U = bf.make_uuid
ESCAPE = re.compile(r"\x1b|\[[0-9;]*m")


def make_report(path, **options):
    with open_snapshot(path) as copy:
        snapshot = read_snapshot(copy)
    text = render_report(
        snapshot,
        today=FIXED_TODAY,
        tool_version="0.1.0",
        environment=ENVIRONMENT,
        options=ReportOptions(**options),
    )
    return snapshot, text


@pytest.fixture
def report_text(fixture_db):
    return make_report(fixture_db)[1]


def value(text, label):
    match = re.search(rf"^\s*{re.escape(label)}\s{{2,}}(.+)$", text, re.M)
    assert match, label
    return match.group(1).strip()


# --- layout -------------------------------------------------------------------


def test_section_order(report_text):
    sections = re.findall(r"^(.+)\n-+$", report_text, re.M)
    assert sections == [
        "tidyline report",
        "Counts",
        "Recurring templates",
        "Read warnings",
        "Health checks",
    ]


def test_header(report_text):
    assert value(report_text, "Date") == "2026-10-10"
    assert value(report_text, "tidyline") == "0.1.0"
    assert value(report_text, "Database version") == "29"
    assert value(report_text, "Things app") == "3.24.1"
    assert value(report_text, "macOS") == "27.0.1"
    assert value(report_text, "Tested versions") == "yes"


def test_untested_versions_are_flagged(fixture_db):
    with open_snapshot(fixture_db) as copy:
        snapshot = read_snapshot(copy)
    text = render_report(
        snapshot,
        today=FIXED_TODAY,
        tool_version="0.1.0",
        environment={"database_version": 30, "tested": False},
    )
    assert value(text, "Tested versions") == "no (run `tidyline doctor`)"
    assert value(text, "Things app") == "unknown"


def test_health_checks_placeholder_is_last(report_text):
    assert report_text.rstrip().endswith(
        "Health checks\n-------------\nHealth checks arrive in v0.2."
    )


def test_ends_with_one_newline(report_text):
    assert report_text.endswith("\n") and not report_text.endswith("\n\n")


# --- counts ---------------------------------------------------------------------


def test_counts_match_the_fixture(report_text):
    expected = {
        "Areas": 2,
        "Projects (open)": bf.FIXTURE_EXPECTATIONS["projects"],
        "Open to-dos": bf.FIXTURE_EXPECTATIONS["open_todos"],
        "Inbox": 1,
        "Today": 4,
        "This Evening": 1,
        "Upcoming": 1,
        "Anytime": 18,
        "Someday": 4,
        "Open, in a trashed project": 1,
        "Completed to-dos": 5,
        "Cancelled to-dos": 1,
        "Trashed to-dos": 1,
    }
    for label, count in expected.items():
        assert value(report_text, label) == str(count), label
    parts = ("Inbox", "Today", "This Evening", "Upcoming", "Anytime", "Someday")
    assert sum(expected[p] for p in parts) == expected["Open to-dos"]


def test_closed_block_only_with_include_completed(fixture_db):
    _, plain = make_report(fixture_db)
    _, full = make_report(fixture_db, include_completed=True)
    assert "Closed items" not in plain
    assert "Closed items" in full
    assert value(full, "Completed in last 30 days") == "5"
    assert value(full, "Completed earlier") == "0"
    assert value(full, "Completed, no date") == "0"
    assert value(full, "Completed projects") == "1"
    assert value(full, "Cancelled projects") == "0"
    assert value(full, "Trashed projects") == "1"
    counts_plain = plain.split("\n\nRecurring")[0]
    assert full.startswith(counts_plain)


def test_completed_recency_uses_today(fixture_db):
    conn = sqlite3.connect(fixture_db)
    old = dt.datetime(2026, 6, 1, tzinfo=dt.timezone.utc).timestamp()
    conn.execute("UPDATE TMTask SET stopDate = ? WHERE uuid = ?", (old, U("t_done")))
    conn.execute(
        "UPDATE TMTask SET stopDate = NULL WHERE uuid = ?", (U("t_photos_done"),)
    )
    conn.commit()
    conn.close()
    _, text = make_report(fixture_db, include_completed=True)
    assert value(text, "Completed in last 30 days") == "3"
    assert value(text, "Completed earlier") == "1"
    assert value(text, "Completed, no date") == "1"


# --- recurrence -----------------------------------------------------------------


def test_recurrence_summary_and_lists(report_text):
    assert value(report_text, "Recognised") == "22"
    assert value(report_text, "Not recognised") == "3"
    assert value(report_text, "Assumed conventions") == "2"
    assert "Live (24)" in report_text
    assert "  - Pay the rent: Monthly on day 15 [verified]" in report_text
    assert "  - Back up the laptop: Monthly on last day [assumed]" in report_text
    assert "  - Mow the lawn: Weekly on Sat (paused) [verified]" in report_text
    assert "recurring (rule unreadable) [unrecognised]" in report_text


def test_leftover_template_is_listed_apart(report_text):
    live, _, leftover = report_text.partition("Leftover: project is trashed")
    assert "Send the newsletter" not in live
    assert leftover.startswith(" or missing (1)\n  - Send the newsletter: Monthly")
    assert "Defrost the freezer" not in report_text  # the trashed template


# --- titles ---------------------------------------------------------------------


def test_no_ordinary_title_appears(fixture_db):
    snapshot, text = make_report(fixture_db, include_completed=True)
    allowed = {t.title for t in snapshot.templates}
    ordinary = {t.title for t in snapshot.tasks if not t.is_template}
    ordinary |= {a.title for a in snapshot.areas} | {t.title for t in snapshot.tags}
    ordinary |= {i.title for i in snapshot.checklist_items}
    ordinary -= allowed  # instances share their template's title
    assert len(ordinary) > 30
    leaked = [title for title in ordinary if title in text]
    assert leaked == []
    for note in ("Ask about the evening slots", "Comprar pimentón", "請求書"):
        assert note not in text


def test_titles_are_made_terminal_safe(fixture_db):
    conn = sqlite3.connect(fixture_db)
    conn.execute(
        "UPDATE TMTask SET title = ? WHERE uuid = ?",
        ("Bad\x1b[31m\ntitle\x07", U("tpl_daily")),
    )
    conn.commit()
    conn.close()
    _, text = make_report(fixture_db)
    assert "  - Bad?[31m title?: Daily [verified]" in text
    assert "\x1b" not in text and "\x07" not in text


def test_empty_title_is_marked(fixture_db):
    conn = sqlite3.connect(fixture_db)
    conn.execute("UPDATE TMTask SET title = '' WHERE uuid = ?", (U("tpl_daily"),))
    conn.commit()
    conn.close()
    assert "  - (untitled): Daily" in make_report(fixture_db)[1]


# --- warnings -----------------------------------------------------------------------


def test_read_warnings_are_listed(fixture_db):
    conn = sqlite3.connect(fixture_db)
    conn.execute(
        "UPDATE TMTask SET startDate = ? WHERE uuid = ?",
        (2026 << 16 | 13 << 12 | 1 << 7, U("t_today")),
    )
    conn.commit()
    conn.close()
    _, text = make_report(fixture_db)
    assert "1 values could not be read cleanly:" in text
    assert f"TMTask {U('t_today')}: startDate" in text
    assert "Water the ferns" not in text


def test_clean_database_has_no_warnings(report_text):
    assert "Read warnings\n-------------\nNone." in report_text


# --- colour -------------------------------------------------------------------------


def test_default_has_no_escape_codes(report_text):
    assert not ESCAPE.search(report_text)


def test_colour_only_on_headings_when_enabled(fixture_db):
    _, text = make_report(fixture_db, color=True)
    assert "\x1b[1mCounts\x1b[0m" in text
    plain = ESCAPE.sub("", text)
    assert plain == make_report(fixture_db)[1]


# --- CLI ------------------------------------------------------------------------------


@pytest.fixture
def no_real_app(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "THINGS_INFO_PLIST", tmp_path / "missing.plist")


def run_report(fixture_db, *extra):
    return cli.main(["--db", str(fixture_db), "report", *extra])


def test_cli_prints_the_report(fixture_db, capsys, no_real_app):
    assert run_report(fixture_db) == 0
    captured = capsys.readouterr()
    assert captured.out.startswith("tidyline report\n")
    assert "Health checks arrive in v0.2." in captured.out
    assert value(captured.out, "Open to-dos") == "29"
    assert value(captured.out, "Database version") == "29"
    assert value(captured.out, "Things app") == "unknown"
    assert captured.err == ""


def test_cli_accepts_db_after_the_command(fixture_db, capsys, no_real_app):
    assert cli.main(["report", "--db", str(fixture_db)]) == 0


def test_cli_include_completed(fixture_db, capsys, no_real_app):
    assert run_report(fixture_db, "--include-completed") == 0
    assert "Closed items" in capsys.readouterr().out


def test_no_color_gives_clean_text_even_on_a_terminal(
    fixture_db, capsys, monkeypatch, no_real_app
):
    import sys

    monkeypatch.delenv("NO_COLOR", raising=False)
    # capsys replaces stdout; make its stream claim to be a terminal
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True, raising=False)
    assert run_report(fixture_db) == 0
    assert "\x1b[1m" in capsys.readouterr().out  # colour on a terminal...
    assert run_report(fixture_db, "--no-color") == 0
    assert not ESCAPE.search(capsys.readouterr().out)  # ...never with --no-color
    monkeypatch.setenv("NO_COLOR", "1")
    assert run_report(fixture_db) == 0
    assert not ESCAPE.search(capsys.readouterr().out)


def test_piped_output_has_no_colour(fixture_db, capsys, no_real_app):
    assert run_report(fixture_db) == 0
    assert not ESCAPE.search(capsys.readouterr().out)


def test_html_is_not_available_yet(fixture_db, tmp_path, capsys, no_real_app):
    out = tmp_path / "report.html"
    assert run_report(fixture_db, "--html", "--out", str(out)) == 2
    assert not out.exists()
    assert "arrives in v0.3" in capsys.readouterr().err


def test_out_writes_a_private_file_and_reminds(
    fixture_db, tmp_path, capsys, no_real_app
):
    out = tmp_path / "report.txt"
    old = os.umask(0)
    try:
        assert run_report(fixture_db, "--out", str(out)) == 0
    finally:
        os.umask(old)
    assert stat.S_IMODE(out.stat().st_mode) == 0o600
    text = out.read_text(encoding="utf-8")
    assert text.startswith("tidyline report\n")
    assert not ESCAPE.search(text)
    captured = capsys.readouterr()
    assert "Wrote the report to" in captured.out
    assert "titles of your recurring tasks" in captured.err
    assert "tidyline report" not in captured.out.split("\n", 1)[0]


def test_out_never_has_colour_on_a_terminal(
    fixture_db, tmp_path, monkeypatch, no_real_app
):
    import sys

    monkeypatch.setattr(sys.stdout, "isatty", lambda: True, raising=False)
    out = tmp_path / "report.txt"
    assert run_report(fixture_db, "--out", str(out)) == 0
    assert not ESCAPE.search(out.read_text(encoding="utf-8"))


def test_out_refuses_to_overwrite(fixture_db, tmp_path, capsys, no_real_app):
    out = tmp_path / "report.txt"
    out.write_text("keep me", encoding="utf-8")
    assert run_report(fixture_db, "--out", str(out)) == 1
    assert out.read_text(encoding="utf-8") == "keep me"
    err = capsys.readouterr().err
    assert "already exists" in err
    assert "Choose a new --out path" in err


def test_out_dash_is_rejected(fixture_db, capsys, no_real_app):
    assert run_report(fixture_db, "--out", "-") == 2
    assert "not supported" in capsys.readouterr().err


def test_out_missing_folder(fixture_db, tmp_path, capsys, no_real_app):
    assert run_report(fixture_db, "--out", str(tmp_path / "no" / "r.txt")) == 1
    assert "does not exist" in capsys.readouterr().err


def test_missing_database(tmp_path, capsys, no_real_app):
    assert cli.main(["--db", str(tmp_path / "none.sqlite"), "report"]) == 1
    assert "error:" in capsys.readouterr().err


def test_help_lists_report(capsys):
    with pytest.raises(SystemExit):
        cli.main(["--help"])
    assert "report" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        cli.main(["report", "--help"])
    out = capsys.readouterr().out
    for option in ("--html", "--out", "--include-completed", "--no-color"):
        assert option in out
