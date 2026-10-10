"""Someday to-dos inside active projects (a judgement list)."""

from __future__ import annotations

import datetime as dt

from tidyline.checks.finding import CheckOptions, Finding, ordered, ref
from tidyline.checks.scope import Scope
from tidyline.model import START_SOMEDAY, Snapshot
from tidyline.status import Status, effective_status

CHECK_ID = "someday_in_active_project"
SEVERITY = "info"


def run(snapshot: Snapshot, today: dt.date, options: CheckOptions) -> list[Finding]:
    scope = Scope(snapshot)
    findings = []
    for task in ordered(scope.in_scope_todos()):
        project = scope.project(task)
        if project is None or not scope.is_open(project):
            continue
        if project.start == START_SOMEDAY:
            continue
        if effective_status(task, project, today) is not Status.SOMEDAY:
            continue
        findings.append(
            Finding(
                CHECK_ID,
                SEVERITY,
                "Someday to-do inside an active project",
                (ref(task), ref(project)),
            )
        )
    return findings
