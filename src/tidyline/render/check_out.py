"""Output for `tidyline check`. Returns text or data; never prints.

The text form shows titles, because it goes to the user's own screen. The JSON
form carries ids only.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from tidyline.checks import CHECKS, Finding
from tidyline.model import Snapshot, Task
from tidyline.render.style import PLAIN, Style

CHECK_SCHEMA_VERSION = "1"
FIXING_GUIDE_URL = (
    "https://github.com/rathodlaxman/tidyline/blob/main/docs/FIXING_PROBLEMS.md"
)
KIND_LABELS = {
    "task": "to-do",
    "project": "project",
    "heading": "heading",
    "template": "template",
}
USER_PATTERN = re.compile(r"matches user pattern (\d+)")


def findings_json(findings: Sequence[Finding]) -> list[dict[str, Any]]:
    """Finding objects as `check --json` and the export print them: ids only."""
    return [
        {
            "check": f.check,
            "severity": f.severity,
            "message": f.message,
            "refs": [{"kind": r.kind, "id": r.id} for r in f.refs],
        }
        for f in findings
    ]


def checks_run_json(
    findings: Sequence[Finding], checks: Sequence[str] | None = None
) -> list[dict[str, Any]]:
    """One entry per check that ran, in registry order, with its finding count.
    A check with no findings is listed with 0."""
    counts: dict[str, int] = {}
    for finding in findings:
        counts[finding.check] = counts.get(finding.check, 0) + 1
    return [
        {
            "check": check,
            "severity": CHECKS[check].SEVERITY,
            "findings": counts.get(check, 0),
        }
        for check in (CHECKS if checks is None else checks)
    ]


def check_json(findings: Sequence[Finding], checks: Sequence[str]) -> dict[str, Any]:
    return {
        "check_schema_version": CHECK_SCHEMA_VERSION,
        "checks": list(checks),
        "summary": _summary(findings),
        "findings": findings_json(findings),
    }


@dataclass(frozen=True)
class _Lookup:
    """What the text output needs to show titles and places."""

    tasks: dict[str, Task]
    areas: dict[str, str]
    patterns: Sequence[str]

    def title(self, uuid: str) -> str:
        task = self.tasks.get(uuid)
        return f'"{safe_title(task.title)}"' if task is not None else "(not found)"

    def place(self, task: Task) -> tuple[str, str] | None:
        """Where a to-do lives: its project (through its heading), else its
        area, else nowhere (None). Returns (kind, uuid)."""
        project = task.project_uuid
        if project is None and task.heading_uuid in self.tasks:
            project = self.tasks[task.heading_uuid].project_uuid
        if project in self.tasks:
            return ("project", project)
        if task.area_uuid in self.areas:
            return ("area", task.area_uuid)
        return None


def check_text(
    findings: Sequence[Finding],
    checks: Sequence[str],
    snapshot: Snapshot,
    patterns: Sequence[str] = (),
    style: Style = PLAIN,
) -> str:
    """The text output: a total line, then one section per check. A message
    that is the same for every finding is printed once under the heading; a
    message that differs follows its item. Items are grouped under their
    project, area or trashed project, with a count."""
    lookup = _Lookup(
        {task.uuid: task for task in snapshot.tasks},
        {area.uuid: area.title for area in snapshot.areas},
        patterns,
    )
    summary = _summary(findings)
    lines = [
        f"tidyline check: {len(checks)} checks, {len(findings)} findings "
        f"({summary['warning']} warnings, {summary['info']} info)"
    ]
    for check in checks:
        found = [f for f in findings if f.check == check]
        heading = f"{check} ({CHECKS[check].SEVERITY}, {_count(len(found), 'finding')})"
        lines += ["", style.bold(heading), "-" * len(heading)]
        if not found:
            lines.append("  none")
        else:
            lines += SECTIONS.get(check, _one_line_each)(found, lookup)
    lines.append("")
    lines.append(style.bold(f"How to fix these: {FIXING_GUIDE_URL}"))
    return "\n".join(lines) + "\n"


def _count(number: int, noun: str) -> str:
    return f"{number} {noun}" + ("" if number == 1 else "s")


def _described(message: str, body: list[str]) -> list[str]:
    return [f"{message}:", *body]


def _group_lines(
    groups: dict[tuple[str, str] | None, list[str]],
    lookup: _Lookup,
    noun: str,
    nowhere: str,
) -> list[str]:
    """One heading per place with its count, the items beneath it."""
    lines = []
    for place, items in groups.items():
        if place is None:
            name = nowhere
            kind = ""
        else:
            kind_name, uuid = place
            name = (
                lookup.title(uuid)
                if kind_name == "project"
                else (f'"{safe_title(lookup.areas[uuid])}"')
            )
            kind = f"{kind_name}, "
        lines.append(f"  {name} ({kind}{_count(len(items), noun)})")
        lines += [f"      {item}" for item in items]
    return lines


def _by_place(
    found: Sequence[Finding], lookup: _Lookup, describe=None
) -> dict[tuple[str, str] | None, list[str]]:
    """Group the first ref of each finding by where that item lives. The item
    line is its title, and `describe(finding)` appended when it is given."""
    groups: dict[tuple[str, str] | None, list[str]] = {}
    for finding in found:
        ref = finding.refs[0]
        task = lookup.tasks.get(ref.id)
        place = lookup.place(task) if task is not None else None
        item = lookup.title(ref.id)
        if describe is not None:
            item += f" - {describe(finding)}"
        groups.setdefault(place, []).append(item)
    return groups


def _one_line_each(found: Sequence[Finding], lookup: _Lookup) -> list[str]:
    """The fallback and the simple checks: the title, then the finding's own
    message after a dash, one line per finding."""
    return [
        f"  {lookup.title(f.refs[0].id)} - {_with_patterns(f.message, lookup.patterns)}"
        for f in found
    ]


def _trashed_container(found: Sequence[Finding], lookup: _Lookup) -> list[str]:
    """One block per trashed project (or heading); the finding's refs are the
    to-do, then the trashed container."""
    groups: dict[str, list[Finding]] = {}
    kinds: dict[str, str] = {}
    for finding in found:
        container = finding.refs[1]
        groups.setdefault(container.id, []).append(finding)
        kinds[container.id] = KIND_LABELS[container.kind]
    lines = []
    for container_id, members in groups.items():
        lines.append(
            f"  {lookup.title(container_id)} "
            f"({kinds[container_id]}, {_count(len(members), 'open to-do')})"
        )
        lines += [f"      {lookup.title(f.refs[0].id)}" for f in members]
    return lines


def _unfiled(found: Sequence[Finding], lookup: _Lookup) -> list[str]:
    """Every finding is a to-do with no project or area: one message, one list."""
    return _described(
        found[0].message, [f"      {lookup.title(f.refs[0].id)}" for f in found]
    )


def _title_hygiene(found: Sequence[Finding], lookup: _Lookup) -> list[str]:
    groups = _by_place(
        found, lookup, lambda f: _with_patterns(f.message, lookup.patterns)
    )
    return _group_lines(groups, lookup, "to-do", "No project or area")


def _possible_duplicates(found: Sequence[Finding], lookup: _Lookup) -> list[str]:
    """One line per set of matching titles."""
    return [
        "  " + " = ".join(lookup.title(ref.id) for ref in finding.refs)
        for finding in found
    ]


def _by_second_ref(found: Sequence[Finding], lookup: _Lookup) -> list[str]:
    """The to-do is the first ref and its project the second; group by project."""
    groups: dict[tuple[str, str] | None, list[str]] = {}
    for finding in found:
        groups.setdefault(("project", finding.refs[1].id), []).append(
            lookup.title(finding.refs[0].id)
        )
    return _described(
        found[0].message, _group_lines(groups, lookup, "to-do", "No project")
    )


def _projects_by_area(found: Sequence[Finding], lookup: _Lookup) -> list[str]:
    groups = _by_place(found, lookup)
    return _described(
        found[0].message, _group_lines(groups, lookup, "project", "No area")
    )


def _outside_heading(found: Sequence[Finding], lookup: _Lookup) -> list[str]:
    """The project is the first ref, the loose to-dos follow."""
    lines = []
    for finding in found:
        to_dos = finding.refs[1:]
        lines.append(
            f"  {lookup.title(finding.refs[0].id)} (project, "
            f"{_count(len(to_dos), 'open to-do')} outside any heading)"
        )
        lines += [f"      {lookup.title(ref.id)}" for ref in to_dos]
    return lines


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


def safe_title(text: str) -> str:
    """Replace control characters so a title cannot drive the terminal.

    Whitespace is kept as it is, so title_hygiene findings stay visible.
    """
    return "".join("?" if unicodedata.category(c) == "Cc" else c for c in text)


def _with_patterns(message: str, patterns: Sequence[str]) -> str:
    """Show the user's own pattern next to "matches user pattern N"."""

    def show(match: re.Match[str]) -> str:
        number = int(match.group(1))
        if 1 <= number <= len(patterns):
            return f"{match.group(0)} (/{safe_title(patterns[number - 1])}/)"
        return match.group(0)

    return USER_PATTERN.sub(show, message)


def _summary(findings: Sequence[Finding]) -> dict[str, int]:
    return {
        "warning": sum(1 for f in findings if f.severity == "warning"),
        "info": sum(1 for f in findings if f.severity == "info"),
    }
