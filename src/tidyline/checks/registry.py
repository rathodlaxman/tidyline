"""All checks, in report order, and a way to run all or some of them."""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable

from tidyline.checks import (
    active_project_no_open_tasks,
    dated_in_someday_project,
    leftover_templates,
    open_in_trashed_project,
    outside_heading,
    possible_duplicates,
    recurrence_not_recognised,
    someday_in_active_project,
    title_hygiene,
    unfiled_open,
)
from tidyline.checks.finding import CheckOptions, Finding
from tidyline.model import Snapshot

# Report order: the order of the DESIGN.md 7.3 table.
CHECKS = {
    module.CHECK_ID: module
    for module in (
        open_in_trashed_project,
        unfiled_open,
        title_hygiene,
        possible_duplicates,
        dated_in_someday_project,
        active_project_no_open_tasks,
        recurrence_not_recognised,
        leftover_templates,
        someday_in_active_project,
        outside_heading,
    )
}
CHECK_IDS = tuple(CHECKS)


class UnknownCheckError(ValueError):
    pass


def selected(only: Iterable[str] | None = None) -> tuple[str, ...]:
    """The check ids to run, in registry order. Raises for unknown ids."""
    if only is None:
        return CHECK_IDS
    wanted = set(only)
    unknown = sorted(wanted - set(CHECK_IDS))
    if unknown:
        raise UnknownCheckError(
            f"unknown check {', '.join(unknown)}; known checks: {', '.join(CHECK_IDS)}"
        )
    return tuple(check for check in CHECK_IDS if check in wanted)


def run_checks(
    snapshot: Snapshot,
    today: dt.date,
    *,
    only: Iterable[str] | None = None,
    options: CheckOptions | None = None,
) -> list[Finding]:
    options = options or CheckOptions()
    findings: list[Finding] = []
    for check in selected(only):
        findings.extend(CHECKS[check].run(snapshot, today, options))
    return findings
