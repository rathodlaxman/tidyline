"""Check that a database copy has the tables and columns tidyline reads."""

from __future__ import annotations

import plistlib
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

MIN_SUPPORTED_VERSION = 22  # things.py refuses 21 and below

TESTED_VERSIONS = {
    "macos": "27.0.1",
    "things": "3.24.1",
    "database_version": 29,
}

# Columns come from tests/fixtures/schema.sql and the queries things.py runs,
# plus the recurrence columns DESIGN.md 7.2 needs. TMSettings is deliberately
# absent: it holds the URL-scheme auth token, which tidyline never reads.
REQUIRED_COLUMNS: dict[str, tuple[str, ...]] = {
    "Meta": ("key", "value"),
    "TMArea": ("uuid", "title", "index"),
    "TMTag": ("uuid", "title", "shortcut", "index"),
    "TMTaskTag": ("tasks", "tags"),
    "TMAreaTag": ("areas", "tags"),
    "TMChecklistItem": (
        "uuid",
        "title",
        "status",
        "stopDate",
        "index",
        "task",
        "creationDate",
        "userModificationDate",
    ),
    "TMTask": (
        "uuid",
        "type",
        "status",
        "trashed",
        "title",
        "notes",
        "start",
        "startDate",
        "reminderTime",
        "deadline",
        "deadlineSuppressionDate",
        "stopDate",
        "creationDate",
        "userModificationDate",
        "index",
        "todayIndex",
        "area",
        "project",
        "heading",
        "rt1_repeatingTemplate",
        "rt1_recurrenceRule",
        "rt1_instanceCreationPaused",
    ),
}


class SchemaError(Exception):
    """The database cannot be read safely. The message names the tested versions."""


@dataclass(frozen=True)
class SchemaReport:
    database_version: int
    warnings: tuple[str, ...] = ()


def tested_versions_text() -> str:
    return (
        f"Tested with macOS {TESTED_VERSIONS['macos']}, "
        f"Things {TESTED_VERSIONS['things']}, "
        f"database version {TESTED_VERSIONS['database_version']}."
    )


def is_tested(macos: str | None, things: str | None, database_version: int) -> bool:
    return (
        macos == TESTED_VERSIONS["macos"]
        and things == TESTED_VERSIONS["things"]
        and database_version == TESTED_VERSIONS["database_version"]
    )


def read_database_version(connection: sqlite3.Connection) -> int:
    """Decode Meta.databaseVersion, which is stored as an XML plist."""
    try:
        row = connection.execute(
            "SELECT value FROM Meta WHERE key = 'databaseVersion'"
        ).fetchone()
    except sqlite3.DatabaseError as error:
        raise SchemaError(
            f"Could not read the Meta table ({error}). This does not look like a "
            f"Things database. {tested_versions_text()}"
        ) from error
    if row is None or row[0] is None:
        raise SchemaError(
            "Meta.databaseVersion is missing, so the database version is unknown. "
            f"{tested_versions_text()}"
        )
    value = row[0]
    try:
        version = plistlib.loads(value if isinstance(value, bytes) else value.encode())
    except Exception as error:  # plistlib raises several unrelated types
        raise SchemaError(
            f"Meta.databaseVersion is not a readable plist ({error}). "
            f"{tested_versions_text()}"
        ) from error
    if isinstance(version, bool) or not isinstance(version, int):
        raise SchemaError(
            f"Meta.databaseVersion decoded to {version!r}, not a number. "
            f"{tested_versions_text()}"
        )
    return version


def check_schema(
    database: str | Path,
    *,
    macos_version: str | None = None,
    things_version: str | None = None,
) -> SchemaReport:
    """Check a snapshot copy. Raise SchemaError, or return a report with warnings."""
    uri = f"file:{quote(str(database))}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    try:
        version = read_database_version(connection)
        if version < MIN_SUPPORTED_VERSION:
            raise SchemaError(
                f"Database version {version} is too old; tidyline needs "
                f"{MIN_SUPPORTED_VERSION} or later. Open the database once with "
                f"a current Things 3 so it upgrades. {tested_versions_text()}"
            )
        problems = _missing(connection)
    finally:
        connection.close()

    if problems:
        raise SchemaError(
            "The database does not have what tidyline needs: "
            + "; ".join(problems)
            + f". Things may have changed its format. {tested_versions_text()} "
            "Run `tidyline doctor` and report this on the issue tracker."
        )

    warnings = []
    if version != TESTED_VERSIONS["database_version"]:
        warnings.append(f"Database version {version} is untested.")
    if macos_version != TESTED_VERSIONS["macos"]:
        warnings.append(f"macOS version {macos_version or 'unknown'} is untested.")
    if things_version != TESTED_VERSIONS["things"]:
        warnings.append(f"Things version {things_version or 'unknown'} is untested.")
    if warnings:
        warnings.append(tested_versions_text())
    return SchemaReport(database_version=version, warnings=tuple(warnings))


def _missing(connection: sqlite3.Connection) -> list[str]:
    problems = []
    for table, columns in REQUIRED_COLUMNS.items():
        present = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM pragma_table_info(?)", (table,)
            )
        }
        if not present:
            problems.append(f"table {table} is missing")
            continue
        absent = [column for column in columns if column not in present]
        if absent:
            problems.append(f"table {table} lacks column(s) {', '.join(absent)}")
    return problems
