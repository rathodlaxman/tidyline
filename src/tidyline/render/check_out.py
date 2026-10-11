"""Output for `tidyline check`. Returns text or data; never prints.

The text form shows titles, because it goes to the user's own screen. The JSON
form carries ids only.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from typing import Any

from tidyline.checks import CHECKS, Finding
from tidyline.model import Snapshot
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
GROUPED_CHECK = "open_in_trashed_project"
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


def check_text(
    findings: Sequence[Finding],
    checks: Sequence[str],
    snapshot: Snapshot,
    patterns: Sequence[str] = (),
    style: Style = PLAIN,
) -> str:
    titles = {task.uuid: task.title for task in snapshot.tasks}
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
        elif check == GROUPED_CHECK:
            lines += _grouped_by_container(found, titles)
        else:
            lines += _one_line_each(found, titles, patterns)
    lines.append("")
    lines.append(style.bold(f"How to fix these: {FIXING_GUIDE_URL}"))
    return "\n".join(lines) + "\n"


def _count(number: int, noun: str) -> str:
    return f"{number} {noun}" + ("" if number == 1 else "s")


def _shown(ref_id: str, titles: dict[str, str]) -> str:
    title = titles.get(ref_id)
    return f'"{safe_title(title)}"' if title is not None else "(not found)"


def _one_line_each(
    found: Sequence[Finding], titles: dict[str, str], patterns: Sequence[str]
) -> list[str]:
    lines = []
    for finding in found:
        lines.append(f"  - {_with_patterns(finding.message, patterns)}")
        for ref in finding.refs:
            lines.append(f"      {KIND_LABELS[ref.kind]:<9}{_shown(ref.id, titles)}")
    return lines


def _grouped_by_container(
    found: Sequence[Finding], titles: dict[str, str]
) -> list[str]:
    """One block per trashed project (or heading), its open to-dos beneath it.
    Each finding's refs are the to-do, then the trashed container."""
    groups: dict[str, list[Finding]] = {}
    kinds: dict[str, str] = {}
    for finding in found:
        container = finding.refs[1]
        groups.setdefault(container.id, []).append(finding)
        kinds[container.id] = KIND_LABELS[container.kind]
    lines = []
    for container_id, members in groups.items():
        lines.append(
            f"  {_shown(container_id, titles)} "
            f"({kinds[container_id]}, {_count(len(members), 'open to-do')})"
        )
        for finding in members:
            lines.append(f"      {_shown(finding.refs[0].id, titles)}")
    return lines


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
