"""`tidyline decode`, against the synthetic fixture only."""

import datetime as dt
import hashlib
import os
import re
import sqlite3
import stat

import pytest
from fixtures import build_fixture as bf

from tidyline import cli
from tidyline import decode as decode_module
from tidyline.anonymise import LABEL_PATTERN, anonymise, make_labels
from tidyline.db.snapshot import open_snapshot
from tidyline.decode import decode_text, label_map
from tidyline.read import read_snapshot
from tidyline.render.json_out import build_export

U = bf.make_uuid


def snapshot_of(path):
    with open_snapshot(path) as copy:
        return read_snapshot(copy)


def strict_export(path):
    export = build_export(
        snapshot_of(path),
        today=dt.date(2026, 10, 10),
        exported_at=dt.datetime(2026, 10, 10, 12, tzinfo=dt.timezone.utc),
        tool_version="test",
        environment={},
    )
    return anonymise(export, "strict")


def labels_by_id(export):
    found = {}
    for area in export["areas"]:
        found[area["id"]] = area["title"]
    for key in ("projects", "headings", "tasks", "recurring_templates"):
        for entry in export[key]:
            found[entry["id"]] = entry["title"]
            for tag in entry.get("tags") or []:
                found[tag["id"]] = tag["title"]
    return found


@pytest.fixture
def labels(fixture_db):
    return labels_by_id(strict_export(fixture_db))


@pytest.fixture
def mapping(fixture_db):
    return label_map(snapshot_of(fixture_db))


# --- core --------------------------------------------------------------------------


def test_round_trip_through_a_strict_export(fixture_db, labels, mapping):
    answer = (
        f"Move {labels[U('t_measure')]} under {labels[U('head_build')]} in "
        f"{labels[U('proj_garden')]} ({labels[U('area_home')]}). Tag it "
        f"{labels[U('tag_errand')]}. Review {labels[U('tpl_monthly_15')]}.\n"
    )
    result = decode_text(answer, mapping)
    assert result.text == (
        'Move "Measure the plot" under "Build" in "Garden Shed Rebuild" '
        '("Household"). Tag it "errand". Review "Pay the rent".\n'
    )
    assert (result.replaced, result.distinct, result.unmatched) == (6, 6, ())


def test_every_strict_label_maps_back_to_its_stored_title(fixture_db, labels, mapping):
    snapshot = snapshot_of(fixture_db)
    titles = {t.uuid: t.title for t in snapshot.tasks}
    titles |= {a.uuid: a.title for a in snapshot.areas}
    titles |= {t.uuid: t.title for t in snapshot.tags}
    for item_id, label in labels.items():
        assert mapping[label] == titles[item_id], label


def test_labels_in_markdown(labels, mapping):
    task, project = labels[U("t_lease")], labels[U("proj_photos")]
    answer = (
        f"{task} starts the line\n"
        f"- **{task}** and `{project}`\n"
        f"| {task} | {project} |\n"
        f'"{project}" ends the line: {task}\n'
        f"_{project}_"
    )
    result = decode_text(answer, mapping)
    lease = "Renew the lease at www.example.com/flat-12"
    photos = "Photo Archive Cleanup"
    assert result.text == (
        f'"{lease}" starts the line\n'
        f'- **"{lease}"** and `{photos}`\n'
        f'| "{lease}" | "{photos}" |\n'
        f'"{photos}" ends the line: "{lease}"\n'
        f'_"{photos}"_'
    )
    assert (result.replaced, result.distinct) == (8, 2)


def test_label_in_underscore_italics_is_replaced(labels, mapping):
    project = labels[U("proj_photos")]
    assert decode_text(f"_{project}_", mapping).text == '_"Photo Archive Cleanup"_'


def test_unknown_labels_stay_and_are_counted(mapping):
    answer = "Task aaaaaa and Task aaaaaa and Project 222222 and Area zzzzzz."
    result = decode_text(answer, mapping)
    assert result.text == answer
    assert result.replaced == 0
    assert result.unmatched == ("Area zzzzzz", "Project 222222", "Task aaaaaa")


def test_longer_words_containing_a_label_are_not_touched(labels, mapping):
    task = labels[U("t_lease")]
    kind, code = task.split(" ")
    answer = f"{task}x / {task}2 / {kind} {code}9 / x{code} / {code}s / {kind}{code}"
    result = decode_text(answer, mapping)
    assert result.text == answer
    assert (result.replaced, result.bare_replaced) == (0, 0)


def test_a_title_that_looks_like_a_label_is_not_replaced_again(labels):
    first, second = labels[U("t_lease")], labels[U("t_level")]
    result = decode_text(f"{first} then {second}", {first: second, second: "Level"})
    assert result.text == f'"{second}" then "Level"'
    assert result.replaced == 2


def quoted_parts(text):
    return " / ".join(f'"{part}"' for part in text.split(" / "))


def test_unicode_titles_round_trip(fixture_db, labels, mapping):
    answer = " / ".join(labels[U(k)] for k in ("t_card", "t_ja", "t_de", "t_es"))
    result = decode_text(answer, mapping)
    assert result.text == quoted_parts(
        "Ｂuy a ﬁrst-birthday card for Zoé / 請求書の写真を整理する / "
        "Müll rausbringen und Gelbe Säcke holen / Comprar pimentón y azafrán"
    )


def test_pipe_in_a_title_is_escaped_in_a_table_row(fixture_db):
    conn = sqlite3.connect(fixture_db)
    conn.execute(
        "UPDATE TMTask SET title = ? WHERE uuid = ?",
        ("Fix a|b *now* `cmd`", U("t_level")),
    )
    conn.commit()
    conn.close()
    label = labels_by_id(strict_export(fixture_db))[U("t_level")]
    row = f"| {label} | MOVE |"
    result = decode_text(row, label_map(snapshot_of(fixture_db)))
    # "|" is escaped on a table line; other markdown characters are not.
    assert result.text == '| "Fix a\\|b *now* `cmd`" | MOVE |'
    assert result.text.replace("\\|", "").count("|") == 3


def test_label_pattern_matches_what_make_labels_writes():
    ids = [U(f"p{n}") for n in range(200)]
    for kind in ("area", "project", "heading", "task", "tag", "template"):
        for label in make_labels(kind, ids).values():
            assert LABEL_PATTERN.fullmatch(label), label
    for suffix in ("abcd", "a" * 46):  # collision forms
        assert LABEL_PATTERN.fullmatch(f"Task abcdef-{suffix}")


# --- CLI ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def no_real_app(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "THINGS_INFO_PLIST", tmp_path / "missing.plist")


def write_answer(tmp_path, text):
    path = tmp_path / "answer.md"
    path.write_text(text, encoding="utf-8")
    return path


def run(fixture_db, *args):
    return cli.main(["--db", str(fixture_db), "decode", *args])


def test_cli_prints_decoded_text_and_summary(fixture_db, tmp_path, labels, capsys):
    answer = write_answer(
        tmp_path, f"Do {labels[U('t_level')]} first. Skip Task aaaaaa.\n"
    )
    assert run(fixture_db, str(answer)) == 0
    captured = capsys.readouterr()
    assert captured.out == 'Do "Buy a spirit level" first. Skip Task aaaaaa.\n'
    assert (
        "Decoded: 1 labels replaced, 0 bare codes replaced (1 distinct items)."
        in captured.err
    )
    assert "1 distinct label-like strings matched nothing" in captured.err
    assert "personal data" in captured.err
    assert "Buy a spirit level" not in captured.err  # titles never in the report
    assert "aaaaaa" not in captured.err


def test_cli_db_after_the_command(fixture_db, tmp_path, labels, capsys):
    answer = write_answer(tmp_path, labels[U("t_level")])
    assert cli.main(["decode", str(answer), "--db", str(fixture_db)]) == 0
    assert capsys.readouterr().out == '"Buy a spirit level"'


def test_cli_out_writes_a_private_file(fixture_db, tmp_path, labels, capsys):
    answer = write_answer(tmp_path, labels[U("t_level")] + "\n")
    out = tmp_path / "decoded.md"
    old = os.umask(0)
    try:
        assert run(fixture_db, str(answer), "--out", str(out)) == 0
    finally:
        os.umask(old)
    assert stat.S_IMODE(out.stat().st_mode) == 0o600
    assert out.read_text(encoding="utf-8") == '"Buy a spirit level"\n'
    captured = capsys.readouterr()
    assert "Wrote the decoded answer to" in captured.out
    assert "Buy a spirit level" not in captured.out


def test_cli_out_refuses_overwrite_before_reading(
    fixture_db, tmp_path, monkeypatch, capsys
):
    answer = write_answer(tmp_path, "Task aaaaaa")
    out = tmp_path / "decoded.md"
    out.write_text("keep", encoding="utf-8")

    def never(args):
        raise AssertionError("the database must not be read")

    monkeypatch.setattr(cli, "_load", never)
    assert run(fixture_db, str(answer), "--out", str(out)) == 2
    assert out.read_text(encoding="utf-8") == "keep"
    assert "already exists" in capsys.readouterr().err


def test_cli_out_creates_the_last_folder_level(fixture_db, tmp_path, capsys):
    answer = write_answer(tmp_path, "Task aaaaaa")
    out = tmp_path / "new" / "x.md"
    assert run(fixture_db, str(answer), "--out", str(out)) == 0
    assert out.is_file()
    assert f"Created folder {out.parent} (readable only by you)." in (
        capsys.readouterr().err
    )


def test_cli_write_failure_exits_3(fixture_db, tmp_path, monkeypatch, capsys):
    answer = write_answer(tmp_path, "Task aaaaaa")

    def fail(path, text):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(cli, "_write_private", fail)
    assert run(fixture_db, str(answer), "--out", str(tmp_path / "x.md")) == 3


def test_cli_missing_answer_file(fixture_db, tmp_path, capsys):
    assert run(fixture_db, str(tmp_path / "none.md")) == 2
    err = capsys.readouterr().err
    assert "could not read" in err and "save the answer to a text file" in err


def test_cli_answer_is_a_folder(fixture_db, tmp_path, capsys):
    assert run(fixture_db, str(tmp_path)) == 2
    assert "could not read" in capsys.readouterr().err


def test_cli_invalid_utf8(fixture_db, tmp_path, capsys):
    answer = tmp_path / "answer.md"
    answer.write_bytes(b"Task \xff\xfe broken")
    assert run(fixture_db, str(answer)) == 2
    assert "not valid UTF-8" in capsys.readouterr().err


def test_cli_oversize_file(fixture_db, tmp_path, capsys):
    answer = tmp_path / "answer.md"
    answer.write_bytes(b"x" * (5 * 1024 * 1024 + 1))
    assert run(fixture_db, str(answer)) == 2
    assert "at most 5 MB" in capsys.readouterr().err


@pytest.mark.parametrize("text", ["", "  \n\n"])
def test_cli_empty_answer(fixture_db, tmp_path, monkeypatch, capsys, text):
    answer = write_answer(tmp_path, text)

    def never(args):
        raise AssertionError("no need to read the database")

    monkeypatch.setattr(cli, "_load", never)
    assert run(fixture_db, str(answer)) == 0
    captured = capsys.readouterr()
    assert captured.out == text
    assert "empty; nothing was replaced" in captured.err


def test_cli_missing_database_exits_3(tmp_path, capsys):
    answer = write_answer(tmp_path, "Task aaaaaa")
    assert cli.main(["--db", str(tmp_path / "none.sqlite"), "decode", str(answer)]) == 3


def test_cli_never_writes_to_the_database(fixture_db, tmp_path, labels, capsys):
    before = hashlib.sha256(fixture_db.read_bytes()).hexdigest()
    mtime = fixture_db.stat().st_mtime_ns
    answer = write_answer(tmp_path, labels[U("t_level")])
    assert run(fixture_db, str(answer)) == 0
    assert hashlib.sha256(fixture_db.read_bytes()).hexdigest() == before
    assert fixture_db.stat().st_mtime_ns == mtime


def test_decode_module_has_no_network_or_print():
    with open(decode_module.__file__, encoding="utf-8") as handle:
        source = handle.read()
    imports = re.findall(r"^\s*(?:import|from)\s+([\w.]+)", source, re.M)
    forbidden = {"socket", "urllib", "http", "requests", "subprocess", "ssl"}
    assert [m for m in imports if m.split(".")[0] in forbidden] == []
    assert not re.search(r"\bprint\(", source)


def test_help_lists_decode(capsys):
    with pytest.raises(SystemExit):
        cli.main(["--help"])
    assert "decode" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        cli.main(["decode", "--help"])
    out = capsys.readouterr().out
    for option in ("ANSWER_FILE", "--out", "--db"):
        assert option in out


def test_decode_builds_no_export():
    # decode needs titles only: it neither exports nor anonymises
    with open(decode_module.__file__, encoding="utf-8") as handle:
        source = handle.read()
    assert "build_export" not in source and "anonymise(" not in source
