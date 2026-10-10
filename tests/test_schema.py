import plistlib
import sqlite3

import pytest

from tidyline.db import schema
from tidyline.db.schema import (
    REQUIRED_COLUMNS,
    TESTED_VERSIONS,
    SchemaError,
    check_schema,
    is_tested,
    read_database_version,
)

TESTED = {
    "macos_version": TESTED_VERSIONS["macos"],
    "things_version": TESTED_VERSIONS["things"],
}


def edit(path, *statements):
    conn = sqlite3.connect(path)
    try:
        for statement in statements:
            conn.execute(statement)
        conn.commit()
    finally:
        conn.close()


def set_version(path, version):
    value = plistlib.dumps(version, fmt=plistlib.FMT_XML).decode()
    edit(path, f"UPDATE Meta SET value = '{value}' WHERE key = 'databaseVersion'")


def test_fixture_passes_with_no_warnings(fixture_db):
    report = check_schema(fixture_db, **TESTED)
    assert report.database_version == 29
    assert report.warnings == ()


def test_required_columns_cover_recurrence_and_exclude_the_token():
    task_columns = REQUIRED_COLUMNS["TMTask"]
    for column in (
        "rt1_recurrenceRule",
        "rt1_repeatingTemplate",
        "rt1_instanceCreationPaused",
    ):
        assert column in task_columns
    assert "TMSettings" not in REQUIRED_COLUMNS
    every = {c for columns in REQUIRED_COLUMNS.values() for c in columns}
    assert "uriSchemeAuthenticationToken" not in every


def test_read_database_version_decodes_xml_plist(fixture_db):
    conn = sqlite3.connect(fixture_db)
    try:
        assert read_database_version(conn) == 29
    finally:
        conn.close()


def test_missing_column_fails_and_names_versions(fixture_db):
    edit(
        fixture_db,
        "ALTER TABLE TMTask RENAME COLUMN rt1_instanceCreationPaused TO renamed",
    )
    with pytest.raises(SchemaError) as error:
        check_schema(fixture_db, **TESTED)
    message = str(error.value)
    assert "TMTask" in message
    assert "rt1_instanceCreationPaused" in message
    assert "macOS 27.0.1" in message
    assert "Things 3.24.1" in message
    assert "database version 29" in message


def test_missing_table_fails(fixture_db):
    edit(fixture_db, "DROP TABLE TMChecklistItem")
    with pytest.raises(SchemaError) as error:
        check_schema(fixture_db, **TESTED)
    assert "table TMChecklistItem is missing" in str(error.value)


@pytest.mark.parametrize("version", [21, 5])
def test_old_database_version_stops(fixture_db, version):
    set_version(fixture_db, version)
    with pytest.raises(SchemaError) as error:
        check_schema(fixture_db, **TESTED)
    message = str(error.value)
    assert f"version {version} is too old" in message
    assert "database version 29" in message


def test_untested_database_version_warns_but_continues(fixture_db):
    set_version(fixture_db, 30)
    report = check_schema(fixture_db, **TESTED)
    assert report.database_version == 30
    assert any("Database version 30 is untested" in w for w in report.warnings)


def test_untested_or_unknown_environment_warns(fixture_db):
    report = check_schema(fixture_db, macos_version="26.1", things_version=None)
    text = " ".join(report.warnings)
    assert "macOS version 26.1 is untested" in text
    assert "Things version unknown is untested" in text


def test_unreadable_version_value_is_a_schema_error(fixture_db):
    edit(fixture_db, "UPDATE Meta SET value = 'not a plist'")
    with pytest.raises(SchemaError):
        check_schema(fixture_db, **TESTED)


def test_not_a_things_database(tmp_path):
    path = tmp_path / "other.sqlite"
    edit(path, "CREATE TABLE unrelated (x)")
    with pytest.raises(SchemaError) as error:
        check_schema(path, **TESTED)
    assert "does not look like a Things database" in str(error.value)


def test_is_tested():
    assert is_tested("27.0.1", "3.24.1", 29)
    assert not is_tested("27.0.1", "3.24.1", 30)
    assert not is_tested(None, "3.24.1", 29)
    assert schema.TESTED_VERSIONS["database_version"] == 29
