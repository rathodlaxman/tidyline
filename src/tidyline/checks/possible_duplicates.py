"""Open to-dos whose titles match after normalisation.

Titles are compared after Unicode NFKC, casefold, removing every punctuation
character (category P*) and collapsing whitespace. Only in-scope open to-dos
are compared. A title that normalises to nothing is never grouped, and a group
made only of instances of one recurring template is not flagged.
"""

from __future__ import annotations

import datetime as dt
import unicodedata

from tidyline.checks.finding import CheckOptions, Finding, ordered, ref
from tidyline.checks.scope import Scope
from tidyline.model import Snapshot, Task

CHECK_ID = "possible_duplicates"
SEVERITY = "warning"


def normalise(title: str) -> str:
    text = unicodedata.normalize("NFKC", title).casefold()
    text = "".join(c for c in text if not unicodedata.category(c).startswith("P"))
    return " ".join(text.split())


def run(snapshot: Snapshot, today: dt.date, options: CheckOptions) -> list[Finding]:
    groups: dict[str, list[Task]] = {}
    for task in ordered(Scope(snapshot).in_scope_todos()):
        key = normalise(task.title)
        if key:
            groups.setdefault(key, []).append(task)
    findings = []
    for members in groups.values():
        if len(members) < 2:
            continue
        templates = {m.recurrence_template_uuid for m in members}
        if len(templates) == 1 and None not in templates:
            continue  # several instances of one recurring template
        findings.append(
            Finding(
                CHECK_ID,
                SEVERITY,
                f"{len(members)} open to-dos share a normalised title",
                tuple(ref(m) for m in members),
            )
        )
    return findings
