"""Build the JSON export (DESIGN.md 7.4). Returns plain data; never prints or writes.

Every row in the Snapshot is exported, including completed, cancelled and
trashed ones; each carries `status`, `trashed` and `effective_status` so a
consumer can filter. Recurring templates appear only under
`recurring_templates`; their instances are ordinary tasks. References are
`{"id", "title"}` objects joined by UUID. Nothing from TMSettings is read, so
the URL-scheme auth token cannot appear.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable, Mapping
from typing import Any

from tidyline.checks import run_checks
from tidyline.model import (
    START_ANYTIME,
    START_INBOX,
    START_SOMEDAY,
    STATUS_CANCELLED,
    STATUS_COMPLETED,
    STATUS_OPEN,
    Snapshot,
    Task,
    TaskKind,
)
from tidyline.recurrence import Rule
from tidyline.render.check_out import findings_json
from tidyline.status import effective_status

EXPORT_SCHEMA_VERSION = "1"
ENVIRONMENT_KEYS = ("macos", "arch", "things_version", "database_version")

STATUS_NAMES = {
    STATUS_OPEN: "open",
    STATUS_CANCELLED: "cancelled",
    STATUS_COMPLETED: "completed",
}
START_NAMES = {START_INBOX: "inbox", START_ANYTIME: "anytime", START_SOMEDAY: "someday"}


def build_export(
    snapshot: Snapshot,
    *,
    today: dt.date,
    exported_at: dt.datetime,
    tool_version: str,
    environment: Mapping[str, Any],
) -> dict[str, Any]:
    """The export as a JSON-ready dict. `today` drives effective status and the
    checks; the checks run with default options (no user patterns)."""
    if exported_at.tzinfo is None:
        raise ValueError("exported_at must be timezone-aware")
    tasks = {task.uuid: task for task in snapshot.tasks}
    areas = {area.uuid: area.title for area in snapshot.areas}
    tags = {tag.uuid: tag.title for tag in snapshot.tags}
    checklists: dict[str, list] = {}
    for item in _ordered(snapshot.checklist_items):
        checklists.setdefault(item.task_uuid, []).append(
            {
                "id": item.uuid,
                "title": item.title,
                **_status(item.status),
            }
        )
    leftovers = set(snapshot.leftover_template_uuids)
    context = _Context(tasks, areas, tags, checklists, today)

    return {
        "export_schema_version": EXPORT_SCHEMA_VERSION,
        "tool": {"name": "tidyline", "version": tool_version},
        "exported_at": exported_at.isoformat(),
        "environment": {key: environment.get(key) for key in ENVIRONMENT_KEYS},
        "anonymisation": "none",
        "areas": [{"id": a.uuid, "title": a.title} for a in _ordered(snapshot.areas)],
        "projects": [context.entry(t) for t in _ordered(snapshot.projects)],
        "headings": [context.entry(t) for t in _ordered(snapshot.headings)],
        "tasks": [context.entry(t) for t in _ordered(snapshot.todos)],
        "recurring_templates": [
            context.template(t, t.uuid in leftovers)
            for t in _ordered(snapshot.templates)
        ],
        "findings": findings_json(run_checks(snapshot, today)),
        "warnings": list(snapshot.warnings),
    }


class _Context:
    def __init__(self, tasks, areas, tags, checklists, today):
        self.tasks: Mapping[str, Task] = tasks
        self.areas: Mapping[str, str] = areas
        self.tags: Mapping[str, str] = tags
        self.checklists: Mapping[str, list] = checklists
        self.today: dt.date = today
        self.instances: dict[str, list[str]] = {}
        for task in _ordered(tasks.values()):
            if task.recurrence_template_uuid is not None:
                self.instances.setdefault(task.recurrence_template_uuid, []).append(
                    task.uuid
                )

    def project_uuid(self, task: Task) -> str | None:
        """The task's project, or its heading's project (DESIGN.md 7.2)."""
        if task.project_uuid is not None or task.heading_uuid is None:
            return task.project_uuid
        heading = self.tasks.get(task.heading_uuid)
        return heading.project_uuid if heading else None

    def ref(self, uuid: str | None, titles: Mapping[str, Any]) -> dict | None:
        if uuid is None:
            return None
        found = titles.get(uuid)
        title = found.title if isinstance(found, Task) else found
        return {"id": uuid, "title": title}

    def entry(self, task: Task) -> dict[str, Any]:
        """A project, heading or to-do; to-dos add checklist and recurrence."""
        project_uuid = self.project_uuid(task)
        project = self.tasks.get(project_uuid) if project_uuid else None
        if project is not None and project.kind is not TaskKind.PROJECT:
            project = None
        result: dict[str, Any] = {
            "id": task.uuid,
            "title": task.title,
            "notes": task.notes,
            "area": self.ref(task.area_uuid, self.areas),
            "project": self.ref(project_uuid, self.tasks),
            "heading": self.ref(task.heading_uuid, self.tasks),
            "effective_status": effective_status(
                task, project, self.today
            ).name.lower(),
            **_start(task.start),
            "start_date": _date(task.start_date),
            "deadline": _date(task.deadline),
            **_status(task.status),
            "trashed": task.trashed,
            "completion_date": _timestamp(task.stopped),
            "tags": [self.ref(uuid, self.tags) for uuid in task.tag_uuids],
        }
        if task.kind is TaskKind.TODO:
            template = self.tasks.get(task.recurrence_template_uuid or "")
            result["checklist"] = self.checklists.get(task.uuid, [])
            result["recurring_template"] = self.ref(
                task.recurrence_template_uuid, self.tasks
            )
            result["recurrence"] = _rule(template.recurrence if template else None)
        return result

    def template(self, task: Task, leftover: bool) -> dict[str, Any]:
        return {
            "id": task.uuid,
            "title": task.title,
            "notes": task.notes,
            "area": self.ref(task.area_uuid, self.areas),
            "project": self.ref(self.project_uuid(task), self.tasks),
            "heading": self.ref(task.heading_uuid, self.tasks),
            "leftover": leftover,
            "paused": task.recurrence_paused,
            "recurrence": _rule(task.recurrence),
            "tags": [self.ref(uuid, self.tags) for uuid in task.tag_uuids],
            "instances": self.instances.get(task.uuid, []),
        }


def _ordered(items: Iterable[Any]) -> list[Any]:
    """Things order: the stored index, then uuid so ties are stable."""
    return sorted(items, key=lambda item: (item.index, item.uuid))


def _status(code: int) -> dict[str, Any]:
    return {"status": STATUS_NAMES.get(code, f"unknown:{code}"), "status_code": code}


def _start(code: int) -> dict[str, Any]:
    return {"start": START_NAMES.get(code, f"unknown:{code}"), "start_code": code}


def _date(value: dt.date | None) -> str | None:
    return value.isoformat() if value is not None else None


def _timestamp(value: dt.datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _rule(rule: Rule | None) -> dict[str, Any] | None:
    if rule is None:
        return None
    return {
        "text": rule.text,
        "confidence": rule.confidence,
        "notes": list(rule.notes),
        "raw": rule.raw,
    }
