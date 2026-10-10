import socket

import pytest
from pytest_socket import SocketBlockedError

from tidyline import __version__
from tidyline.cli import main


def test_main_prints_version(capsys):
    main()
    assert capsys.readouterr().out == f"tidyline {__version__}\n"


def test_sockets_are_blocked():
    with pytest.raises(SocketBlockedError):
        socket.socket()
