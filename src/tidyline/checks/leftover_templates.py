"""Live recurring templates whose project is trashed or missing (DESIGN.md 7.2)."""

from __future__ import annotations

import datetime as dt

from tidyline.checks.finding import CheckOptions, Finding, ordered, ref
from tidyline.checks.scope import Scope
from tidyline.model import Snapshot

CHECK_ID = "leftover_templates"
SEVERITY = "info"


def run(snapshot: Snapshot, today: dt.date, options: CheckOptions) -> list[Finding]:
    scope = Scope(snapshot)
    leftovers = set(snapshot.leftover_template_uuids)
    findings = []
    for template in ordered(snapshot.templates):
        if template.uuid not in leftovers:
            continue
        project = scope.project(template)
        message = (
            "recurring template whose project is trashed"
            if project is not None and project.trashed
            else "recurring template whose project is missing"
        )
        findings.append(Finding(CHECK_ID, SEVERITY, message, (ref(template),)))
    return findings
