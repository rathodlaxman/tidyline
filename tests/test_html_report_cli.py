"""`tidyline report --html --out FILE` (DESIGN.md 7.7), with the synthetic
fixture only. Sockets are blocked for every test (pyproject addopts)."""

import io
import os
import socket
import stat
import sys

import pytest
from pytest_socket import SocketBlockedError

from tidyline import cli

YELLOW, RED, RESET = "\x1b[1;33m", "\x1b[1;31m", "\x1b[0m"


class FakeTerminal(io.StringIO):
    def isatty(self):
        return True


@pytest.fixture(autouse=True)
def no_real_app(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "THINGS_INFO_PLIST", tmp_path / "missing.plist")
    monkeypatch.delenv("NO_COLOR", raising=False)


def run(fixture_db, *extra):
    return cli.main(["--db", str(fixture_db), "report", "--html", *extra])


def test_writes_a_private_html_file_with_sockets_blocked(fixture_db, tmp_path, capsys):
    with pytest.raises(SocketBlockedError):
        socket.socket()  # the run below happens with the network blocked
    out = tmp_path / "report.html"
    old = os.umask(0)
    try:
        assert run(fixture_db, "--out", str(out)) == 0
    finally:
        os.umask(old)
    assert stat.S_IMODE(out.stat().st_mode) == 0o600
    page = out.read_text(encoding="utf-8")
    assert page.startswith("<!DOCTYPE html>")
    assert "Sort the loose cables" in page  # titles are shown
    captured = capsys.readouterr()
    assert captured.out == f"Wrote the HTML report to {out}\n"
    assert captured.err == (f"\n{cli.HTML_REPORT_NOTE}\n\n")


def test_privacy_note_is_styled_on_a_terminal(fixture_db, tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "stderr", FakeTerminal())
    monkeypatch.setattr(sys, "stdout", io.StringIO())
    assert run(fixture_db, "--out", str(tmp_path / "r.html")) == 0
    err = sys.stderr.getvalue()
    assert err == (
        f"\n{YELLOW}note:{RESET} this file contains your task titles. "
        f"{RED}{cli.KEEP_PRIVATE}{RESET}\n\n"
    )


def test_missing_out_is_refused(fixture_db, capsys):
    assert run(fixture_db) == 2
    err = capsys.readouterr().err
    assert "--html needs --out FILE" in err and "Nothing was written" in err


def test_existing_file_is_refused(fixture_db, tmp_path, capsys):
    out = tmp_path / "report.html"
    out.write_text("keep me")
    assert run(fixture_db, "--out", str(out)) == 2
    assert out.read_text() == "keep me"
    assert "already exists" in capsys.readouterr().err


def test_out_dash_is_refused(fixture_db, capsys):
    assert run(fixture_db, "--out", "-") == 2


def test_last_folder_level_is_created(fixture_db, tmp_path, capsys):
    out = tmp_path / "new" / "report.html"
    assert run(fixture_db, "--out", str(out)) == 0
    assert stat.S_IMODE(out.parent.stat().st_mode) == 0o700
    assert "Created folder" in capsys.readouterr().err


def test_missing_parent_folder_is_refused(fixture_db, tmp_path):
    out = tmp_path / "a" / "b" / "report.html"
    assert run(fixture_db, "--out", str(out)) == 2
    assert not (tmp_path / "a").exists()


def test_include_completed_and_no_color(fixture_db, tmp_path):
    plain = tmp_path / "plain.html"
    closed = tmp_path / "closed.html"
    nocolor = tmp_path / "nocolor.html"
    assert run(fixture_db, "--out", str(plain)) == 0
    assert run(fixture_db, "--out", str(closed), "--include-completed") == 0
    assert run(fixture_db, "--out", str(nocolor), "--no-color") == 0
    assert "Closed items" not in plain.read_text(encoding="utf-8")
    assert "<h3>Closed items</h3>" in closed.read_text(encoding="utf-8")
    assert nocolor.read_text(encoding="utf-8") == plain.read_text(encoding="utf-8")
    assert "\x1b" not in plain.read_text(encoding="utf-8")
