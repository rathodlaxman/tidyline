import os
from pathlib import Path

import pytest

from tidyline.db.locate import (
    CONTAINER,
    DATABASE_PARTS,
    DatabaseNotFoundError,
    locate_database,
)


def make_standard(home: Path, name: str = "ThingsData-AAAA") -> Path:
    path = home / CONTAINER / name / Path(*DATABASE_PARTS)
    path.parent.mkdir(parents=True)
    path.write_bytes(b"")
    return path


def touch(path: Path) -> Path:
    path.write_bytes(b"")
    return path


def test_db_option_beats_env_and_standard(tmp_path):
    option = touch(tmp_path / "option.sqlite")
    env_file = touch(tmp_path / "env.sqlite")
    make_standard(tmp_path)
    found = locate_database(option, environ={"THINGSDB": str(env_file)}, home=tmp_path)
    assert found == option


def test_env_beats_standard(tmp_path):
    env_file = touch(tmp_path / "env.sqlite")
    make_standard(tmp_path)
    found = locate_database(None, environ={"THINGSDB": str(env_file)}, home=tmp_path)
    assert found == env_file


def test_standard_location_is_globbed(tmp_path):
    standard = make_standard(tmp_path)
    assert locate_database(None, environ={}, home=tmp_path) == standard


def test_newest_thingsdata_directory_wins(tmp_path):
    old = make_standard(tmp_path, "ThingsData-OLD1")
    new = make_standard(tmp_path, "ThingsData-NEW2")
    os.utime(old, (1_000_000, 1_000_000))
    os.utime(new, (2_000_000, 2_000_000))
    assert locate_database(None, environ={}, home=tmp_path) == new


def test_nothing_found_lists_everything_tried(tmp_path):
    with pytest.raises(DatabaseNotFoundError) as error:
        locate_database(None, environ={}, home=tmp_path)
    message = str(error.value)
    assert "--db" in message
    assert "THINGSDB" in message
    assert "ThingsData-*" in message
    assert "pass --db PATH" in message


def test_bad_db_option_does_not_fall_through(tmp_path):
    make_standard(tmp_path)
    missing = tmp_path / "missing.sqlite"
    with pytest.raises(DatabaseNotFoundError) as error:
        locate_database(missing, environ={}, home=tmp_path)
    assert str(missing) in str(error.value)


def test_bad_env_does_not_fall_through(tmp_path):
    make_standard(tmp_path)
    with pytest.raises(DatabaseNotFoundError) as error:
        locate_database(
            None, environ={"THINGSDB": str(tmp_path / "nope")}, home=tmp_path
        )
    assert "THINGSDB" in str(error.value)
