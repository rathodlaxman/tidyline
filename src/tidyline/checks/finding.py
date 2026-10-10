"""The Finding type shared by every health check (DESIGN.md 7.3)."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal

from tidyline.model import Task, TaskKind

Severity = Literal["warning", "info"]
RefKind = Literal["task", "project", "heading", "template"]


@dataclass(frozen=True)
class Ref:
    """What a finding is about, by UUID. Titles are looked up by renderers."""

    kind: RefKind
    id: str


@dataclass(frozen=True)
class Finding:
    check: str
    severity: Severity
    message: str  # fixed wording; never a title, note or user pattern
    refs: tuple[Ref, ...]


@dataclass(frozen=True)
class CheckOptions:
    """User settings for checks. `patterns` feed title_hygiene."""

    patterns: tuple[re.Pattern[str], ...] = field(default=())


def ref(task: Task) -> Ref:
    if task.is_template:
        return Ref("template", task.uuid)
    kinds: Mapping[TaskKind, RefKind] = {
        TaskKind.TODO: "task",
        TaskKind.PROJECT: "project",
        TaskKind.HEADING: "heading",
    }
    return Ref(kinds[task.kind], task.uuid)


def ordered(tasks) -> list[Task]:
    """Things order: the stored index, then uuid so ties are stable."""
    return sorted(tasks, key=lambda task: (task.index, task.uuid))
