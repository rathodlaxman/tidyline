"""To-dos with a start date inside a Someday project: they will never surface.

The app keeps everything in a Someday project parked, whatever its own dates
say (DESIGN.md 7.1 rule 2).
"""

from __future__ import annotations

import datetime as dt

from tidyline.checks.finding import CheckOptions, Finding, ordered, ref
from tidyline.checks.scope import Scope
from tidyline.model import START_SOMEDAY, Snapshot

CHECK_ID = "dated_in_someday_project"
SEVERITY = "warning"


def run(snapshot: Snapshot, today: dt.date, options: CheckOptions) -> list[Finding]:
    scope = Scope(snapshot)
    findings = []
    for task in ordered(scope.in_scope_todos()):
        if task.start_date is None:
            continue
        project = scope.project(task)
        if project is None or not scope.is_open(project):
            continue
        if project.start != START_SOMEDAY:
            continue
        findings.append(
            Finding(
                CHECK_ID,
                SEVERITY,
                "to-do with a start date inside a Someday project",
                (ref(task), ref(project)),
            )
        )
    return findings
