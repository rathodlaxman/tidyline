"""Output for `tidyline check`. Returns text or data; never prints.

The text form shows titles, because it goes to the user's own screen. The JSON
form carries ids only.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Sequence
from typing import Any

from tidyline.checks import CHECKS, Finding
from tidyline.checks.groups import Group, Item, Named, group_findings
from tidyline.model import Snapshot
from tidyline.render.style import PLAIN, Style

CHECK_SCHEMA_VERSION = "1"
FIXING_GUIDE_URL = (
    "https://github.com/rathodlaxman/tidyline/blob/main/docs/FIXING_PROBLEMS.md"
)


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
    """The text output: a total line, then one section per check, grouped by
    `group_findings`. A message that is the same for every finding is printed
    once under the heading; a message that differs follows its item."""
    summary = _summary(findings)
    lines = [
        f"tidyline check: {len(checks)} checks, {len(findings)} findings "
        f"({summary['warning']} warnings, {summary['info']} info)"
    ]
    for section in group_findings(findings, checks, snapshot, patterns):
        heading = (
            f"{section.check} ({section.severity}, "
            f"{_count(section.findings, 'finding')})"
        )
        lines += ["", style.bold(heading), "-" * len(heading)]
        if not section.findings:
            lines.append("  none")
            continue
        if section.message is not None:
            lines.append(f"{section.message}:")
        if section.layout == "groups":
            lines += _group_lines(section.groups)
        else:
            indent = "      " if section.layout == "list" else "  "
            lines += [f"{indent}{_item(item)}" for item in section.items]
    lines.append("")
    lines.append(style.bold(f"How to fix these: {FIXING_GUIDE_URL}"))
    return "\n".join(lines) + "\n"


def _count(number: int, noun: str) -> str:
    return f"{number} {noun}" + ("" if number == 1 else "s")


def _title(named: Named) -> str:
    return f'"{safe_title(named.title)}"' if named.title is not None else "(not found)"


def _item(item: Item) -> str:
    text = " = ".join(_title(named) for named in item.things)
    return text if item.note is None else f"{text} - {safe_title(item.note)}"


def _group_lines(groups: Sequence[Group]) -> list[str]:
    """One heading per place with its count, the items beneath it."""
    lines = []
    for group in groups:
        count = _count(len(group.items), group.noun) + group.suffix
        if group.place is None:
            lines.append(f"  {group.nowhere} ({count})")
        else:
            lines.append(f"  {_title(group.place)} ({group.place.kind}, {count})")
        lines += [f"      {_item(item)}" for item in group.items]
    return lines


def safe_title(text: str) -> str:
    """Replace control characters so a title cannot drive the terminal.

    Whitespace is kept as it is, so title_hygiene findings stay visible.
    """
    return "".join("?" if unicodedata.category(c) == "Cc" else c for c in text)


def _summary(findings: Sequence[Finding]) -> dict[str, int]:
    return {
        "warning": sum(1 for f in findings if f.severity == "warning"),
        "info": sum(1 for f in findings if f.severity == "info"),
    }
