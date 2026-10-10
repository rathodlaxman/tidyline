"""Untidy titles of open to-dos and projects.

Flags a stray middle dot at the start or end, leading or trailing whitespace,
runs of two or more whitespace characters inside the title, and matches of the
user's own patterns. A pattern match is reported as "matches user pattern N"
(1-based, in the order given); the pattern text never goes into a finding.
"""

from __future__ import annotations

import datetime as dt
import re

from tidyline.checks.finding import CheckOptions, Finding, ordered, ref
from tidyline.checks.scope import Scope
from tidyline.model import Snapshot

CHECK_ID = "title_hygiene"
SEVERITY = "warning"
MIDDLE_DOT = "·"
DOUBLED_SPACE = re.compile(r"\s{2,}")


def problems(title: str, patterns: tuple[re.Pattern[str], ...] = ()) -> list[str]:
    found = []
    core = title.strip()
    if core.startswith(MIDDLE_DOT):
        found.append("stray middle dot at the start")
    if core.endswith(MIDDLE_DOT) and core != MIDDLE_DOT:
        found.append("stray middle dot at the end")
    if title != title.lstrip():
        found.append("leading whitespace")
    if title != title.rstrip():
        found.append("trailing whitespace")
    if DOUBLED_SPACE.search(core):
        found.append("doubled spaces")
    for number, pattern in enumerate(patterns, start=1):
        if pattern.search(title):
            found.append(f"matches user pattern {number}")
    return found


def run(snapshot: Snapshot, today: dt.date, options: CheckOptions) -> list[Finding]:
    scope = Scope(snapshot)
    findings = []
    for task in ordered(scope.open_projects()) + ordered(scope.in_scope_todos()):
        found = problems(task.title, options.patterns)
        if found:
            findings.append(Finding(CHECK_ID, SEVERITY, "; ".join(found), (ref(task),)))
    return findings
