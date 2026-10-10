"""Copy the Things database to a private temporary file and read only the copy."""

from __future__ import annotations

import os
import sqlite3
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import quote

RETRIES = 3
WAIT_SECONDS = 0.25


class SnapshotError(Exception):
    """The snapshot could not be made. The message says what failed and what to try.

    `permission_problem` is True when macOS probably denied access, so callers
    can explain Full Disk Access.
    """

    def __init__(self, message: str, *, permission_problem: bool = False):
        super().__init__(message)
        self.permission_problem = permission_problem


class _Busy(Exception):
    pass


SQLITE_BUSY, SQLITE_LOCKED = 5, 6  # sqlite3.SQLITE_* constants exist from 3.11
BUSY_TIMEOUT_SECONDS = 0.5


def _abort_if_busy(status: int, remaining: int, total: int) -> None:
    # Connection.backup() otherwise loops for ever while the source is busy, which
    # would defeat the bounded retries in _copy_with_retries.
    if status in (SQLITE_BUSY, SQLITE_LOCKED):
        raise _Busy


@contextmanager
def open_snapshot(
    source: str | os.PathLike,
    *,
    retries: int = RETRIES,
    wait: float = WAIT_SECONDS,
) -> Iterator[Path]:
    """Yield the path of a private copy of `source`; delete it on exit.

    The source is opened read-only (`mode=ro`) and copied with the SQLite backup
    API, which gives a consistent snapshot including changes in the write-ahead
    log. There is no fallback to reading the live file directly.
    """
    source = Path(source)
    with tempfile.TemporaryDirectory(prefix="tidyline-") as directory:
        os.chmod(directory, 0o700)
        copy = Path(directory) / "snapshot.sqlite"
        _copy_with_retries(source, copy, retries, wait)
        yield copy


def _copy_with_retries(source: Path, copy: Path, retries: int, wait: float) -> None:
    for attempt in range(1, retries + 1):
        try:
            _copy_once(source, copy)
            return
        except _Busy:
            copy.unlink(missing_ok=True)
            if attempt == retries:
                raise SnapshotError(
                    f"The Things database at {source} stayed busy after {retries} "
                    "attempts. Wait a few seconds and run tidyline again."
                ) from None
            time.sleep(wait)


def _copy_once(source: Path, copy: Path) -> None:
    try:
        if not source.exists():
            raise SnapshotError(
                f"The database file {source} does not exist. Check the path or "
                "pass --db PATH."
            )
    except PermissionError as error:
        raise _permission_error(source, error) from error

    uri = f"file:{quote(str(source))}?mode=ro"
    reader = writer = None
    try:
        reader = sqlite3.connect(uri, uri=True, timeout=BUSY_TIMEOUT_SECONDS)
        writer = sqlite3.connect(copy)
        reader.backup(writer, sleep=0, progress=_abort_if_busy)
        # Make the copy one plain file, so later read-only opens need no -wal/-shm.
        writer.execute("PRAGMA journal_mode=DELETE")
    except sqlite3.OperationalError as error:
        text = str(error).lower()
        if "locked" in text or "busy" in text:
            raise _Busy from error
        if "unable to open" in text:
            raise _permission_error(source, error) from error
        raise SnapshotError(
            f"SQLite could not read {source}: {error}. Make sure Things is not "
            "mid-update and the file is a Things database."
        ) from error
    except sqlite3.DatabaseError as error:
        raise SnapshotError(
            f"{source} is not a readable SQLite database ({error}). Check that "
            "--db points at Things' main.sqlite file."
        ) from error
    finally:
        for connection in (writer, reader):
            if connection is not None:
                connection.close()
    os.chmod(copy, 0o600)


def _permission_error(source: Path, error: Exception) -> SnapshotError:
    return SnapshotError(
        f"Could not open {source} read-only ({error}). macOS may be blocking "
        "access: give your terminal app Full Disk Access in System Settings > "
        "Privacy & Security, then restart it. Also check the file exists.",
        permission_problem=True,
    )
