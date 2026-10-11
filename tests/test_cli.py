import socket
import subprocess
import sys

import pytest
from pytest_socket import SocketBlockedError

from tidyline import __version__
from tidyline.cli import build_parser, main
from tidyline.render.help_out import COMMANDS, render_help
from tidyline.render.style import Style

COMMAND_NAMES = [name for name, _ in COMMANDS]


def test_version_flag(capsys):
    with pytest.raises(SystemExit) as exit_info:
        main(["--version"])
    assert exit_info.value.code == 0
    assert capsys.readouterr().out == f"tidyline {__version__}\n"


def test_no_command_prints_the_help_screen(capsys):
    assert main([]) == 0
    out = capsys.readouterr().out
    assert out.startswith(f"tidyline {__version__}\n")
    for command in COMMAND_NAMES:
        assert f"  {command} " in out
    assert "\x1b" not in out  # piped, so no colour codes
    assert max(len(line) for line in out.splitlines()) <= 80
    assert "New here? Run tidyline doctor, then tidyline report." in out
    assert "Nothing is sent anywhere." in out
    assert (
        "Show them on screen or in the file: check, recurrence, export, decode." in out
    )
    assert "Never show them: report, check --json." in out
    assert "docs/GETTING_STARTED.md" in out


def test_help_screen_blank_lines_when_plain():
    lines = render_help("9.9").split("\n")
    new_here = lines.index("New here? Run tidyline doctor, then tidyline report.")
    assert lines[new_here + 1] == "" and lines[new_here + 2] == "Step-by-step guide:"
    more = lines.index(
        "More detail on any command: tidyline COMMAND --help, or tidyline --help."
    )
    assert lines[more - 1] == "" and lines[more - 2].startswith("  https://")
    assert lines[-1] == "" and "\x1b" not in "\n".join(lines)


def test_help_screen_uses_colour_only_when_asked():
    styled = render_help("9.9", Style(True))
    bold, underline, reset = "\x1b[1m", "\x1b[4m", "\x1b[0m"
    assert f"{bold}tidyline 9.9{reset}\n" in styled
    for heading in ("Commands", "Examples", "Your task titles"):
        assert f"\n{underline}{heading}{reset}\n" in styled
    assert (
        f"{bold}New here?{reset} Run tidyline doctor, then tidyline report.\n" in styled
    )
    assert f"{bold}Step-by-step guide:{reset}\n" in styled
    assert styled.count(bold) == 3 and styled.count(underline) == 3
    assert styled.count(reset) == 6  # nothing else is styled
    assert "\x1b" not in render_help("9.9")


def test_help_screen_colour_follows_terminal_and_no_color(capsys, monkeypatch):
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True, raising=False)
    monkeypatch.delenv("NO_COLOR", raising=False)
    assert main([]) == 0
    assert "\x1b[1m" in capsys.readouterr().out
    monkeypatch.setenv("NO_COLOR", "1")
    assert main([]) == 0
    assert "\x1b" not in capsys.readouterr().out


def test_help_flag_is_still_argparse_output(capsys):
    with pytest.raises(SystemExit) as exit_info:
        main(["--help"])
    assert exit_info.value.code == 0
    assert "usage: tidyline" in capsys.readouterr().out


def test_help_screen_lists_every_registered_command():
    parser = build_parser()
    action = next(a for a in parser._actions if a.dest == "command")
    assert set(COMMAND_NAMES) == set(action.choices)


def test_sockets_are_blocked():
    with pytest.raises(SocketBlockedError):
        socket.socket()


def test_importing_cli_does_not_import_things():
    code = "import sys, tidyline.cli; sys.exit(1 if 'things' in sys.modules else 0)"
    result = subprocess.run([sys.executable, "-I", "-c", code], check=False)
    assert result.returncode == 0
