"""How the findings of each check are grouped for people to read (DESIGN.md
7.3, the 2026-10-11 layout row, and 7.7). Core code: returns data, never prints.

The text output of `check` and the HTML report both render these sections, so
the grouping exists once. Titles are looked up here and returned as stored;
each renderer makes them safe for its own medium.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from tidyline.checks.finding import Finding
from tidyline.checks.registry import CHECKS
from tidyline.model import Snapshot, Task

USER_PATTERN = re.compile(r"matches user pattern (\d+)")
KIND_LABELS = {
    "task": "to-do",
    "project": "project",
    "heading": "heading",
    "template": "template",
}

# groups: items under a heading per place; list: the shared message, then the
# items; lines: one line per finding, with its own message when it has one.
Layout = Literal["groups", "list", "lines"]


@dataclass(frozen=True)
class Named:
    """Something shown by its title. `title` is None when the id is not in the
    snapshot."""

    id: str
    kind: str  # "project", "area", "heading", "to-do" or "template"
    title: str | None


@dataclass(frozen=True)
class Item:
    """One finding as shown: usually one thing; a set of possible duplicates
    has several. `note` is the finding's own message when it differs from
    finding to finding."""

    things: tuple[Named, ...]
    note: str | None = None


@dataclass(frozen=True)
class Group:
    """Items under one place. `place` is None for the "nowhere" group, which is
    labelled `nowhere`. The heading counts the items with `noun`, then adds
    `suffix`."""

    place: Named | None
    nowhere: str
    noun: str
    items: tuple[Item, ...]
    suffix: str = ""


@dataclass(frozen=True)
class CheckSection:
    check: str
    severity: str
    findings: int
    layout: Layout
    message: str | None  # the message shared by every finding, shown once
    groups: tuple[Group, ...] = ()  # layout "groups"
    items: tuple[Item, ...] = ()  # layouts "list" and "lines"


def group_findings(
    findings: Sequence[Finding],
    checks: Sequence[str],
    snapshot: Snapshot,
    patterns: Sequence[str] = (),
) -> list[CheckSection]:
    """One section per check in `checks`, in that order, including checks with
    no findings. `patterns` are the user's `--pattern` texts, shown next to
    "matches user pattern N"."""
    lookup = _Lookup(
        {task.uuid: task for task in snapshot.tasks},
        {area.uuid: area.title for area in snapshot.areas},
        tuple(patterns),
    )
    sections = []
    for check in checks:
        found = [f for f in findings if f.check == check]
        severity = CHECKS[check].SEVERITY
        if not found:
            sections.append(CheckSection(check, severity, 0, "lines", None))
            continue
        layout, message, groups, items = SECTIONS.get(check, _one_line_each)(
            found, lookup
        )
        sections.append(
            CheckSection(
                check,
                severity,
                len(found),
                layout,
                message,
                tuple(groups),
                tuple(items),
            )
        )
    return sections


@dataclass(frozen=True)
class _Lookup:
    tasks: dict[str, Task]
    areas: dict[str, str]
    patterns: tuple[str, ...]

    def named(self, uuid: str, kind: str) -> Named:
        task = self.tasks.get(uuid)
        return Named(uuid, kind, task.title if task is not None else None)

    def place(self, task: Task) -> Named | None:
        """Where a to-do lives: its project (through its heading), else its
        area, else nowhere (None)."""
        project = task.project_uuid
        if project is None and task.heading_uuid in self.tasks:
            project = self.tasks[task.heading_uuid].project_uuid
        if project in self.tasks:
            return self.named(project, "project")
        if task.area_uuid in self.areas:
            return Named(task.area_uuid, "area", self.areas[task.area_uuid])
        return None

    def with_patterns(self, message: str) -> str:
        """The user's own pattern next to "matches user pattern N"."""

        def show(match: re.Match[str]) -> str:
            number = int(match.group(1))
            if 1 <= number <= len(self.patterns):
                return f"{match.group(0)} (/{self.patterns[number - 1]}/)"
            return match.group(0)

        return USER_PATTERN.sub(show, message)


def _kind(ref_kind: str) -> str:
    return KIND_LABELS[ref_kind]


def _first(finding: Finding, lookup: _Lookup) -> Named:
    ref = finding.refs[0]
    return lookup.named(ref.id, _kind(ref.kind))


def _by_place(
    found: Sequence[Finding], lookup: _Lookup, with_note: bool, noun: str, nowhere: str
) -> list[Group]:
    """Group the first ref of each finding by where that item lives."""
    places: dict[str | None, Named | None] = {}
    members: dict[str | None, list[Item]] = {}
    for finding in found:
        task = lookup.tasks.get(finding.refs[0].id)
        place = lookup.place(task) if task is not None else None
        key = None if place is None else f"{place.kind}:{place.id}"
        places.setdefault(key, place)
        note = lookup.with_patterns(finding.message) if with_note else None
        members.setdefault(key, []).append(Item((_first(finding, lookup),), note))
    return [
        Group(places[key], nowhere, noun, tuple(items))
        for key, items in members.items()
    ]


def _one_line_each(found, lookup):
    """The fallback and the simple checks: the item, then its own message."""
    items = [Item((_first(f, lookup),), lookup.with_patterns(f.message)) for f in found]
    return "lines", None, [], items


def _trashed_container(found, lookup):
    """One group per trashed project (or heading); the refs are the to-do,
    then the trashed container."""
    members: dict[str, list[Item]] = {}
    containers: dict[str, Named] = {}
    for finding in found:
        container = finding.refs[1]
        containers[container.id] = lookup.named(container.id, _kind(container.kind))
        members.setdefault(container.id, []).append(Item((_first(finding, lookup),)))
    groups = [
        Group(containers[uuid], "", "open to-do", tuple(items))
        for uuid, items in members.items()
    ]
    return "groups", None, groups, []


def _unfiled(found, lookup):
    """Every finding is a to-do with no project or area: one message, one list."""
    return "list", found[0].message, [], [Item((_first(f, lookup),)) for f in found]


def _title_hygiene(found, lookup):
    groups = _by_place(found, lookup, True, "to-do", "No project or area")
    return "groups", None, groups, []


def _possible_duplicates(found, lookup):
    """One item per set of matching titles."""
    items = [
        Item(tuple(lookup.named(r.id, _kind(r.kind)) for r in f.refs)) for f in found
    ]
    return "lines", None, [], items


def _by_second_ref(found, lookup):
    """The to-do is the first ref and its project the second; group by project."""
    members: dict[str, list[Item]] = {}
    for finding in found:
        members.setdefault(finding.refs[1].id, []).append(
            Item((_first(finding, lookup),))
        )
    groups = [
        Group(lookup.named(uuid, "project"), "No project", "to-do", tuple(items))
        for uuid, items in members.items()
    ]
    return "groups", found[0].message, groups, []


def _projects_by_area(found, lookup):
    groups = _by_place(found, lookup, False, "project", "No area")
    return "groups", found[0].message, groups, []


def _outside_heading(found, lookup):
    """The project is the first ref, the loose to-dos follow."""
    groups = [
        Group(
            _first(finding, lookup),
            "",
            "open to-do",
            tuple(Item((lookup.named(r.id, _kind(r.kind)),)) for r in finding.refs[1:]),
            " outside any heading",
        )
        for finding in found
    ]
    return "groups", None, groups, []


SECTIONS = {
    "open_in_trashed_project": _trashed_container,
    "unfiled_open": _unfiled,
    "title_hygiene": _title_hygiene,
    "possible_duplicates": _possible_duplicates,
    "dated_in_someday_project": _by_second_ref,
    "active_project_no_open_tasks": _projects_by_area,
    "someday_in_active_project": _by_second_ref,
    "outside_heading": _outside_heading,
}
