import socket
import subprocess
import sys

import pytest
from pytest_socket import SocketBlockedError

from tidyline import __version__
from tidyline.cli import main


def test_version_flag(capsys):
    with pytest.raises(SystemExit) as exit_info:
        main(["--version"])
    assert exit_info.value.code == 0
    assert capsys.readouterr().out == f"tidyline {__version__}\n"


def test_no_command_prints_help(capsys):
    assert main([]) == 0
    assert "doctor" in capsys.readouterr().out


def test_sockets_are_blocked():
    with pytest.raises(SocketBlockedError):
        socket.socket()


def test_importing_cli_does_not_import_things():
    code = "import sys, tidyline.cli; sys.exit(1 if 'things' in sys.modules else 0)"
    result = subprocess.run([sys.executable, "-I", "-c", code], check=False)
    assert result.returncode == 0
