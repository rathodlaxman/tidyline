"""Styling is applied only to a terminal and never with NO_COLOR."""

import io

from tidyline.render.style import PLAIN, Style, style_for


class FakeTerminal(io.StringIO):
    def isatty(self):
        return True


def test_plain_when_piped():
    style = style_for(io.StringIO(), {})
    for method in (style.bold, style.notice, style.danger):
        assert method("text") == "text"


def test_escape_codes_on_a_terminal():
    style = style_for(FakeTerminal(), {})
    assert style.bold("a") == "\x1b[1ma\x1b[0m"
    assert style.notice("a") == "\x1b[1;33ma\x1b[0m"
    assert style.danger("a") == "\x1b[1;31ma\x1b[0m"


def test_only_standard_sixteen_colours():
    style = Style(True)
    for text in (style.bold("a"), style.notice("a"), style.danger("a")):
        assert "38;" not in text and "48;" not in text  # no 256 or true colour


def test_no_color_wins_on_a_terminal():
    assert style_for(FakeTerminal(), {"NO_COLOR": "1"}) is PLAIN
    assert style_for(FakeTerminal(), {"NO_COLOR": ""}).enabled  # empty is unset


def test_empty_text_gets_no_codes():
    assert Style(True).bold("") == ""


def test_stream_without_isatty_or_closed_is_plain():
    closed = io.StringIO()
    closed.close()
    assert not style_for(closed, {}).enabled
    assert not style_for(object(), {}).enabled  # type: ignore[arg-type]


def test_stdout_and_stderr_are_judged_separately(monkeypatch):
    import sys

    from tidyline.render import style

    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setattr(sys, "stdout", io.StringIO())
    monkeypatch.setattr(sys, "stderr", FakeTerminal())
    assert not style.stdout_style().enabled
    assert style.stderr_style().enabled
    monkeypatch.setenv("NO_COLOR", "1")
    assert not style.stderr_style().enabled
