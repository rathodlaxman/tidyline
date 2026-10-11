"""Build the `tidyline prompt` payload (DESIGN.md 7.6). Pure: no I/O, no clock.

The payload holds open work only, plus ready-made counts, so an assistant does
not have to count rows itself. Rows come from the same export entries as
`tidyline export` and are anonymised by the same rules and labels, so `decode`
maps strict labels back.

Definitions:
- An open to-do is a to-do (not a template) that is neither completed,
  cancelled nor trashed. It is in a trashed project when its project or heading
  is trashed. `open_todos` and `by_status` count open to-dos that are not in a
  trashed project; `open_in_trashed_project` counts the others.
- A completed to-do has status completed and is not trashed. Cancelled to-dos
  are not counted. The 14- and 30-day windows end on the local date of
  `exported_at`, that day included.
- A to-do belongs to an area through its own area, or else its project's area.
- Projects listed: open, untrashed projects, plus any other project that still
  holds an open to-do.
"""

from __future__ import annotations

import datetime as dt
from collections import Counter
from collections.abc import Iterable
from typing import Any

from tidyline.anonymise import anonymise_payload
from tidyline.checks.scope import Scope
from tidyline.decode import labels_by_kind
from tidyline.model import START_SOMEDAY, STATUS_COMPLETED, Snapshot, Task
from tidyline.render.json_out import build_export

PAYLOAD_SCHEMA_VERSION = "1"
LEVELS = ("light", "strict")
STATUSES = ("inbox", "today", "this_evening", "upcoming", "anytime", "someday")
SCOPE = (
    "Open work only: completed, cancelled and trashed to-dos, and completed or "
    "trashed projects that hold no open to-dos, are left out and counted in "
    "the summary only."
)
TASK_KEYS = (
    "id",
    "title",
    "notes",
    "area",
    "project",
    "heading",
    "effective_status",
    "start_date",
    "deadline",
    "created",
    "modified",
    "tags",
    "checklist_count",
    "recurrence",
)


def build_payload(
    snapshot: Snapshot, *, today: dt.date, exported_at: dt.datetime, level: str
) -> dict[str, Any]:
    """The anonymised payload at `level` ("light" or "strict")."""
    if level not in LEVELS:
        raise ValueError(f"the payload must be light or strict, not {level!r}")
    if exported_at.tzinfo is None:
        raise ValueError("exported_at must be timezone-aware")
    export = build_export(
        snapshot,
        today=today,
        exported_at=exported_at,
        tool_version="",
        environment={},
    )
    payload = _Builder(snapshot, export, exported_at).payload()
    labels = labels_by_kind(snapshot) if level == "strict" else None
    return anonymise_payload(payload, level, labels)


class _Builder:
    def __init__(
        self, snapshot: Snapshot, export: dict[str, Any], exported_at: dt.datetime
    ):
        self.snapshot = snapshot
        self.export = export
        self.exported_at = exported_at
        self.local_today = exported_at.date()
        self.scope = Scope(snapshot)
        self.entries = {e["id"]: e for e in export["tasks"]}

        self.open = self.scope.open_todos()
        self.in_trash = {
            t.uuid for t in self.open if self.scope.trashed_container(t) is not None
        }
        self.live = [t for t in self.open if t.uuid not in self.in_trash]
        self.completed = [
            t for t in snapshot.todos if t.status == STATUS_COMPLETED and not t.trashed
        ]
        self.leftovers = set(snapshot.leftover_template_uuids)
        self.under = Counter(t.heading_uuid for t in self.open)  # per heading

    # --- membership ---

    def project_id(self, task: Task) -> str | None:
        project = self.scope.project(task)
        return project.uuid if project else None

    def area_id(self, task: Task) -> str | None:
        if task.area_uuid is not None:
            return task.area_uuid
        project = self.scope.project(task)
        return project.area_uuid if project else None

    def status(self, task: Task) -> str:
        return self.entries[task.uuid]["effective_status"]

    def by_status(self, tasks: Iterable[Task]) -> dict[str, int]:
        counts = Counter(self.status(t) for t in tasks)
        return {name: counts.get(name, 0) for name in STATUSES}

    def within(self, task: Task, days: int) -> bool:
        if task.stopped is None:
            return False
        day = task.stopped.astimezone(self.exported_at.tzinfo).date()
        return self.local_today - dt.timedelta(days=days - 1) <= day <= self.local_today

    def completed_counts(self, tasks: list[Task], windows=(14, 30)) -> dict[str, int]:
        result = {
            f"completed_last_{days}_days": sum(self.within(t, days) for t in tasks)
            for days in windows
        }
        result["completed_total"] = len(tasks)
        return result

    # --- the payload ---

    def payload(self) -> dict[str, Any]:
        projects = self.projects()
        project_ids = {p["id"] for p in projects}
        tasks = self.tasks()
        task_ids = {t["id"] for t in tasks}
        return {
            "payload_schema_version": PAYLOAD_SCHEMA_VERSION,
            "anonymisation": "none",
            "exported_at": self.exported_at.isoformat(),
            "scope": SCOPE,
            "summary": self.summary(),
            "areas": self.areas(),
            "projects": projects,
            "headings": self.headings(project_ids),
            "tasks": tasks,
            "tags": self.tags(),
            "recurring_templates": self.templates(task_ids),
            "checks_run": self.export["checks_run"],
            "findings": self.export["findings"],
            "data_read_warnings": self.export["warnings"],
        }

    def summary(self) -> dict[str, Any]:
        projects = [p for p in self.snapshot.projects if not p.trashed]
        open_projects = [p for p in projects if self.scope.is_open(p)]
        someday = sum(p.start == START_SOMEDAY for p in open_projects)
        windows = self.completed_counts(self.completed)
        return {
            "open_todos": len(self.live),
            "by_status": self.by_status(self.live),
            "open_in_trashed_project": len(self.in_trash),
            "areas": len(self.snapshot.areas),
            "projects": {
                "open": len(open_projects),
                "someday": someday,
                "active": len(open_projects) - someday,
                "completed": sum(p.status == STATUS_COMPLETED for p in projects),
                "trashed": sum(p.trashed for p in self.snapshot.projects),
            },
            "completed_todos": {
                "total": windows["completed_total"],
                "last_14_days": windows["completed_last_14_days"],
                "last_30_days": windows["completed_last_30_days"],
            },
            "recurring_templates": {
                "live": sum(
                    t.uuid not in self.leftovers for t in self.snapshot.templates
                ),
                "leftover": sum(
                    t.uuid in self.leftovers for t in self.snapshot.templates
                ),
            },
            "tagged_open_todos": sum(bool(t.tag_uuids) for t in self.live),
        }

    def areas(self) -> list[dict[str, Any]]:
        rows = []
        for area in self.export["areas"]:
            uuid = area["id"]
            live = [t for t in self.live if self.area_id(t) == uuid]
            done = [t for t in self.completed if self.area_id(t) == uuid]
            rows.append(
                {
                    "id": uuid,
                    "title": area["title"],
                    "open_projects": sum(
                        p.area_uuid == uuid and self.scope.is_open(p)
                        for p in self.snapshot.projects
                    ),
                    "open_todos": len(live),
                    "by_status": self.by_status(live),
                    **self.completed_counts(done),
                }
            )
        return rows

    def projects(self) -> list[dict[str, Any]]:
        holding = {self.project_id(t) for t in self.open}
        tasks = {t.uuid: t for t in self.snapshot.projects}
        rows = []
        for entry in self.export["projects"]:
            project = tasks[entry["id"]]
            if not (self.scope.is_open(project) or project.uuid in holding):
                continue
            uuid = project.uuid
            todos = [t for t in self.open if self.project_id(t) == uuid]
            headings = self.open_headings(uuid)
            rows.append(
                {
                    "id": uuid,
                    "title": entry["title"],
                    "area": entry["area"],
                    "state": "someday" if project.start == START_SOMEDAY else "active",
                    "deadline": entry["deadline"],
                    "created": entry["created"],
                    "modified": entry["modified"],
                    "open_todos": len(todos),
                    "by_status": self.by_status(todos),
                    "headings": len(headings),
                    "empty_headings": sum(not self.under[h.uuid] for h in headings),
                    "live_templates": sum(
                        self.project_id(t) == uuid and t.uuid not in self.leftovers
                        for t in self.snapshot.templates
                    ),
                    **self.completed_counts(
                        [t for t in self.completed if self.project_id(t) == uuid],
                        windows=(30,),
                    ),
                    "trashed": project.trashed,
                }
            )
        return rows

    def open_headings(self, project_uuid: str) -> list[Task]:
        return [
            h
            for h in self.snapshot.headings
            if h.project_uuid == project_uuid and self.scope.is_open(h)
        ]

    def headings(self, project_ids: set[str]) -> list[dict[str, Any]]:
        return [
            {
                "id": entry["id"],
                "title": entry["title"],
                "project": entry["project"],
                "open_todos": self.under[entry["id"]],
            }
            for entry in self.export["headings"]
            if entry["project"] is not None
            and entry["project"]["id"] in project_ids
            and entry["status"] == "open"
            and not entry["trashed"]
        ]

    def tasks(self) -> list[dict[str, Any]]:
        open_ids = {t.uuid for t in self.open}
        return [
            {
                **{key: entry[key] for key in TASK_KEYS},
                "in_trashed_project": entry["id"] in self.in_trash,
            }
            for entry in self.export["tasks"]
            if entry["id"] in open_ids
        ]

    def tags(self) -> list[dict[str, Any]]:
        order = sorted(self.snapshot.tags, key=lambda tag: (tag.index, tag.uuid))
        return [
            {
                "id": tag.uuid,
                "title": tag.title,
                "open_todos": sum(tag.uuid in t.tag_uuids for t in self.live),
                "completed_total": sum(tag.uuid in t.tag_uuids for t in self.completed),
            }
            for tag in order
        ]

    def templates(self, task_ids: set[str]) -> list[dict[str, Any]]:
        return [
            {
                **{k: v for k, v in entry.items() if k != "notes"},
                "instances": [i for i in entry["instances"] if i in task_ids],
            }
            for entry in self.export["recurring_templates"]
        ]
