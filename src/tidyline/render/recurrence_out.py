"""Text for `tidyline recurrence`. Returns a string; never prints.

One block per recurring template, so the readable rule can be checked against
what Things shows in the Repeat dialog. Rules the decoder does not understand
are shown as "not recognised", never described. Titles appear because the
output goes to the user's own screen; control characters are replaced.
"""

from __future__ import annotations

from tidyline.model import Snapshot, Task
from tidyline.render.check_out import safe_title
from tidyline.render.style import PLAIN, Style
from tidyline.report_data import (
    NOT_RECOGNISED,
    TEMPLATE_STATES,
    TemplatePlace,
    TemplateRow,
    template_rows,
)

RAW_WARNING = (
    "Raw rules may contain personal data. Check before pasting them into a "
    "public bug report."
)
MAX_RAW_BYTES = 10_000
RULE_FIELDS = (
    "unit",
    "interval",
    "after_completion",
    "has_end_date",
    "repeat_limit",
    "start_days_before_deadline",
    "confidence",
)


def render_recurrence(
    snapshot: Snapshot, *, raw: bool = False, style: Style = PLAIN
) -> str:
    tasks = {task.uuid: task for task in snapshot.tasks}
    rows = template_rows(snapshot)

    lines: list[str] = []
    if raw:
        lines += [f"{style.notice('warning:')} {RAW_WARNING}", ""]
    for row in rows:
        lines += _block(row)
        if raw:
            lines += _raw_lines(tasks[row.uuid])
        lines.append("")
    counts = {name: 0 for name in TEMPLATE_STATES}
    for row in rows:
        counts[row.state.split(",")[0]] += 1
    lines.append(
        f"{len(rows)} templates, {counts['live']} live, "
        f"{counts['leftover']} leftover, {counts[NOT_RECOGNISED]} not recognised"
    )
    return "\n".join(lines) + "\n"


def _block(row: TemplateRow) -> list[str]:
    return [
        row.headline,
        f"  title:  {safe_title(row.title)}",
        f"  in:     {_place(row.place)}",
        f"  state:  {row.state}",
    ]


def _place(place: TemplatePlace) -> str:
    if place.kind == "none":
        return "no project or area"
    if place.title is None:
        return f"{place.kind} (not found)"
    trashed = " (trashed)" if place.trashed else ""
    return f"{place.kind} {safe_title(place.title)}{trashed}"


def _raw_lines(template: Task) -> list[str]:
    rule = template.recurrence
    lines = ["  raw rule:"]
    lines += [f"    {line}" for line in _stored(template.raw_rule)]
    lines.append("  decoded:")
    for name in RULE_FIELDS:
        lines.append(f"    {name} = {_show(getattr(rule, name))}")
    lines.append("  fields in the rule:")
    for key in sorted(rule.raw):
        lines.append(f"    {key} = {_show(rule.raw[key])}")
    if not rule.recognised:
        lines.append("  reason:")
        lines += [f"    {note}" for note in rule.notes]
    elif rule.notes:
        lines.append("  notes:")
        lines += [f"    {note}" for note in rule.notes]
    return lines


def _stored(blob: bytes | None) -> list[str]:
    """The rule as stored: XML text as it is, anything else as hex with its length."""
    if blob is None:
        return ["(none)"]
    shown = blob[:MAX_RAW_BYTES]
    cut = f" (first {MAX_RAW_BYTES} bytes)" if len(blob) > MAX_RAW_BYTES else ""
    try:
        text = shown.decode("utf-8")
    except UnicodeDecodeError:
        text = None
    if text is not None and not blob.startswith(b"bplist"):
        if all(c.isprintable() or c in "\n\r\t" for c in text):
            return text.splitlines() + ([f"[{len(blob)} bytes{cut}]"] if cut else [])
    return [f"hex: {shown.hex()}", f"[{len(blob)} bytes{cut}]"]


def _show(value: object) -> str:
    return safe_title(str(value))
