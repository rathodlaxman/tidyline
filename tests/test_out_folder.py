"""The folder for --out (DESIGN.md decisions log, 2026-10-11).

Only the last level is created, never a chain; only when its parent exists and
is a folder; with mode 0700; an existing folder is never changed. The same
rules apply to report, export, decode (the folder of the file) and prompt (the
--out folder itself).
"""

import json
import os
import stat
from pathlib import Path

import pytest

from tidyline import cli


@pytest.fixture(autouse=True)
def no_real_app(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "THINGS_INFO_PLIST", tmp_path / "missing.plist")


def report_args(folder, db):
    return ["--db", db, "report", "--out", str(folder / "out.txt")]


def export_args(folder, db):
    return ["--db", db, "export", "--out", str(folder / "out.json")]


def decode_args(folder, db):
    answer = Path(db).parent / "answer.md"
    answer.write_text("Task aaaaaa", encoding="utf-8")
    return ["--db", db, "decode", str(answer), "--out", str(folder / "out.md")]


def prompt_args(folder, db):
    return ["--db", db, "prompt", "--out", str(folder)]


FILE_NAMES = {report_args: "out.txt", export_args: "out.json", decode_args: "out.md"}

COMMANDS = pytest.mark.parametrize(
    "make_args", [report_args, export_args, decode_args, prompt_args]
)


@pytest.fixture
def base(tmp_path):
    """A folder for the test; the folder under test is made inside it."""
    folder = tmp_path / "base"
    folder.mkdir(mode=0o700)
    return folder


def run(make_args, folder, db):
    return cli.main(make_args(folder, str(db)))


@COMMANDS
def test_creates_the_last_level_with_mode_0700(make_args, fixture_db, base, capsys):
    folder = base / "new"
    old = os.umask(0)  # a loose umask must not loosen the folder
    try:
        assert run(make_args, folder, fixture_db) == 0
    finally:
        os.umask(old)
    assert stat.S_IMODE(folder.stat().st_mode) == 0o700
    assert list(folder.iterdir())
    err = capsys.readouterr().err
    assert f"Created folder {folder} (readable only by you).\n" in err
    assert err.count("Created folder") == 1


@COMMANDS
def test_a_strict_umask_still_gives_0700(make_args, fixture_db, base):
    folder = base / "new"
    old = os.umask(0o077)
    try:
        assert run(make_args, folder, fixture_db) == 0
    finally:
        os.umask(old)
    assert stat.S_IMODE(folder.stat().st_mode) == 0o700


@COMMANDS
def test_never_creates_a_chain(make_args, fixture_db, base, capsys):
    folder = base / "one" / "two"
    assert run(make_args, folder, fixture_db) == 2
    assert not (base / "one").exists()
    err = capsys.readouterr().err
    assert "error:" in err and "neither does" in err
    assert "Create the parent folder yourself" in err
    assert "Created folder" not in err


@COMMANDS
def test_parent_that_is_a_file_is_refused(make_args, fixture_db, base, capsys):
    parent = base / "afile"
    parent.write_text("x", encoding="utf-8")
    assert run(make_args, parent / "new", fixture_db) == 2
    assert parent.read_text(encoding="utf-8") == "x"
    err = capsys.readouterr().err
    assert f"{parent} exists and is not a folder" in err


def test_folder_that_is_a_file_is_refused_for_prompt(fixture_db, base, capsys):
    target = base / "afile"
    target.write_text("x", encoding="utf-8")
    assert run(prompt_args, target, fixture_db) == 2
    assert f"{target} exists and is not a folder" in capsys.readouterr().err


@COMMANDS
def test_existing_folder_is_not_changed_and_loose_modes_warn(
    make_args, fixture_db, base, capsys
):
    folder = base / "shared"
    folder.mkdir()
    os.chmod(folder, 0o755)
    assert run(make_args, folder, fixture_db) == 0
    assert stat.S_IMODE(folder.stat().st_mode) == 0o755  # not tightened
    err = capsys.readouterr().err
    assert f"warning: the folder {folder} can be read by other users" in err
    assert "Created folder" not in err


@COMMANDS
def test_group_readable_folder_warns_too(make_args, fixture_db, base, capsys):
    folder = base / "group"
    folder.mkdir()
    os.chmod(folder, 0o750)
    assert run(make_args, folder, fixture_db) == 0
    assert stat.S_IMODE(folder.stat().st_mode) == 0o750
    assert "can be read by other users" in capsys.readouterr().err


@COMMANDS
def test_private_existing_folder_has_no_warning(make_args, fixture_db, base, capsys):
    folder = base / "mine"
    folder.mkdir(mode=0o700)
    assert run(make_args, folder, fixture_db) == 0
    err = capsys.readouterr().err
    assert "can be read by other users" not in err
    assert "Created folder" not in err


@pytest.mark.parametrize("make_args", [report_args, export_args, decode_args])
def test_existing_file_is_never_overwritten(make_args, fixture_db, base, capsys):
    folder = base / "mine"
    folder.mkdir(mode=0o700)
    target = folder / FILE_NAMES[make_args]
    target.write_text("keep", encoding="utf-8")
    assert run(make_args, folder, fixture_db) == 2
    assert target.read_text(encoding="utf-8") == "keep"
    assert "already exists" in capsys.readouterr().err


def test_existing_prompt_files_are_never_overwritten(fixture_db, base, capsys):
    folder = base / "mine"
    folder.mkdir(mode=0o700)
    (folder / "tidyline_payload.json").write_text("keep", encoding="utf-8")
    assert run(prompt_args, folder, fixture_db) == 2
    assert (folder / "tidyline_payload.json").read_text(encoding="utf-8") == "keep"
    assert "already in" in capsys.readouterr().err


@COMMANDS
def test_no_folder_is_made_when_the_database_cannot_be_read(
    make_args, base, tmp_path, capsys
):
    folder = base / "new"
    assert run(make_args, folder, tmp_path / "none.sqlite") != 0
    assert not folder.exists()
    assert "Created folder" not in capsys.readouterr().err


@COMMANDS
def test_a_failed_write_does_not_leave_the_new_folder(
    make_args, fixture_db, base, monkeypatch, capsys
):
    def fail(path, text):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(cli, "_write_private", fail)
    folder = base / "new"
    assert run(make_args, folder, fixture_db) == 3
    assert not folder.exists()


def test_out_stays_required_for_export_and_prompt_has_no_default(
    fixture_db, tmp_path, monkeypatch, capsys
):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit) as error:
        cli.main(["--db", str(fixture_db), "export"])
    assert error.value.code == 2
    assert cli.main(["--db", str(fixture_db), "prompt"]) == 0
    assert "Nothing was written." in capsys.readouterr().out
    assert not any(p.name.startswith("tidyline_") for p in tmp_path.iterdir())


def test_payload_is_still_readable_json_after_creating_the_folder(fixture_db, base):
    folder = base / "new"
    assert run(prompt_args, folder, fixture_db) == 0
    data = json.loads((folder / "tidyline_payload.json").read_text(encoding="utf-8"))
    assert data["anonymisation"] == "strict"
