"""Plain-text report (DESIGN.md 9, v0.1). Returns a string; never prints.

Counts only: no task, project, heading, area or template title appears. The
recurring-templates section gives counts (`tidyline recurrence` shows the
titles). The health-check section lists every check with its finding count,
nothing more; `tidyline check` gives the details.
"""

from __future__ import annotations

import datetime as dt
import unicodedata
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from tidyline.checks import CHECKS, run_checks
from tidyline.model import (
    STATUS_CANCELLED,
    STATUS_COMPLETED,
    Snapshot,
    Task,
    TaskKind,
)
from tidyline.status import Status, effective_status

MAX_WARNING_LINES = 20
RECENT_DAYS = 30
STATUS_ORDER = (
    (Status.INBOX, "Inbox"),
    (Status.TODAY, "Today"),
    (Status.THIS_EVENING, "This Evening"),
    (Status.UPCOMING, "Upcoming"),
    (Status.ANYTIME, "Anytime"),
    (Status.SOMEDAY, "Someday"),
)
BOLD, RESET = "\x1b[1m", "\x1b[0m"


@dataclass(frozen=True)
class ReportOptions:
    include_completed: bool = False
    color: bool = False  # headings in bold; off unless the caller turns it on


def render_report(
    snapshot: Snapshot,
    *,
    today: dt.date,
    tool_version: str,
    environment: Mapping[str, Any],
    options: ReportOptions | None = None,
) -> str:
    """The report as text. `environment` has macos, things_version,
    database_version and tested (a bool)."""
    options = options or ReportOptions()
    out = _Writer(options.color)
    _header(out, today, tool_version, environment)
    _counts(out, snapshot, today, options)
    _recurrence(out, snapshot)
    _warnings(out, snapshot)
    _checks(out, snapshot, today)
    return out.text()


class _Writer:
    def __init__(self, color: bool):
        self.color = color
        self.lines: list[str] = []

    def heading(self, title: str) -> None:
        if self.lines:
            self.lines.append("")
        self.lines.append(f"{BOLD}{title}{RESET}" if self.color else title)
        self.lines.append("-" * len(title))

    def line(self, text: str = "") -> None:
        self.lines.append(text)

    def row(self, label: str, value: object, indent: int = 0) -> None:
        self.lines.append(f"{' ' * indent}{label:<{30 - indent}}{value}")

    def text(self) -> str:
        return "\n".join(self.lines) + "\n"


def _header(out, today, tool_version, environment) -> None:
    out.heading("tidyline report")
    out.row("Date", today.isoformat())
    out.row("tidyline", tool_version)
    out.row("Database version", environment.get("database_version") or "unknown")
    out.row("Things app", environment.get("things_version") or "unknown")
    out.row("macOS", environment.get("macos") or "unknown")
    out.row(
        "Tested versions",
        "yes" if environment.get("tested") else "no (run `tidyline doctor`)",
    )


def _counts(out, snapshot: Snapshot, today: dt.date, options: ReportOptions) -> None:
    tasks = {task.uuid: task for task in snapshot.tasks}

    def project_of(task: Task) -> Task | None:
        owner = task.project_uuid
        if owner is None and task.heading_uuid is not None:
            heading = tasks.get(task.heading_uuid)
            owner = heading.project_uuid if heading else None
        project = tasks.get(owner) if owner else None
        return project if project and project.kind is TaskKind.PROJECT else None

    by_status: Counter[Status] = Counter()
    in_trashed_project = completed = cancelled = trashed = 0
    completed_recent = completed_old = completed_undated = 0
    cutoff = today - dt.timedelta(days=RECENT_DAYS)
    for todo in snapshot.todos:
        if todo.trashed:
            trashed += 1
            continue
        parent = project_of(todo)
        state = effective_status(todo, parent, today)
        if state is Status.CLOSED:
            if todo.status == STATUS_COMPLETED:
                completed += 1
                if todo.stopped is None:
                    completed_undated += 1
                elif todo.stopped.date() >= cutoff:
                    completed_recent += 1
                else:
                    completed_old += 1
            elif todo.status == STATUS_CANCELLED:
                cancelled += 1
        elif parent is not None and parent.trashed:
            in_trashed_project += 1  # hidden in the app; not an open to-do
        else:
            by_status[state] += 1

    projects = snapshot.projects
    out.heading("Counts")
    out.row("Areas", len(snapshot.areas))
    out.row("Projects (open)", sum(1 for p in projects if _is_live(p)))
    out.row("Open to-dos", sum(by_status.values()))
    for state, label in STATUS_ORDER:
        out.row(label, by_status[state], indent=2)
    out.row("Open, in a trashed project", in_trashed_project)
    out.row("Completed to-dos", completed)
    out.row("Cancelled to-dos", cancelled)
    out.row("Trashed to-dos", trashed)

    if options.include_completed:
        out.line()
        out.line("Closed items")
        out.row(f"Completed in last {RECENT_DAYS} days", completed_recent, indent=2)
        out.row("Completed earlier", completed_old, indent=2)
        out.row("Completed, no date", completed_undated, indent=2)
        out.row(
            "Completed projects",
            sum(1 for p in projects if not p.trashed and p.status == STATUS_COMPLETED),
            indent=2,
        )
        out.row(
            "Cancelled projects",
            sum(1 for p in projects if not p.trashed and p.status == STATUS_CANCELLED),
            indent=2,
        )
        out.row("Trashed projects", sum(1 for p in projects if p.trashed), indent=2)


def _checks(out, snapshot: Snapshot, today: dt.date) -> None:
    findings = run_checks(snapshot, today)  # default options: no user patterns
    out.heading("Health checks")
    for check_id, module in CHECKS.items():
        count = sum(1 for f in findings if f.check == check_id)
        out.row(check_id, f"{module.SEVERITY:<9}{count}")
    out.line()
    out.line("Run `tidyline check` for details.")


def _is_live(task: Task) -> bool:
    return not task.trashed and not task.is_closed


def _recurrence(out, snapshot: Snapshot) -> None:
    """Counts only. Titles are shown by `tidyline recurrence`.

    Recognised rules were read and described; of those, Assumed ones rest on a
    convention not yet seen on a real database (DESIGN.md 7.2), the rest were
    verified against what Things shows."""
    leftovers = set(snapshot.leftover_template_uuids)
    templates = snapshot.templates
    not_recognised = sum(1 for t in templates if not t.recurrence.recognised)
    out.heading("Recurring templates")
    out.row("Live", sum(1 for t in templates if t.uuid not in leftovers))
    out.row("Leftover", len(leftovers & {t.uuid for t in templates}))
    out.row("Recognised", sum(1 for t in templates if t.recurrence.recognised))
    out.row(
        "Assumed", sum(1 for t in templates if t.recurrence.confidence == "assumed")
    )
    if not_recognised:
        out.row("Not recognised", not_recognised)
    out.line()
    out.line("Details: tidyline recurrence")


def _warnings(out, snapshot: Snapshot) -> None:
    out.heading("Read warnings")
    if not snapshot.warnings:
        out.line("None.")
        return
    out.line(f"{len(snapshot.warnings)} values could not be read cleanly:")
    for warning in snapshot.warnings[:MAX_WARNING_LINES]:
        out.line(f"  - {_clean(warning)}")
    extra = len(snapshot.warnings) - MAX_WARNING_LINES
    if extra > 0:
        out.line(f"  ... and {extra} more")


def _clean(text: str) -> str:
    """Make a title safe for a terminal: no control characters, one line."""
    if not text:
        return "(untitled)"
    chars = [
        " " if ch in "\r\n\t" else "?" if unicodedata.category(ch) == "Cc" else ch
        for ch in text
    ]
    return "".join(chars).strip() or "(untitled)"
