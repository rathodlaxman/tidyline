"""Build a model.Snapshot from a snapshot copy of the database (DESIGN.md 3, 5, 7).

things.py supplies areas, tags and the identity of to-dos, projects and
headings: uuid, type, title, notes, status, start, trashed, area, project,
heading and index. One read-only SQL pass over the same copy supplies what
things.py does not give cleanly: packed dates as stored, the suppression date,
raw timestamps, startBucket, the rt1_* columns, tag UUIDs, checklist items,
area and tag order, and whole template rows (things.py never returns rows with
a recurrence rule). Rows are matched by UUID; if the two sources disagree, a
warning is added.

things.py is imported inside `read_snapshot`, never at module level, because
importing it lists another app's container (DESIGN.md 5). This module computes
no effective status and needs no date.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any
from urllib.parse import quote

from tidyline import dates
from tidyline.db.schema import check_schema
from tidyline.model import (
    Area,
    ChecklistItem,
    Snapshot,
    Tag,
    Task,
    TaskKind,
)
from tidyline.recurrence import parse_rule

KINDS = {0: TaskKind.TODO, 1: TaskKind.PROJECT, 2: TaskKind.HEADING}
THINGS_KINDS = {
    "to-do": TaskKind.TODO,
    "project": TaskKind.PROJECT,
    "heading": TaskKind.HEADING,
}
THINGS_STATUS = {"incomplete": 0, "canceled": 2, "completed": 3}
THINGS_START = {"Inbox": 0, "Anytime": 1, "Someday": 2}

TASK_SQL = """
    SELECT uuid, type, status, start, trashed, title, notes, "index",
           area, project, heading,
           startDate, deadline, deadlineSuppressionDate, startBucket,
           creationDate, userModificationDate, stopDate,
           rt1_recurrenceRule, rt1_repeatingTemplate, rt1_instanceCreationPaused
    FROM TMTask
"""
TASK_TAG_SQL = """
    SELECT link.tasks, link.tags
    FROM TMTaskTag AS link LEFT JOIN TMTag AS tag ON tag.uuid = link.tags
    ORDER BY link.tasks, tag."index", link.tags
"""
CHECKLIST_SQL = """
    SELECT uuid, task, title, status, "index"
    FROM TMChecklistItem ORDER BY task, "index", uuid
"""


class ReadError(Exception):
    """The snapshot copy could not be read."""


def read_snapshot(path: str | Path) -> Snapshot:
    """Read a snapshot copy made by `tidyline.db.snapshot`.

    Raises SchemaError when the copy lacks what tidyline needs, and ReadError
    when the path is not a file. Never opens anything but `path`.
    """
    path = Path(path)
    if not path.is_file():
        raise ReadError(
            f"No database copy at {path}. Make one with tidyline.db.snapshot "
            "first; read_snapshot never opens the live database."
        )
    check_schema(path)  # raises SchemaError; version warnings belong to doctor
    warnings: list[str] = []

    import things  # lazy: see the module docstring

    database = things.Database(filepath=str(path))
    try:
        library_areas = things.areas(database=database)
        library_tags = things.tags(database=database)
        library_tasks = things.tasks(
            database=database, status=None, trashed=None, context_trashed=None
        )
    finally:
        database.connection.close()

    raw = _read_raw(path)
    order = raw["area_order"], raw["tag_order"]
    areas = tuple(
        Area(uuid=a["uuid"], title=a["title"], index=order[0].get(a["uuid"], 0))
        for a in library_areas
    )
    tags = tuple(
        Tag(uuid=t["uuid"], title=t["title"], index=order[1].get(t["uuid"], 0))
        for t in library_tags
    )

    rows: dict[str, Mapping[str, Any]] = raw["tasks"]
    tag_links: dict[str, list[str]] = raw["task_tags"]
    tasks: list[Task] = []

    seen: set[str] = set()
    for item in library_tasks:
        uuid = item["uuid"]
        row = rows.get(uuid)
        if row is None:
            warnings.append(f"TMTask {uuid}: listed by things.py but not found")
            continue
        seen.add(uuid)
        tasks.append(_from_library(item, row, tag_links, warnings))

    templates: list[Task] = []
    for uuid, row in rows.items():
        if row["rt1_recurrenceRule"] is not None:
            if not row["trashed"]:  # a trashed template is ignored (7.2)
                task = _from_row(row, tag_links, warnings)
                if task is not None:
                    templates.append(task)
        elif uuid not in seen:
            warnings.append(f"TMTask {uuid}: not listed by things.py; skipped")

    by_uuid = {row["uuid"]: row for row in rows.values()}
    leftovers = tuple(
        t.uuid for t in templates if _is_leftover(by_uuid[t.uuid], by_uuid)
    )

    return Snapshot(
        areas=areas,
        tags=tags,
        tasks=tuple(tasks + templates),
        checklist_items=raw["checklist"],
        leftover_template_uuids=leftovers,
        warnings=tuple(warnings),
    )


def _read_raw(path: Path) -> dict[str, Any]:
    connection = sqlite3.connect(f"file:{quote(str(path))}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        tasks = {row["uuid"]: row for row in connection.execute(TASK_SQL)}
        task_tags: dict[str, list[str]] = {}
        for task_uuid, tag_uuid in connection.execute(TASK_TAG_SQL):
            task_tags.setdefault(task_uuid, []).append(tag_uuid)
        checklist = tuple(
            ChecklistItem(
                uuid=row["uuid"],
                task_uuid=row["task"],
                title=row["title"] or "",
                status=row["status"],
                index=row["index"] or 0,
            )
            for row in connection.execute(CHECKLIST_SQL)
        )
        area_order = dict(connection.execute('SELECT uuid, "index" FROM TMArea'))
        tag_order = dict(connection.execute('SELECT uuid, "index" FROM TMTag'))
    finally:
        connection.close()
    return {
        "tasks": tasks,
        "task_tags": task_tags,
        "checklist": checklist,
        "area_order": area_order,
        "tag_order": tag_order,
    }


def _from_library(
    item: Mapping[str, Any],
    row: Mapping[str, Any],
    tag_links: Mapping[str, list[str]],
    warnings: list[str],
) -> Task:
    """A to-do, project or heading: identity from things.py, the rest from SQL."""
    uuid = item["uuid"]
    kind = THINGS_KINDS.get(item["type"]) or KINDS.get(row["type"], TaskKind.TODO)
    status = _mapped(item.get("status"), THINGS_STATUS, row, "status", warnings)
    start = _mapped(item.get("start"), THINGS_START, row, "start", warnings)
    for column in ("area", "project", "heading"):
        if row[column] is not None and item.get(column) is None:
            warnings.append(
                f"TMTask {uuid}: {column} {row[column]} does not exist; ignored"
            )
    return Task(
        uuid=uuid,
        kind=kind,
        title=item["title"] or "",
        notes=item.get("notes") or None,
        status=status,
        trashed=bool(item.get("trashed")),
        start=start,
        area_uuid=item.get("area"),
        project_uuid=item.get("project"),
        heading_uuid=item.get("heading"),
        index=item.get("index") or 0,
        **_raw_fields(row, tag_links, warnings),
    )


def _from_row(
    row: Mapping[str, Any],
    tag_links: Mapping[str, list[str]],
    warnings: list[str],
) -> Task | None:
    """A recurring template, read entirely from SQL."""
    kind = KINDS.get(row["type"])
    if kind is None:
        warnings.append(f"TMTask {row['uuid']}: unknown type {row['type']!r}; skipped")
        return None
    return Task(
        uuid=row["uuid"],
        kind=kind,
        title=row["title"] or "",
        notes=row["notes"] or None,
        status=row["status"],
        trashed=bool(row["trashed"]),
        start=row["start"],
        area_uuid=row["area"],
        project_uuid=row["project"],
        heading_uuid=row["heading"],
        index=row["index"] or 0,
        recurrence=parse_rule(row["rt1_recurrenceRule"]),
        recurrence_paused=bool(row["rt1_instanceCreationPaused"]),
        **_raw_fields(row, tag_links, warnings),
    )


def _raw_fields(
    row: Mapping[str, Any],
    tag_links: Mapping[str, list[str]],
    warnings: list[str],
) -> dict[str, Any]:
    uuid = row["uuid"]

    def packed(column: str) -> Any:
        return _decoded(uuid, column, row[column], dates.unpack_date, warnings)

    def stamp(column: str) -> Any:
        return _decoded(uuid, column, row[column], dates.to_datetime, warnings)

    return {
        "start_date": packed("startDate"),
        "deadline": packed("deadline"),
        "deadline_suppression_date": packed("deadlineSuppressionDate"),
        "raw_start_date": row["startDate"],
        "raw_deadline": row["deadline"],
        "raw_deadline_suppression_date": row["deadlineSuppressionDate"],
        "start_bucket": row["startBucket"] or 0,
        "created": stamp("creationDate"),
        "modified": stamp("userModificationDate"),
        "stopped": stamp("stopDate"),
        "tag_uuids": tuple(tag_links.get(uuid, ())),
        "recurrence_template_uuid": row["rt1_repeatingTemplate"],
    }


def _decoded(
    uuid: str,
    column: str,
    value: object,
    decode: Callable[[object], Any],
    warnings: list[str],
) -> Any:
    if value is None:
        return None
    result = decode(value)
    if result is None:
        warnings.append(
            f"TMTask {uuid}: {column} {value!r} could not be decoded; "
            "treated as missing"
        )
    return result


def _mapped(
    value: object,
    names: Mapping[str, int],
    row: Mapping[str, Any],
    column: str,
    warnings: list[str],
) -> int:
    """Map a things.py label to its code; fall back to the stored value."""
    if isinstance(value, str) and value in names:
        return names[value]
    warnings.append(f"TMTask {row['uuid']}: unknown {column} {row[column]!r}")
    return row[column]


def _is_leftover(
    template: Mapping[str, Any], rows: Mapping[str, Mapping[str, Any]]
) -> bool:
    """True when the template's project is trashed or missing (DESIGN.md 7.2).

    The project is the `project` column, or the heading's project when the
    template sits under a heading. A template with neither is not a leftover.
    """
    project = template["project"]
    heading = template["heading"]
    if project is None and heading is not None:
        heading_row = rows.get(heading)
        if heading_row is None:
            return True
        project = heading_row["project"]
    if project is None:
        return False
    project_row = rows.get(project)
    return project_row is None or bool(project_row["trashed"])
