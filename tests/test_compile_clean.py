"""Every module compiles without a SyntaxWarning (an invalid escape such as
"\\|" in a plain string warns when pip compiles the package at install time).
Python 3.10 to 3.11 report that as a DeprecationWarning, 3.12 and later as a
SyntaxWarning; both are errors here."""

import warnings
from pathlib import Path

import pytest

import tidyline

SOURCES = sorted(Path(tidyline.__file__).parent.rglob("*.py"))


def test_sources_were_found():
    assert len(SOURCES) > 20


@pytest.mark.parametrize("path", SOURCES, ids=lambda p: p.name)
def test_module_compiles_without_warnings(path):
    with warnings.catch_warnings():
        warnings.simplefilter("error", SyntaxWarning)
        warnings.simplefilter("error", DeprecationWarning)
        compile(path.read_bytes(), str(path), "exec", dont_inherit=True)
