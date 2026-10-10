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

CHECK_SCHEMA_VERSION = "1"
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
) -> str:
    titles = {task.uuid: task.title for task in snapshot.tasks}
    summary = _summary(findings)
    lines = [
        f"tidyline check: {len(checks)} checks, {len(findings)} findings "
        f"({summary['warning']} warnings, {summary['info']} info)"
    ]
    for check in checks:
        found = [f for f in findings if f.check == check]
        lines.append("")
        lines.append(f"{check} ({CHECKS[check].SEVERITY}): {len(found)}")
        if not found:
            lines.append("  none")
        for finding in found:
            lines.append(f"  - {_with_patterns(finding.message, patterns)}")
            for ref in finding.refs:
                title = titles.get(ref.id)
                shown = f'"{safe_title(title)}"' if title is not None else "(not found)"
                lines.append(f"      {KIND_LABELS[ref.kind]:<9}{shown}")
    return "\n".join(lines) + "\n"


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
