import dataclasses
import datetime as dt

import pytest

from tidyline.model import (
    STATUS_CANCELLED,
    STATUS_COMPLETED,
    STATUS_OPEN,
    Area,
    ChecklistItem,
    Snapshot,
    Tag,
    Task,
    TaskKind,
)
from tidyline.recurrence import parse_rule


def todo(**fields):
    return Task(uuid="u1", kind=TaskKind.TODO, title="A task", **fields)


def test_defaults():
    task = todo()
    assert task.status == STATUS_OPEN
    assert not task.trashed
    assert task.tag_uuids == ()
    assert task.recurrence is None
    assert not task.is_template


@pytest.mark.parametrize(
    "obj",
    [
        todo(),
        Area(uuid="a", title="Home"),
        Tag(uuid="t", title="errand"),
        ChecklistItem(uuid="c", task_uuid="u1", title="Step"),
        Snapshot(),
    ],
)
def test_classes_are_frozen(obj):
    assert dataclasses.is_dataclass(obj)
    field = dataclasses.fields(obj)[0].name
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(obj, field, "changed")


def test_closed_statuses():
    assert todo(status=STATUS_COMPLETED).is_closed
    assert todo(status=STATUS_CANCELLED).is_closed
    assert not todo(status=STATUS_OPEN).is_closed


def test_template_has_a_rule():
    rule = parse_rule({"fu": 16, "fa": 1, "tp": 0, "of": [{"dy": 0}], "rrv": 4})
    template = todo(recurrence=rule)
    assert template.is_template
    assert template.recurrence.text == "Daily"
    hash(template)  # a Task with a Rule stays hashable


def test_snapshot_holds_tuples_and_references_by_uuid():
    heading = Task(uuid="h", kind=TaskKind.HEADING, title="Plan", project_uuid="p")
    item = todo(heading_uuid="h", tag_uuids=("t",), start_date=dt.date(2026, 1, 1))
    snapshot = Snapshot(
        areas=(Area(uuid="a", title="Home"),),
        tags=(Tag(uuid="t", title="errand"),),
        tasks=(heading, item),
    )
    assert isinstance(snapshot.tasks, tuple)
    assert item.heading_uuid == heading.uuid
    assert item.project_uuid is None
