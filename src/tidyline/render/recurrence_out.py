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

RAW_WARNING = (
    "Raw rules may contain personal data. Check before pasting them into a "
    "public bug report."
)
NOT_RECOGNISED = "not recognised"
STATES = ("live", "leftover", NOT_RECOGNISED)  # also the sort order
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
    areas = {area.uuid: area.title for area in snapshot.areas}
    leftovers = set(snapshot.leftover_template_uuids)

    entries = []
    for template in snapshot.templates:
        entries.append((_state(template, leftovers), template))
    entries.sort(
        key=lambda item: (
            STATES.index(item[0].split(",")[0]),
            _headline(item[1]),
            item[1].uuid,
        )
    )

    lines: list[str] = []
    if raw:
        lines += [f"{style.notice('warning:')} {RAW_WARNING}", ""]
    for state, template in entries:
        lines += _block(state, template, tasks, areas, raw)
        lines.append("")
    counts = {name: 0 for name in STATES}
    for state, _ in entries:
        counts[state.split(",")[0]] += 1
    lines.append(
        f"{len(entries)} templates, {counts['live']} live, "
        f"{counts['leftover']} leftover, {counts[NOT_RECOGNISED]} not recognised"
    )
    return "\n".join(lines) + "\n"


def _state(template: Task, leftovers: set[str]) -> str:
    """live, leftover or not recognised; the last wins when more than one applies."""
    leftover = template.uuid in leftovers
    if not template.recurrence.recognised:
        return f"{NOT_RECOGNISED}, leftover" if leftover else NOT_RECOGNISED
    return "leftover" if leftover else "live"


def _headline(template: Task) -> str:
    """The first line of a block, which is also what the blocks are sorted by."""
    rule = template.recurrence
    text = rule.text if rule.recognised else NOT_RECOGNISED
    return f"{text} (paused)" if template.recurrence_paused else text


def _block(state, template, tasks, areas, raw) -> list[str]:
    lines = [
        _headline(template),
        f"  title:  {safe_title(template.title)}",
        f"  in:     {_place(template, tasks, areas)}",
        f"  state:  {state}",
    ]
    if raw:
        lines += _raw_lines(template)
    return lines


def _place(template: Task, tasks, areas) -> str:
    project_uuid = template.project_uuid
    if project_uuid is None and template.heading_uuid is not None:
        heading = tasks.get(template.heading_uuid)
        project_uuid = heading.project_uuid if heading else None
    if project_uuid is not None:
        project = tasks.get(project_uuid)
        if project is None:
            return "project (not found)"
        trashed = " (trashed)" if project.trashed else ""
        return f"project {safe_title(project.title)}{trashed}"
    if template.area_uuid is not None:
        title = areas.get(template.area_uuid)
        return f"area {safe_title(title)}" if title is not None else "area (not found)"
    return "no project or area"


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
