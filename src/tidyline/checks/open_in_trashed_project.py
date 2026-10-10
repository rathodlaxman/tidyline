"""Open to-dos inside a trashed project or heading.

The app hides them, but they are still open in the database. This is the only
check that looks at them; every other check uses the in-scope to-dos.
"""

from __future__ import annotations

import datetime as dt

from tidyline.checks.finding import CheckOptions, Finding, ordered, ref
from tidyline.checks.scope import Scope
from tidyline.model import Snapshot, TaskKind

CHECK_ID = "open_in_trashed_project"
SEVERITY = "warning"


def run(snapshot: Snapshot, today: dt.date, options: CheckOptions) -> list[Finding]:
    scope = Scope(snapshot)
    findings = []
    for task in ordered(scope.open_todos()):
        container = scope.trashed_container(task)
        if container is None:
            continue
        where = "project" if container.kind is TaskKind.PROJECT else "heading"
        findings.append(
            Finding(
                CHECK_ID,
                SEVERITY,
                f"open to-do inside a trashed {where}",
                (ref(task), ref(container)),
            )
        )
    return findings
