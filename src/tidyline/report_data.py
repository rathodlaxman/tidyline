"""The numbers and lists behind `report`, text and HTML (DESIGN.md 9 and 7.7).
Core code: returns data, never prints.

Both report renderers draw on `build_report`, and `tidyline recurrence` on
`template_rows`, so every count and every grouping exists once.
"""

from __future__ import annotations

import datetime as dt
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from tidyline.checks import CHECKS, run_checks
from tidyline.checks.groups import CheckSection, group_findings
from tidyline.model import (
    STATUS_CANCELLED,
    STATUS_COMPLETED,
    Snapshot,
    Task,
    TaskKind,
)
from tidyline.status import Status, effective_status

RECENT_DAYS = 30
STATUS_ORDER = (
    (Status.INBOX, "Inbox"),
    (Status.TODAY, "Today"),
    (Status.THIS_EVENING, "This Evening"),
    (Status.UPCOMING, "Upcoming"),
    (Status.ANYTIME, "Anytime"),
    (Status.SOMEDAY, "Someday"),
)
NOT_RECOGNISED = "not recognised"
TEMPLATE_STATES = ("live", "leftover", NOT_RECOGNISED)  # also the sort order


@dataclass(frozen=True)
class Counts:
    """To-do and project counts. Open to-dos inside a trashed project are
    counted apart: the app hides them, so they are not open to-dos."""

    areas: int
    open_projects: int
    by_status: tuple[tuple[Status, int], ...]  # in STATUS_ORDER
    open_in_trashed_project: int
    completed: int
    cancelled: int
    trashed: int
    completed_recent: int  # in the last RECENT_DAYS days
    completed_earlier: int
    completed_undated: int
    completed_projects: int
    cancelled_projects: int
    trashed_projects: int

    @property
    def open_todos(self) -> int:
        return sum(count for _, count in self.by_status)


@dataclass(frozen=True)
class RecurrenceCounts:
    live: int
    leftover: int
    recognised: int
    assumed: int  # recognised, but resting on an unverified convention (7.2)
    not_recognised: int


@dataclass(frozen=True)
class TemplatePlace:
    """Where a template lives. `kind` is "project", "area" or "none"; `title`
    is None when the project or area is not in the snapshot."""

    kind: str
    title: str | None = None
    trashed: bool = False


@dataclass(frozen=True)
class TemplateRow:
    uuid: str
    state: str  # live, leftover, not recognised, or "not recognised, leftover"
    headline: str  # the rule text, or "not recognised"; "(paused)" appended
    title: str
    place: TemplatePlace
    confidence: str  # verified, assumed or unrecognised


@dataclass(frozen=True)
class Attention:
    """What "Look at this first" says: finding totals and the warning check
    with the most findings (the first in registry order on a tie)."""

    warnings: int
    warning_checks: int
    info: int
    info_checks: int
    largest: tuple[str, int] | None


@dataclass(frozen=True)
class ReportData:
    today: dt.date
    tool_version: str
    environment: Mapping[str, Any]
    counts: Counts
    recurrence: RecurrenceCounts
    templates: tuple[TemplateRow, ...]
    checks: tuple[CheckSection, ...]
    attention: Attention
    warnings: tuple[str, ...]


def build_report(
    snapshot: Snapshot,
    *,
    today: dt.date,
    tool_version: str,
    environment: Mapping[str, Any],
) -> ReportData:
    """Everything a report shows. `environment` has macos, things_version,
    database_version and tested (a bool). Checks run with default options."""
    findings = run_checks(snapshot, today)
    sections = tuple(group_findings(findings, tuple(CHECKS), snapshot))
    return ReportData(
        today=today,
        tool_version=tool_version,
        environment=environment,
        counts=count_items(snapshot, today),
        recurrence=recurrence_counts(snapshot),
        templates=tuple(template_rows(snapshot)),
        checks=sections,
        attention=attention(sections),
        warnings=snapshot.warnings,
    )


def count_items(snapshot: Snapshot, today: dt.date) -> Counts:
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
    return Counts(
        areas=len(snapshot.areas),
        open_projects=sum(1 for p in projects if not p.trashed and not p.is_closed),
        by_status=tuple((state, by_status[state]) for state, _ in STATUS_ORDER),
        open_in_trashed_project=in_trashed_project,
        completed=completed,
        cancelled=cancelled,
        trashed=trashed,
        completed_recent=completed_recent,
        completed_earlier=completed_old,
        completed_undated=completed_undated,
        completed_projects=sum(
            1 for p in projects if not p.trashed and p.status == STATUS_COMPLETED
        ),
        cancelled_projects=sum(
            1 for p in projects if not p.trashed and p.status == STATUS_CANCELLED
        ),
        trashed_projects=sum(1 for p in projects if p.trashed),
    )


def recurrence_counts(snapshot: Snapshot) -> RecurrenceCounts:
    """Recognised rules were read and described; of those, assumed ones rest
    on a convention not yet seen on a real database (DESIGN.md 7.2)."""
    leftovers = set(snapshot.leftover_template_uuids)
    templates = snapshot.templates
    return RecurrenceCounts(
        live=sum(1 for t in templates if t.uuid not in leftovers),
        leftover=len(leftovers & {t.uuid for t in templates}),
        recognised=sum(1 for t in templates if t.recurrence.recognised),
        assumed=sum(1 for t in templates if t.recurrence.confidence == "assumed"),
        not_recognised=sum(1 for t in templates if not t.recurrence.recognised),
    )


def template_rows(snapshot: Snapshot) -> list[TemplateRow]:
    """Every template, sorted by state, rule text and id."""
    tasks = {task.uuid: task for task in snapshot.tasks}
    areas = {area.uuid: area.title for area in snapshot.areas}
    leftovers = set(snapshot.leftover_template_uuids)
    rows = [
        TemplateRow(
            uuid=template.uuid,
            state=_state(template, leftovers),
            headline=_headline(template),
            title=template.title,
            place=_place(template, tasks, areas),
            confidence=template.recurrence.confidence,
        )
        for template in snapshot.templates
    ]
    rows.sort(
        key=lambda row: (
            TEMPLATE_STATES.index(row.state.split(",")[0]),
            row.headline,
            row.uuid,
        )
    )
    return rows


def attention(sections: tuple[CheckSection, ...]) -> Attention:
    warned = [s for s in sections if s.severity == "warning" and s.findings]
    informed = [s for s in sections if s.severity == "info" and s.findings]
    largest = None
    for section in warned:
        if largest is None or section.findings > largest[1]:
            largest = (section.check, section.findings)
    return Attention(
        warnings=sum(s.findings for s in warned),
        warning_checks=len(warned),
        info=sum(s.findings for s in informed),
        info_checks=len(informed),
        largest=largest,
    )


def _state(template: Task, leftovers: set[str]) -> str:
    """live, leftover or not recognised; the last wins when more than one applies."""
    leftover = template.uuid in leftovers
    if not template.recurrence.recognised:
        return f"{NOT_RECOGNISED}, leftover" if leftover else NOT_RECOGNISED
    return "leftover" if leftover else "live"


def _headline(template: Task) -> str:
    rule = template.recurrence
    text = rule.text if rule.recognised else NOT_RECOGNISED
    return f"{text} (paused)" if template.recurrence_paused else text


def _place(template: Task, tasks, areas) -> TemplatePlace:
    project_uuid = template.project_uuid
    if project_uuid is None and template.heading_uuid is not None:
        heading = tasks.get(template.heading_uuid)
        project_uuid = heading.project_uuid if heading else None
    if project_uuid is not None:
        project = tasks.get(project_uuid)
        if project is None:
            return TemplatePlace("project")
        return TemplatePlace("project", project.title, project.trashed)
    if template.area_uuid is not None:
        return TemplatePlace("area", areas.get(template.area_uuid))
    return TemplatePlace("none")
