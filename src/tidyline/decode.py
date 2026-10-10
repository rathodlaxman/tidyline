"""Map strict labels in an LLM answer back to real titles (`tidyline decode`).

Labels come from `anonymise.make_labels`, which derives each label from the
item's id alone, so the current database is enough: no mapping file is kept.
Ids are grouped by kind the way the strict export groups them, including ids
that items refer to, so collision suffixes come out the same.

Known limits:
- Only `strict` output has labels. `light` output keeps real titles and needs
  no decoding.
- Decode needs the same database the prompt was made from. A label whose item
  was deleted since, or that comes from another database, stays as it is and is
  counted as unmatched.
- A kind word followed by six lowercase letters or digits 2-7 looks like a
  label ("Project review"); it stays as it is and is counted as unmatched.
- Titles go in exactly as stored, with no escaping. A title containing "|"
  splits a markdown table cell; "*" or a backtick can start emphasis or code.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from tidyline.anonymise import LABEL_PATTERN, make_labels
from tidyline.model import Snapshot


@dataclass(frozen=True)
class DecodeResult:
    text: str
    replaced: int  # label occurrences replaced
    distinct: int  # distinct labels replaced
    unmatched: tuple[str, ...]  # distinct label-like strings with no match


def label_map(snapshot: Snapshot) -> dict[str, str]:
    """label -> stored title, for every item the strict export labels."""
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

    result = {}
    for kind, kind_ids in ids.items():
        for uuid, label in make_labels(kind, kind_ids).items():
            if (kind, uuid) in titles:
                result[label] = titles[kind, uuid]
    return result


def decode_text(text: str, labels: Mapping[str, str]) -> DecodeResult:
    """Replace whole labels in one pass; a title put in is never scanned again."""
    replaced = 0
    used: set[str] = set()
    unmatched: set[str] = set()

    def swap(match) -> str:
        nonlocal replaced
        label = match.group(0)
        if label in labels:
            replaced += 1
            used.add(label)
            return labels[label]
        unmatched.add(label)
        return label

    decoded = LABEL_PATTERN.sub(swap, text)
    return DecodeResult(decoded, replaced, len(used), tuple(sorted(unmatched)))
