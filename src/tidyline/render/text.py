"""Plain-text report (DESIGN.md 9, v0.1). Returns a string; never prints.

Counts only: no task, project, heading, area or template title appears. The
recurring-templates section gives counts (`tidyline recurrence` shows the
titles). The health-check section lists every check with its finding count,
nothing more; `tidyline check` gives the details. The numbers come from
`report_data`, which the HTML report uses too.
"""

from __future__ import annotations

import datetime as dt
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from tidyline.model import Snapshot
from tidyline.render.style import Style
from tidyline.report_data import (
    RECENT_DAYS,
    STATUS_ORDER,
    Counts,
    RecurrenceCounts,
    ReportData,
    build_report,
)

MAX_WARNING_LINES = 20


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
    data = build_report(
        snapshot, today=today, tool_version=tool_version, environment=environment
    )
    out = _Writer(options.color)
    _header(out, today, tool_version, environment)
    _counts(out, data.counts, options)
    _recurrence(out, data.recurrence)
    _warnings(out, data.warnings)
    _checks(out, data)
    return out.text()


class _Writer:
    def __init__(self, color: bool):
        self.style = Style(color)
        self.lines: list[str] = []

    def heading(self, title: str) -> None:
        if self.lines:
            self.lines.append("")
        self.lines.append(self.style.bold(title))
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


def _counts(out, counts: Counts, options: ReportOptions) -> None:
    out.heading("Counts")
    out.row("Areas", counts.areas)
    out.row("Projects (open)", counts.open_projects)
    out.row("Open to-dos", counts.open_todos)
    labels = dict(STATUS_ORDER)
    for state, number in counts.by_status:
        out.row(labels[state], number, indent=2)
    out.row("Open, in a trashed project", counts.open_in_trashed_project)
    out.row("Completed to-dos", counts.completed)
    out.row("Cancelled to-dos", counts.cancelled)
    out.row("Trashed to-dos", counts.trashed)

    if options.include_completed:
        out.line()
        out.line("Closed items")
        out.row(
            f"Completed in last {RECENT_DAYS} days", counts.completed_recent, indent=2
        )
        out.row("Completed earlier", counts.completed_earlier, indent=2)
        out.row("Completed, no date", counts.completed_undated, indent=2)
        out.row("Completed projects", counts.completed_projects, indent=2)
        out.row("Cancelled projects", counts.cancelled_projects, indent=2)
        out.row("Trashed projects", counts.trashed_projects, indent=2)


def _checks(out, data: ReportData) -> None:
    out.heading("Health checks")
    for section in data.checks:
        out.row(section.check, f"{section.severity:<9}{section.findings}")
    out.line()
    if out.style.enabled:
        out.line(f"Run {out.style.bold('tidyline check')} for details.")
    else:
        out.line("Run `tidyline check` for details.")


def _recurrence(out, counts: RecurrenceCounts) -> None:
    """Counts only. Titles are shown by `tidyline recurrence`."""
    out.heading("Recurring templates")
    out.row("Live", counts.live)
    out.row("Leftover", counts.leftover)
    out.row("Recognised", counts.recognised)
    out.row("Assumed", counts.assumed)
    if counts.not_recognised:
        out.row("Not recognised", counts.not_recognised)
    out.line()
    out.line("Details: tidyline recurrence")


def _warnings(out, warnings: tuple[str, ...]) -> None:
    out.heading("Read warnings")
    if not warnings:
        out.line("None.")
        return
    out.line(f"{len(warnings)} values could not be read cleanly:")
    for warning in warnings[:MAX_WARNING_LINES]:
        out.line(f"  - {_clean(warning)}")
    extra = len(warnings) - MAX_WARNING_LINES
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
