"""Health checks (DESIGN.md 7.3). Core code: returns findings, never prints."""

from tidyline.checks.finding import CheckOptions, Finding, Ref
from tidyline.checks.registry import (
    CHECK_IDS,
    CHECKS,
    UnknownCheckError,
    run_checks,
    selected,
)

__all__ = [
    "CHECKS",
    "CHECK_IDS",
    "CheckOptions",
    "Finding",
    "Ref",
    "UnknownCheckError",
    "run_checks",
    "selected",
]
