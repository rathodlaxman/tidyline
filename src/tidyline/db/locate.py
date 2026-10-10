"""Find the Things database file. Looks at file paths only; never reads the database."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

ENV_VAR = "THINGSDB"
CONTAINER = Path("Library/Group Containers/JLMPQHK86H.com.culturedcode.ThingsMac")
DATA_PREFIX = "ThingsData-"
DATABASE_PARTS = ("Things Database.thingsdatabase", "main.sqlite")
STANDARD_PATTERN = f"~/{CONTAINER}/{DATA_PREFIX}*/{'/'.join(DATABASE_PARTS)}"


class DatabaseNotFoundError(Exception):
    """No Things database could be found. The message says what was tried."""


def locate_database(
    db_option: str | os.PathLike | None = None,
    environ: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> Path:
    """Return the database path: --db, then THINGSDB, then the standard location.

    An explicit --db or THINGSDB that does not point at a file is an error; it
    never falls through to the next source. A PermissionError while looking at
    the standard location is not caught, so the caller can explain it.
    """
    env = os.environ if environ is None else environ
    home = Path.home() if home is None else Path(home)

    if db_option:
        path = Path(db_option).expanduser()
        if path.is_file():
            return path
        raise DatabaseNotFoundError(
            f"Tried the --db path {path}, but it is not a file. "
            "Check the path, or leave out --db to search the standard location."
        )

    from_env = env.get(ENV_VAR)
    if from_env:
        path = Path(from_env).expanduser()
        if path.is_file():
            return path
        raise DatabaseNotFoundError(
            f"Tried the {ENV_VAR} environment variable ({path}), but it is not a "
            f"file. Fix or unset {ENV_VAR}, or pass --db PATH."
        )

    candidates = _standard_candidates(home)
    if candidates:
        return max(candidates, key=lambda p: (p.stat().st_mtime, str(p)))

    raise DatabaseNotFoundError(
        "Could not find a Things database. Tried, in order: "
        "the --db option (not given); "
        f"the {ENV_VAR} environment variable (not set); "
        f"the standard location {STANDARD_PATTERN} (no match). "
        "Open Things 3 once so it creates its database, or pass --db PATH."
    )


def _standard_candidates(home: Path) -> list[Path]:
    try:
        entries = list(os.scandir(home / CONTAINER))
    except (FileNotFoundError, NotADirectoryError):
        return []
    found = []
    for entry in entries:
        if entry.name.startswith(DATA_PREFIX):
            path = Path(entry.path, *DATABASE_PARTS)
            if path.is_file():
                found.append(path)
    return found
