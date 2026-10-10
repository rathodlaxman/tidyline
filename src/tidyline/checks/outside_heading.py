"""To-dos outside any heading in projects that use headings (a judgement list).

One finding per open project that has at least one non-trashed heading and at
least one in-scope open to-do directly under it with no heading. The project
is the first ref; each such to-do follows.
"""

from __future__ import annotations

import datetime as dt

from tidyline.checks.finding import CheckOptions, Finding, ordered, ref
from tidyline.checks.scope import Scope
from tidyline.model import Snapshot

CHECK_ID = "outside_heading"
SEVERITY = "info"


def run(snapshot: Snapshot, today: dt.date, options: CheckOptions) -> list[Finding]:
    scope = Scope(snapshot)
    with_headings = {h.project_uuid for h in snapshot.headings if not h.trashed}
    loose: dict[str, list] = {}
    for task in ordered(scope.in_scope_todos()):
        if task.heading_uuid is None and task.project_uuid in with_headings:
            loose.setdefault(task.project_uuid, []).append(task)
    findings = []
    for project in ordered(scope.open_projects()):
        tasks = loose.get(project.uuid)
        if not tasks:
            continue
        findings.append(
            Finding(
                CHECK_ID,
                SEVERITY,
                f"{len(tasks)} open to-dos outside any heading in a project "
                "that uses headings",
                (ref(project), *(ref(task) for task in tasks)),
            )
        )
    return findings
