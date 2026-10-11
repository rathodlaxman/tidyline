"""Terminal styling for the text tidyline prints. Never prints itself.

Only the 16 standard ANSI colours are used (bold, bold yellow, bold red), so a
terminal's own light or dark theme decides the shades. Styling is applied only
when the stream it is for is a terminal and `NO_COLOR` is not set; stdout and
stderr are judged separately, so `tidyline check > file` still colours a
warning that goes to a terminal on stderr.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from typing import TextIO

RESET = "\x1b[0m"
BOLD = "\x1b[1m"
BOLD_YELLOW = "\x1b[1;33m"
BOLD_RED = "\x1b[1;31m"


class Style:
    """`bold`, `notice` (yellow bold) and `danger` (red bold); each returns the
    text unchanged when styling is off."""

    def __init__(self, enabled: bool = False):
        self.enabled = enabled

    def _wrap(self, code: str, text: str) -> str:
        return f"{code}{text}{RESET}" if self.enabled and text else text

    def bold(self, text: str) -> str:
        return self._wrap(BOLD, text)

    def notice(self, text: str) -> str:
        return self._wrap(BOLD_YELLOW, text)

    def danger(self, text: str) -> str:
        return self._wrap(BOLD_RED, text)


PLAIN = Style(False)


def style_for(stream: TextIO, environ: Mapping[str, str] | None = None) -> Style:
    """Styling for `stream`: on only for a terminal, and never with NO_COLOR."""
    environ = os.environ if environ is None else environ
    if environ.get("NO_COLOR"):
        return PLAIN
    try:
        return Style(bool(stream.isatty()))
    except (AttributeError, ValueError):  # no isatty, or a closed stream
        return PLAIN


def stdout_style() -> Style:
    return style_for(sys.stdout)


def stderr_style() -> Style:
    return style_for(sys.stderr)
