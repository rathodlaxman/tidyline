"""Which rows the checks look at. All joins are by UUID."""

from __future__ import annotations

from tidyline.model import Snapshot, Task, TaskKind


class Scope:
    def __init__(self, snapshot: Snapshot):
        self.snapshot = snapshot
        self.tasks = {task.uuid: task for task in snapshot.tasks}

    def heading(self, task: Task) -> Task | None:
        if task.heading_uuid is None:
            return None
        heading = self.tasks.get(task.heading_uuid)
        return heading if heading and heading.kind is TaskKind.HEADING else None

    def project(self, task: Task) -> Task | None:
        """The task's project, directly or through its heading."""
        uuid = task.project_uuid
        if uuid is None:
            heading = self.heading(task)
            uuid = heading.project_uuid if heading else None
        project = self.tasks.get(uuid) if uuid else None
        return project if project and project.kind is TaskKind.PROJECT else None

    def trashed_container(self, task: Task) -> Task | None:
        """The trashed heading or project the task sits in, if any."""
        heading = self.heading(task)
        if heading is not None and heading.trashed:
            return heading
        project = self.project(task)
        if project is not None and project.trashed:
            return project
        return None

    def open_todos(self) -> list[Task]:
        """Open, untrashed to-dos (templates excluded), wherever they sit."""
        return [t for t in self.snapshot.todos if not t.is_closed and not t.trashed]

    def in_scope_todos(self) -> list[Task]:
        """Open to-dos the app shows: not trashed, not in a trashed container."""
        return [t for t in self.open_todos() if self.trashed_container(t) is None]

    def open_projects(self) -> list[Task]:
        return [p for p in self.snapshot.projects if not p.is_closed and not p.trashed]
