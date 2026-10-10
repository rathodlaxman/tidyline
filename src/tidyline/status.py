"""Effective status of a task (DESIGN.md section 7.1).

Pure function: `today` is always passed in, the clock is never read.
"""

from __future__ import annotations

import datetime as dt
from enum import Enum

from tidyline.model import (
    BUCKET_THIS_EVENING,
    START_INBOX,
    START_SOMEDAY,
    Task,
)


class Status(Enum):
    INBOX = "inbox"
    TODAY = "today"
    THIS_EVENING = "this evening"
    UPCOMING = "upcoming"
    ANYTIME = "anytime"
    SOMEDAY = "someday"
    CLOSED = "closed"


def effective_status(task: Task, parent_project: Task | None, today: dt.date) -> Status:
    """Where Things shows `task`.

    `parent_project` is the project the task belongs to (directly, or through
    its heading), or None. The caller resolves it by UUID.
    """
    # Step 0: completed, cancelled or trashed tasks are not on any list.
    if task.is_closed or task.trashed:
        return Status.CLOSED
    # 7.1 rule 1: Inbox.
    if task.start == START_INBOX:
        return Status.INBOX
    # 7.1 rule 2: everything inside a Someday project is parked, whatever its
    # own dates say.
    if parent_project is not None and parent_project.start == START_SOMEDAY:
        return Status.SOMEDAY
    if task.start_date is not None:
        # 7.1 rule 3: a start date after today.
        if task.start_date > today:
            return Status.UPCOMING
        # 7.1 rule 4: a start date of today or earlier. startBucket 1 is This
        # Evening, whatever `start` is.
        if task.start_bucket == BUCKET_THIS_EVENING:
            return Status.THIS_EVENING
        return Status.TODAY
    # 7.1 rule 5: no start date, deadline today or earlier, deadline not
    # suppressed. Untested on real data (DESIGN 7.1, 11): it follows things.py
    # and is covered only by the synthetic fixture.
    if (
        task.deadline is not None
        and task.deadline <= today
        and not task.deadline_suppressed
    ):
        return Status.TODAY
    # 7.1 rule 6: Someday.
    if task.start == START_SOMEDAY:
        return Status.SOMEDAY
    # 7.1 rule 7: everything else.
    return Status.ANYTIME
