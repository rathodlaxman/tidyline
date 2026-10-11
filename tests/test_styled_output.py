"""Where styling is applied (DESIGN.md decisions log, 2026-10-11), and that it
follows each stream: a fake terminal gets escape codes, a pipe never does, and
NO_COLOR switches it off."""

import io
import sys

import pytest

from tidyline import cli
from tidyline.render.check_out import FIXING_GUIDE_URL

RED, YELLOW, BOLD, RESET = "\x1b[1;31m", "\x1b[1;33m", "\x1b[1m", "\x1b[0m"


class FakeTerminal(io.StringIO):
    def isatty(self):
        return True


@pytest.fixture(autouse=True)
def quiet_env(monkeypatch, tmp_path):
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setattr(cli, "THINGS_INFO_PLIST", tmp_path / "missing.plist")


def run_on_terminal(monkeypatch, argv, *, out=True, err=True):
    stdout = FakeTerminal() if out else io.StringIO()
    stderr = FakeTerminal() if err else io.StringIO()
    monkeypatch.setattr(sys, "stdout", stdout)
    monkeypatch.setattr(sys, "stderr", stderr)
    code = cli.main(argv)
    return code, stdout.getvalue(), stderr.getvalue()


def test_error_prefix_is_red_bold_and_the_message_plain(monkeypatch, tmp_path):
    missing = tmp_path / "none.sqlite"
    code, _, err = run_on_terminal(monkeypatch, ["--db", str(missing), "report"])
    assert code == 3
    assert err.startswith(f"{RED}error:{RESET} ")
    assert err.count("\x1b") == 2  # the prefix only; the message is plain


def test_error_is_plain_when_piped(monkeypatch, tmp_path, capsys):
    assert cli.main(["--db", str(tmp_path / "none.sqlite"), "report"]) == 3
    err = capsys.readouterr().err
    assert err.startswith("error: ") and "\x1b" not in err


def test_error_is_plain_with_no_color(monkeypatch, tmp_path):
    monkeypatch.setenv("NO_COLOR", "1")
    _, _, err = run_on_terminal(monkeypatch, ["--db", str(tmp_path / "x"), "report"])
    assert err.startswith("error: ") and "\x1b" not in err


def test_stdout_and_stderr_are_judged_separately(monkeypatch, tmp_path):
    _, out, err = run_on_terminal(
        monkeypatch, ["--db", str(tmp_path / "x"), "report"], out=False
    )
    assert "\x1b" in err and "\x1b" not in out
    _, _, err = run_on_terminal(
        monkeypatch, ["--db", str(tmp_path / "x"), "report"], err=False
    )
    assert "\x1b" not in err


def test_privacy_note_has_blank_lines_and_styled_parts(
    monkeypatch, fixture_db, tmp_path
):
    out = tmp_path / "r.txt"
    _, _, err = run_on_terminal(
        monkeypatch, ["--db", str(fixture_db), "report", "--out", str(out)]
    )
    note = cli.REPORT_FILE_NOTE
    label, _, body = note.partition(": ")
    sentence = cli.KEEP_PRIVATE
    expected = (
        f"\n{YELLOW}{label}:{RESET} {body[: -len(sentence)]}{RED}{sentence}{RESET}\n\n"
    )
    assert expected in err


def test_privacy_note_plain_when_piped(fixture_db, tmp_path, capsys):
    out = tmp_path / "r.txt"
    assert cli.main(["--db", str(fixture_db), "report", "--out", str(out)]) == 0
    err = capsys.readouterr().err
    assert f"\n{cli.REPORT_FILE_NOTE}\n\n" in err
    assert "\x1b" not in err


def test_every_export_and_decode_note_is_set_apart(fixture_db, tmp_path, capsys):
    for level in ("none", "strict"):
        out = tmp_path / f"{level}.json"
        args = ["--db", str(fixture_db), "export", "--out", str(out)]
        assert cli.main([*args, "--anonymise", level]) == 0
        err = capsys.readouterr().err
        assert "\nnote: " in err and err.endswith("\n\n")
    answer = tmp_path / "answer.md"
    answer.write_text("Task aaaaaa", encoding="utf-8")
    assert cli.main(["--db", str(fixture_db), "decode", str(answer)]) == 0
    err = capsys.readouterr().err
    assert "\nwarning: the decoded text contains real titles" in err
    assert cli.KEEP_PRIVATE in err and err.endswith("\n\n")


def test_check_headings_and_link_line_are_bold(monkeypatch, fixture_db):
    _, out, _ = run_on_terminal(monkeypatch, ["--db", str(fixture_db), "check"])
    assert f"{BOLD}open_in_trashed_project (warning, 3 findings){RESET}\n" in out
    assert out.endswith(f"\n\n{BOLD}How to fix these: {FIXING_GUIDE_URL}{RESET}\n")
    assert out.count(BOLD) == 11  # ten checks and the link line


def test_prompt_preview_labels_are_bold(monkeypatch, fixture_db):
    _, out, _ = run_on_terminal(monkeypatch, ["--db", str(fixture_db), "prompt"])
    for label in (
        "Anonymisation:",
        "Payload counts:",
        "Removed or replaced at this level:",
        "Kept:",
        "Left out (counted in the summary only):",
    ):
        assert f"{BOLD}{label}{RESET}" in out, label
    last = out.rstrip("\n").splitlines()[-1]
    sentence = "Nothing has been sent anywhere. You attach or paste these yourself."
    assert last == f"{BOLD}{sentence}{RESET}"


def test_prompt_preview_written_label_and_warning(monkeypatch, fixture_db, tmp_path):
    out_dir = tmp_path / "files"
    _, out, _ = run_on_terminal(
        monkeypatch, ["--db", str(fixture_db), "prompt", "--out", str(out_dir)]
    )
    assert f"{BOLD}Written:{RESET}" in out
    assert f"{YELLOW}warning:{RESET} these placeholders stay visible" in out


def test_piped_output_has_no_escape_codes_anywhere(fixture_db, tmp_path, capsys):
    for argv in (
        ["check"],
        ["report"],
        ["recurrence", "--raw"],
        ["prompt", "--out", str(tmp_path / "p")],
        [],
    ):
        cli.main(["--db", str(fixture_db), *argv])
        captured = capsys.readouterr()
        assert "\x1b" not in captured.out + captured.err, argv


def test_recurrence_raw_warning_label_is_yellow(monkeypatch, fixture_db):
    _, out, _ = run_on_terminal(
        monkeypatch, ["--db", str(fixture_db), "recurrence", "--raw"]
    )
    assert out.startswith(f"{YELLOW}warning:{RESET} Raw rules may contain")


def test_report_no_color_still_works_on_a_terminal(monkeypatch, fixture_db):
    _, out, _ = run_on_terminal(monkeypatch, ["--db", str(fixture_db), "report"])
    assert f"{BOLD}Counts{RESET}" in out
    _, plain, _ = run_on_terminal(
        monkeypatch, ["--db", str(fixture_db), "report", "--no-color"]
    )
    assert "\x1b" not in plain


def test_help_screen_escape_codes_on_a_terminal_only(monkeypatch):
    _, out, _ = run_on_terminal(monkeypatch, [])
    assert f"{BOLD}New here?{RESET} Run tidyline doctor" in out
    assert "\x1b[4mCommands\x1b[0m" in out


def test_help_screen_has_no_codes_under_no_color(monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    _, out, _ = run_on_terminal(monkeypatch, [])
    assert "\x1b" not in out and "New here? Run tidyline doctor" in out


def test_report_footer_follows_the_terminal(monkeypatch, fixture_db):
    argv = ["--db", str(fixture_db), "report"]
    _, out, _ = run_on_terminal(monkeypatch, argv)
    assert out.endswith(f"Run {BOLD}tidyline check{RESET} for details.\n")
    monkeypatch.setenv("NO_COLOR", "1")
    _, out, _ = run_on_terminal(monkeypatch, argv)
    assert out.endswith("Run `tidyline check` for details.\n")
