"""Map strict labels in an LLM answer back to real titles (`tidyline decode`).

Labels come from `anonymise.make_labels`, which derives each label from the
item's id alone, so the current database is enough: no mapping file is kept.
Ids are grouped by kind the way the strict export groups them, including ids
that items refer to, so collision suffixes come out the same.

Rules (DESIGN.md 7.5):
- Whole labels ("Task k3f7az") are replaced, and so are bare codes ("k3f7az")
  that belong to exactly one label. A bare code shared by several labels is
  left as it is and counted as ambiguous. Lowercase only; a letter or digit
  next to a label or code means it is part of a longer word. Everything is
  replaced in one pass over the original text, so an inserted title is never
  scanned again.
- A title has its whitespace collapsed to single spaces and is cut to 79
  characters plus "…" when longer than 80.
- On a markdown table line (first non-space character "|"), "|" in a title is
  written as "\\|".
- A title is put in straight double quotes, unless the label is already
  directly between quote characters or backticks.
- When two or more items still in the payload's scope share a title, each gets
  its location inside the quotes: "Title (in Parent)".

Known limits:
- Only `strict` output has labels. `light` output keeps real titles and needs
  no decoding.
- Decode needs the same database the prompt was made from. A label whose item
  was deleted since, or that comes from another database, stays as it is and is
  counted as unmatched.
- A kind word followed by six lowercase letters or digits 2-7 looks like a
  label ("Project review"); it stays as it is and is counted as unmatched. A
  bare six-letter word that happens to equal a code is replaced.
- Other markdown characters in titles ("*", backticks) are not escaped.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

from tidyline.anonymise import BARE_CODE_PATTERN, LABEL_PATTERN, make_labels
from tidyline.model import Snapshot, Task, TaskKind

MAX_TITLE = 80
MAX_PARENT = 40
ELLIPSIS = "…"
QUOTES = frozenset("\"“”'`")
_TOKEN = re.compile(
    rf"(?P<label>{LABEL_PATTERN.pattern})|(?P<bare>{BARE_CODE_PATTERN.pattern})"
)


@dataclass(frozen=True)
class DecodeResult:
    text: str
    replaced: int  # label occurrences replaced
    distinct: int  # distinct items replaced, by label or bare code
    unmatched: tuple[str, ...]  # distinct label-like strings with no match
    bare_replaced: int = 0  # bare code occurrences replaced
    ambiguous: tuple[str, ...] = ()  # distinct bare codes shared by several labels


@dataclass(frozen=True)
class Item:
    """What decode knows about a label besides its title."""

    parent: str | None = None  # project, or area; None for areas and tags
    in_scope: bool = True  # would appear in the prompt payload (DESIGN.md 7.6)


def label_map(snapshot: Snapshot) -> dict[str, str]:
    """label -> stored title, for every item the strict export labels."""
    ids, titles = _ids_and_titles(snapshot)
    result = {}
    for kind, kind_ids in ids.items():
        for uuid, label in make_labels(kind, kind_ids).items():
            if (kind, uuid) in titles:
                result[label] = titles[kind, uuid]
    return result


def labels_by_kind(snapshot: Snapshot) -> dict[str, dict[str, str]]:
    """kind -> {id: label}, grouped exactly as `label_map` groups them, so a
    payload labelled with these decodes with `label_map`."""
    ids, _ = _ids_and_titles(snapshot)
    return {kind: make_labels(kind, kind_ids) for kind, kind_ids in ids.items()}


def label_items(snapshot: Snapshot) -> dict[str, Item]:
    """label -> Item, for every item `label_map` covers.

    In scope, as in the prompt payload: areas, tags and recurring templates;
    open, untrashed to-dos (also inside a trashed project); open, untrashed
    projects and projects that still hold such a to-do; open, untrashed
    headings of those projects.
    """
    tasks = {task.uuid: task for task in snapshot.tasks}
    areas = {area.uuid: area.title for area in snapshot.areas}

    def project_of(task: Task) -> Task | None:
        uuid = task.project_uuid
        if uuid is None and task.heading_uuid in tasks:
            uuid = tasks[task.heading_uuid].project_uuid
        found = tasks.get(uuid) if uuid else None
        return found if found is not None and found.kind is TaskKind.PROJECT else None

    def is_open(task: Task) -> bool:
        return not task.is_closed and not task.trashed

    def area_title(task: Task) -> str | None:
        return areas.get(task.area_uuid) if task.area_uuid else None

    holding = set()
    for todo in snapshot.todos:
        project = project_of(todo)
        if is_open(todo) and project is not None:
            holding.add(project.uuid)
    projects = {p.uuid for p in snapshot.projects if is_open(p) or p.uuid in holding}

    details: dict[tuple[str, str], Item] = {}
    for area in snapshot.areas:
        details["area", area.uuid] = Item()
    for tag in snapshot.tags:
        details["tag", tag.uuid] = Item()
    for project in snapshot.projects:
        details["project", project.uuid] = Item(
            area_title(project), project.uuid in projects
        )
    for heading in snapshot.headings:
        parent = tasks.get(heading.project_uuid or "")
        details["heading", heading.uuid] = Item(
            parent.title if parent is not None else None,
            is_open(heading) and heading.project_uuid in projects,
        )
    for kind, items in (("task", snapshot.todos), ("template", snapshot.templates)):
        for item in items:
            project = project_of(item)
            parent = project.title if project is not None else area_title(item)
            details[kind, item.uuid] = Item(parent, kind == "template" or is_open(item))

    ids, _ = _ids_and_titles(snapshot)
    result = {}
    for kind, kind_ids in ids.items():
        for uuid, label in make_labels(kind, kind_ids).items():
            if (kind, uuid) in details:
                result[label] = details[kind, uuid]
    return result


def _ids_and_titles(
    snapshot: Snapshot,
) -> tuple[dict[str, set[str]], dict[tuple[str, str], str]]:
    ids: dict[str, set[str]] = {
        kind: set()
        for kind in ("area", "project", "heading", "task", "tag", "template")
    }
    titles: dict[tuple[str, str], str] = {}

    def add(kind: str, uuid: str | None, title: str | None = None) -> None:
        if uuid is None:
            return
        ids[kind].add(uuid)
        if title is not None:
            titles[kind, uuid] = title

    tasks = {task.uuid: task for task in snapshot.tasks}
    for area in snapshot.areas:
        add("area", area.uuid, area.title)
    for tag in snapshot.tags:
        add("tag", tag.uuid, tag.title)
    for kind, items in (
        ("project", snapshot.projects),
        ("heading", snapshot.headings),
        ("task", snapshot.todos),
        ("template", snapshot.templates),
    ):
        for item in items:
            add(kind, item.uuid, item.title)
            # ids the export refers to, so collision groups match the export
            add("area", item.area_uuid)
            add("heading", item.heading_uuid)
            project = item.project_uuid
            if project is None and item.heading_uuid in tasks:
                project = tasks[item.heading_uuid].project_uuid
            add("project", project)
            add("template", item.recurrence_template_uuid)
            for tag in item.tag_uuids:
                add("tag", tag)
    return ids, titles


def decode_text(
    text: str,
    labels: Mapping[str, str],
    items: Mapping[str, Item] | None = None,
) -> DecodeResult:
    """Replace labels and bare codes in one pass over `text` (rules in the
    module docstring). `labels` maps label -> title; `items` adds locations for
    titles shared by items in scope."""
    codes: dict[str, list[str]] = {}
    for label in labels:
        codes.setdefault(label.split(" ", 1)[1], []).append(label)
    shown = _shown_titles(labels, items or {})
    table_lines: dict[int, bool] = {}
    replaced = bare_replaced = 0
    used: set[str] = set()
    unmatched: set[str] = set()
    ambiguous: set[str] = set()

    def insert(label: str, start: int, end: int) -> str:
        line = text.rfind("\n", 0, start) + 1
        if line not in table_lines:
            table_lines[line] = text[line:].lstrip(" \t").startswith("|")
        title = shown[label]
        if table_lines[line]:
            title = title.replace("|", "\\|")
        before = text[start - 1] if start > 0 else ""
        after = text[end] if end < len(text) else ""
        if before in QUOTES and after in QUOTES and before and after:
            return title
        return f'"{title}"'

    def swap(match: re.Match[str]) -> str:
        nonlocal replaced, bare_replaced
        found = match.group(0)
        if match.group("label") is not None:
            if found not in labels:
                unmatched.add(found)
                return found
            replaced += 1
            used.add(found)
            return insert(found, match.start(), match.end())
        code, rest = found, ""
        if code not in codes and "-" in code:  # "k3f7az-done": only the code
            code, rest = found[: found.index("-")], found[found.index("-") :]
        owners = codes.get(code)
        if not owners:
            return found
        if len(owners) > 1:
            ambiguous.add(code)
            return found
        bare_replaced += 1
        used.add(owners[0])
        return insert(owners[0], match.start(), match.start() + len(code)) + rest

    decoded = _TOKEN.sub(swap, text)
    return DecodeResult(
        text=decoded,
        replaced=replaced,
        distinct=len(used),
        unmatched=tuple(sorted(unmatched)),
        bare_replaced=bare_replaced,
        ambiguous=tuple(sorted(ambiguous)),
    )


def tidy(text: str, limit: int) -> str:
    """Whitespace collapsed to single spaces; cut to limit - 1 plus "…"."""
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + ELLIPSIS


def _shown_titles(
    labels: Mapping[str, str], items: Mapping[str, Item]
) -> dict[str, str]:
    """label -> the text to insert, with a location for shared titles."""
    sharing: dict[str, set[str]] = {}
    for label, title in labels.items():
        item = items.get(label)
        if item is not None and item.in_scope:
            sharing.setdefault(" ".join(title.split()), set()).add(label)
    shown = {}
    for label, title in labels.items():
        text = tidy(title, MAX_TITLE)
        item = items.get(label)
        shared = len(sharing.get(" ".join(title.split()), ())) > 1
        if item is not None and item.in_scope and shared and item.parent:
            text += f" (in {tidy(item.parent, MAX_PARENT)})"
        shown[label] = text
    return shown
