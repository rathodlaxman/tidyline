"""Live recurring templates whose rule is unreadable or not recognised."""

from __future__ import annotations

import datetime as dt

from tidyline.checks.finding import CheckOptions, Finding, ordered, ref
from tidyline.model import Snapshot
from tidyline.recurrence import UNREADABLE_TEXT

CHECK_ID = "recurrence_not_recognised"
SEVERITY = "warning"


def run(snapshot: Snapshot, today: dt.date, options: CheckOptions) -> list[Finding]:
    findings = []
    for template in ordered(snapshot.templates):  # trashed templates are not read
        rule = template.recurrence
        if rule is None or rule.recognised:
            continue
        message = (
            "recurrence rule could not be read"
            if rule.text == UNREADABLE_TEXT
            else "recurrence rule not recognised"
        )
        findings.append(Finding(CHECK_ID, SEVERITY, message, (ref(template),)))
    return findings
