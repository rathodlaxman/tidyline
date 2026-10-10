"""Active projects with nothing left to do.

A project that is open, not trashed and not Someday, with no in-scope open
to-do and no live recurring template in it (directly or through a heading).
"""

from __future__ import annotations

import datetime as dt

from tidyline.checks.finding import CheckOptions, Finding, ordered, ref
from tidyline.checks.scope import Scope
from tidyline.model import START_SOMEDAY, Snapshot

CHECK_ID = "active_project_no_open_tasks"
SEVERITY = "warning"


def run(snapshot: Snapshot, today: dt.date, options: CheckOptions) -> list[Finding]:
    scope = Scope(snapshot)
    busy = set()
    for task in scope.in_scope_todos() + list(snapshot.templates):
        project = scope.project(task)
        if project is not None:
            busy.add(project.uuid)
    findings = []
    for project in ordered(scope.open_projects()):
        if project.start == START_SOMEDAY or project.uuid in busy:
            continue
        findings.append(
            Finding(
                CHECK_ID,
                SEVERITY,
                "active project with no open to-dos",
                (ref(project),),
            )
        )
    return findings
