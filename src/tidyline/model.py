"""Frozen data model (DESIGN.md section 8).

Everything refers to everything else by UUID, never by title. Collections are
tuples. These classes hold data only: `read.py` fills them and `status.py`
interprets them.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from enum import Enum

from tidyline.recurrence import Rule

# TMTask.start
START_INBOX = 0
START_ANYTIME = 1
START_SOMEDAY = 2

# TMTask.status (1 has not been seen)
STATUS_OPEN = 0
STATUS_CANCELLED = 2
STATUS_COMPLETED = 3

CLOSED_STATUSES = frozenset({STATUS_CANCELLED, STATUS_COMPLETED})

# TMTask.startBucket: 1 is This Evening
BUCKET_THIS_EVENING = 1


class TaskKind(Enum):
    TODO = "to-do"  # TMTask.type 0
    PROJECT = "project"  # type 1
    HEADING = "heading"  # type 2


@dataclass(frozen=True)
class Area:
    uuid: str
    title: str
    index: int = 0


@dataclass(frozen=True)
class Tag:
    uuid: str
    title: str
    index: int = 0


@dataclass(frozen=True)
class ChecklistItem:
    uuid: str
    task_uuid: str
    title: str
    status: int = STATUS_OPEN
    index: int = 0


@dataclass(frozen=True)
class Task:
    """A to-do, project or heading.

    A to-do under a heading has `heading_uuid` set and `project_uuid` None; the
    heading row carries the project. A recurring template has `recurrence` set;
    its visible instances have `recurrence_template_uuid` set instead.

    Dates are None when the column is NULL. `read.py` must not let a non-NULL
    value that fails to unpack pass as NULL: for `start_date` and
    `deadline_suppression_date` that would change the effective status.
    """

    uuid: str
    kind: TaskKind
    title: str
    notes: str | None = None
    status: int = STATUS_OPEN
    trashed: bool = False
    start: int = START_ANYTIME
    start_date: dt.date | None = None
    start_bucket: int = 0
    deadline: dt.date | None = None
    deadline_suppression_date: dt.date | None = None
    area_uuid: str | None = None
    project_uuid: str | None = None
    heading_uuid: str | None = None
    tag_uuids: tuple[str, ...] = ()
    recurrence_template_uuid: str | None = None
    recurrence: Rule | None = None
    recurrence_paused: bool = False
    created: dt.datetime | None = None
    modified: dt.datetime | None = None
    stopped: dt.datetime | None = None
    index: int = 0

    @property
    def is_closed(self) -> bool:
        return self.status in CLOSED_STATUSES

    @property
    def is_template(self) -> bool:
        return self.recurrence is not None


@dataclass(frozen=True)
class Snapshot:
    areas: tuple[Area, ...] = ()
    tags: tuple[Tag, ...] = ()
    tasks: tuple[Task, ...] = ()
    checklist_items: tuple[ChecklistItem, ...] = ()
