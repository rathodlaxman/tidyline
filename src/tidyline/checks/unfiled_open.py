"""Open to-dos with no area and no project, outside the Inbox.

A to-do under a heading has a project. Inbox to-dos are unfiled by design, so
a to-do whose effective status is Inbox is not flagged.
"""

from __future__ import annotations

import datetime as dt

from tidyline.checks.finding import CheckOptions, Finding, ordered, ref
from tidyline.checks.scope import Scope
from tidyline.model import Snapshot
from tidyline.status import Status, effective_status

CHECK_ID = "unfiled_open"
SEVERITY = "warning"


def run(snapshot: Snapshot, today: dt.date, options: CheckOptions) -> list[Finding]:
    scope = Scope(snapshot)
    findings = []
    for task in ordered(scope.in_scope_todos()):
        if task.area_uuid or task.project_uuid or task.heading_uuid:
            continue  # a to-do under a heading has a project
        if effective_status(task, None, today) is Status.INBOX:
            continue
        findings.append(
            Finding(CHECK_ID, SEVERITY, "open to-do with no area and no project",
                    (ref(task),))
        )  # fmt: skip
    return findings
