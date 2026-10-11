"""`tidyline prompt` and llm/prompt.py, against the synthetic fixture only.

pbcopy is always mocked; it is never run for real.
"""

import datetime as dt
import json
import os
import re
import sqlite3
import stat
import subprocess
import unicodedata
from importlib import resources

import pytest
from fixtures import build_fixture as bf

from tidyline import cli
from tidyline.db.snapshot import open_snapshot
from tidyline.llm import prompt as prompt_module
from tidyline.llm.payload import build_payload
from tidyline.llm.prompt import (
    CONTEXT_FIELDS,
    PART5_BODIES,
    Context,
    ContextError,
    build_prompt,
    load_template,
    parse_context,
)
from tidyline.read import read_snapshot

U = bf.make_uuid
FAKE_PII = (
    "landlord@example.com",
    "www.example.com",
    "+91 98765 43210",
    "555-010-4477",
    "25000000",
    "12345678",
    "1,500",
    "$1,200.00",
)
LIGHT_PART5 = """Review task titles. For tasks that are genuinely vague or non-actionable, rewrite them as:

**ACTION VERB + SPECIFIC OBJECT + CLEAR OUTCOME**

Examples:

- Vague: "Work on CV". Better: "Rewrite professional summary in 2-page CV"
- Vague: "Study Python". Better: "Complete Pandas filtering exercise"
- Vague: "Research certifications". Better: "Compare 3 certification options on fees, duration and eligibility"

Do not rewrite every task unnecessarily. Only rewrite where the wording is genuinely unclear."""  # noqa: E501
STRICT_PART5 = (
    "Titles are hidden in this data, so task wording cannot be judged. Skip this "
    "part and write one line saying so. Do not guess at task wording."
)
PLACEHOLDERS = (
    "[ROLE AND SITUATION]",
    "[MAJOR RESPONSIBILITIES AND PRIORITIES]",
    "[KEY DATES AND TRANSITIONS]",
)
CONTEXT = """Role: Freelance designer
working from home.

Priorities:
- Ship the studio site
- Keep Sundays free

Dates: Move house in March 2027.
"""


def fold(text):
    return unicodedata.normalize("NFKC", text).casefold()


def payload_of(path, level):
    with open_snapshot(path) as copy:
        snapshot = read_snapshot(copy)
    return build_payload(
        snapshot,
        today=dt.date(2026, 10, 10),
        exported_at=dt.datetime(2026, 10, 10, 12, tzinfo=dt.timezone.utc),
        level=level,
    )


def stored_strings(path):
    conn = sqlite3.connect(path)
    try:
        found = []
        for sql in (
            "SELECT title FROM TMTask",
            "SELECT notes FROM TMTask",
            "SELECT title FROM TMArea",
            "SELECT title FROM TMTag",
            "SELECT title FROM TMChecklistItem",
        ):
            found += [row[0] for row in conn.execute(sql) if row[0]]
    finally:
        conn.close()
    return found


# --- template and fixed texts -----------------------------------------------------


def test_template_is_packaged_and_loads():
    text = (
        resources.files("tidyline.llm").joinpath("audit_prompt.md").read_text("utf-8")
    )
    assert text.startswith("# Things 3 System Audit")
    assert load_template() == text
    assert set(re.findall(r"\{\{([A-Z0-9_]+)\}\}", text)) == {
        "DATA_NOTE",
        "PART5_BODY",
        "CONTEXT_ROLE",
        "CONTEXT_PRIORITIES",
        "CONTEXT_DATES",
        "AREA_LIST",
    }


def test_fixed_texts_are_exactly_as_agreed():
    assert PART5_BODIES["light"] == LIGHT_PART5
    assert PART5_BODIES["strict"] == STRICT_PART5
    assert tuple(p for _, _, p in CONTEXT_FIELDS) == PLACEHOLDERS


# --- leaks -------------------------------------------------------------------------


def test_strict_payload_and_prompt_contain_no_stored_text(fixture_db):
    payload = payload_of(fixture_db, "strict")
    result = build_prompt(payload)
    payload_text = fold(json.dumps(payload, ensure_ascii=False))
    prompt_text = fold(result.text)
    # Words the template itself uses (e.g. the tag "errand" in Part 7) are not
    # leaks; everything else must be absent from both files.
    template_text = fold(re.sub(r"\{\{[A-Z0-9_]+\}\}", "", load_template()))
    strings = [fold(s).strip() for s in stored_strings(fixture_db)]
    assert len(strings) > 80
    assert [s for s in strings if s and s in payload_text] == []
    assert [
        s for s in strings if s and s in prompt_text and s not in template_text
    ] == []


def test_light_payload_and_prompt_contain_no_raw_pii(fixture_db):
    payload = payload_of(fixture_db, "light")
    combined = json.dumps(payload, ensure_ascii=False) + build_prompt(payload).text
    for value in FAKE_PII:
        assert value not in combined, value
    assert "<url>" in combined and "<amount>" in combined


def test_part5_by_level(fixture_db):
    light = build_prompt(payload_of(fixture_db, "light")).text
    strict = build_prompt(payload_of(fixture_db, "strict")).text
    assert "## Part 5: Task quality audit\n\n" + LIGHT_PART5 + "\n\n## Part 6" in light
    assert STRICT_PART5 not in light
    assert (
        "## Part 5: Task quality audit\n\n" + STRICT_PART5 + "\n\n## Part 6" in strict
    )
    assert "ACTION VERB" not in strict


def test_data_note_by_level(fixture_db):
    strict = build_prompt(payload_of(fixture_db, "strict")).text
    light = build_prompt(payload_of(fixture_db, "light")).text
    assert '"Task k3f7az"' in strict and "checklist_count" in strict
    assert "<email>" in light and "Notes are removed." in light


# --- token filling ---------------------------------------------------------------


def test_no_tokens_remain_and_area_list_matches(fixture_db):
    for level in ("light", "strict"):
        payload = payload_of(fixture_db, level)
        result = build_prompt(payload)
        assert "{{" not in result.text
        expected = ", ".join(area["title"] for area in payload["areas"])
        assert result.area_list == expected
        assert f"My Areas: {expected}\n" in result.text
    strict_areas = build_prompt(payload_of(fixture_db, "strict")).area_list
    assert re.fullmatch(r"Area [a-z2-7]{6}, Area [a-z2-7]{6}", strict_areas)
    assert build_prompt(payload_of(fixture_db, "light")).area_list == (
        "Household, Side Studio"
    )


def test_empty_area_list(fixture_db):
    payload = payload_of(fixture_db, "strict")
    payload["areas"] = []
    assert "My Areas: (no areas)\n" in build_prompt(payload).text


def test_unfilled_placeholders_are_visible_and_reported(fixture_db):
    result = build_prompt(payload_of(fixture_db, "strict"))
    assert result.unfilled == PLACEHOLDERS
    assert "- Who I am and what I do: [ROLE AND SITUATION]\n" in result.text
    assert (
        "- Major ongoing responsibilities and priorities: "
        "[MAJOR RESPONSIBILITIES AND PRIORITIES]\n" in result.text
    )
    assert (
        "- Key dates or transitions that shape the next 6-12 months: "
        "[KEY DATES AND TRANSITIONS]\n" in result.text
    )


def test_context_is_filled_verbatim(fixture_db):
    context = parse_context(CONTEXT)
    assert context == Context(
        role="Freelance designer\nworking from home.",
        priorities="- Ship the studio site\n- Keep Sundays free",
        dates="Move house in March 2027.",
    )
    result = build_prompt(payload_of(fixture_db, "strict"), context)
    assert result.unfilled == ()
    assert "Who I am and what I do: Freelance designer\nworking from home.\n" in (
        result.text
    )
    assert "- Ship the studio site\n- Keep Sundays free" in result.text


def test_context_braces_are_not_treated_as_tokens(fixture_db):
    context = Context(role="I write {{AREA_LIST}} literally")
    result = build_prompt(payload_of(fixture_db, "strict"), context)
    assert "I write {{AREA_LIST}} literally" in result.text


def test_none_payload_is_refused(fixture_db):
    payload = {**payload_of(fixture_db, "strict"), "anonymisation": "none"}
    with pytest.raises(ValueError, match="anonymised"):
        build_prompt(payload)


def test_unknown_template_token_is_an_error(fixture_db):
    with pytest.raises(ValueError, match="NEW_TOKEN"):
        build_prompt(payload_of(fixture_db, "strict"), template="{{NEW_TOKEN}}")


# --- context parsing ----------------------------------------------------------------


def test_one_section_missing():
    context = parse_context("role: Teacher\nDATES: June\n")
    assert context == Context(role="Teacher", priorities=None, dates="June")


def test_empty_value_counts_as_unfilled(fixture_db):
    context = parse_context("Role:\n\nPriorities: Family\n")
    assert context.role is None
    result = build_prompt(payload_of(fixture_db, "strict"), context)
    assert result.unfilled == ("[ROLE AND SITUATION]", "[KEY DATES AND TRANSITIONS]")


def test_indented_colon_is_text():
    context = parse_context("Dates:\n  Note: exams in May\n")
    assert context.dates == "  Note: exams in May"


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("", "empty"),
        ("   \n\n", "empty"),
        ("Hello\nRole: x\n", "before the first label"),
        ("Role: x\nGoals: y\n", "unknown label 'Goals'"),
        ("Role: x\nrole: y\n", "appears twice"),
    ],
)
def test_context_errors(text, message):
    with pytest.raises(ContextError, match=message):
        parse_context(text)


# --- CLI ----------------------------------------------------------------------


@pytest.fixture(autouse=True)
def no_real_app(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "THINGS_INFO_PLIST", tmp_path / "missing.plist")


@pytest.fixture
def pbcopy(monkeypatch):
    calls = []

    def fake_run(args, **kwargs):
        if args == ["pbcopy"]:
            calls.append((args, kwargs))
        return subprocess.CompletedProcess(args, 0, stdout="")

    monkeypatch.setattr(cli.subprocess, "run", fake_run)
    return calls


def run(fixture_db, *args):
    return cli.main(["--db", str(fixture_db), "prompt", *args])


def test_preview_without_out_or_copy_writes_nothing(fixture_db, tmp_path, capsys):
    before = set(tmp_path.iterdir())
    assert run(fixture_db) == 0
    out = capsys.readouterr().out
    assert "Anonymisation: strict" in out
    assert (
        "Payload counts: 2 areas, 6 projects, 2 headings, 30 to-do rows (29 open, "
        "1 inside trashed projects), 2 tags, 25 recurring templates, 17 findings" in out
    )
    assert (
        "Left out (counted in the summary only):\n"
        "  - completed, cancelled and trashed to-dos\n"
        "  - completed and trashed projects, unless they still hold open to-dos\n"
    ) in out
    assert "notes removed" in out
    assert "warning: these placeholders stay visible" in out
    assert "Nothing was written." in out
    assert out.rstrip().endswith(
        "Nothing has been sent anywhere. You attach or paste these yourself."
    )
    assert set(tmp_path.iterdir()) == before
    assert "Things 3 System Audit" not in out  # the preview, not the prompt


def test_out_writes_private_files(fixture_db, tmp_path, capsys):
    target = tmp_path / "new" / "dir"
    old = os.umask(0)
    try:
        assert run(fixture_db, "--out", str(target)) == 0
    finally:
        os.umask(old)
    assert stat.S_IMODE(target.stat().st_mode) == 0o700
    payload = target / "tidyline_payload.json"
    prompt_file = target / "tidyline_prompt.md"
    for path in (payload, prompt_file):
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    data = json.loads(payload.read_text(encoding="utf-8"))
    assert data["anonymisation"] == "strict"
    assert prompt_file.read_text(encoding="utf-8").startswith("# Things 3 System Audit")
    out = capsys.readouterr().out
    assert f"{payload}  ({payload.stat().st_size} bytes)" in out
    assert "Nothing was written." not in out


def test_existing_files_are_refused_before_reading(
    fixture_db, tmp_path, capsys, monkeypatch
):
    (tmp_path / "tidyline_prompt.md").write_text("keep", encoding="utf-8")

    def never(args):
        raise AssertionError("the database must not be read")

    monkeypatch.setattr(cli, "_load", never)
    assert run(fixture_db, "--out", str(tmp_path)) == 2
    assert (tmp_path / "tidyline_prompt.md").read_text(encoding="utf-8") == "keep"
    assert not (tmp_path / "tidyline_payload.json").exists()
    assert "already in" in capsys.readouterr().err


def test_out_that_is_a_file_is_refused(fixture_db, tmp_path, capsys):
    target = tmp_path / "file.txt"
    target.write_text("x", encoding="utf-8")
    assert run(fixture_db, "--out", str(target)) == 2
    assert "not a folder" in capsys.readouterr().err


def test_copy_sends_the_prompt_to_pbcopy(fixture_db, capsys, pbcopy):
    assert run(fixture_db, "--copy", "--anonymise", "light") == 0
    ((args, kwargs),) = pbcopy
    assert args == ["pbcopy"]
    text = kwargs["input"].decode("utf-8")
    assert text.startswith("# Things 3 System Audit")
    assert LIGHT_PART5 in text
    out = capsys.readouterr().out
    assert "Copied the prompt text to the clipboard." in out
    assert "Use --out DIR to get the payload file" in out


def test_copy_and_out_together(fixture_db, tmp_path, pbcopy):
    assert run(fixture_db, "--copy", "--out", str(tmp_path)) == 0
    assert len(pbcopy) == 1
    copied = pbcopy[0][1]["input"].decode("utf-8")
    assert copied + "\n" == (tmp_path / "tidyline_prompt.md").read_text("utf-8")


@pytest.mark.parametrize(
    "failure",
    [FileNotFoundError(2, "No such file", "pbcopy"),
     subprocess.CalledProcessError(1, ["pbcopy"])],
)  # fmt: skip
def test_copy_failure_exits_3(fixture_db, capsys, monkeypatch, failure):
    def fail(args, **kwargs):
        if args == ["pbcopy"]:
            raise failure
        return subprocess.CompletedProcess(args, 0, stdout="")

    monkeypatch.setattr(cli.subprocess, "run", fail)
    assert run(fixture_db, "--copy") == 3
    captured = capsys.readouterr()
    assert "could not copy to the clipboard" in captured.err
    assert "Nothing has been sent anywhere" in captured.out  # preview still shown


def test_context_file_in_the_preview(fixture_db, tmp_path, capsys):
    context = tmp_path / "context.txt"
    context.write_text(CONTEXT, encoding="utf-8")
    assert run(fixture_db, "--context", str(context), "--out", str(tmp_path / "o")) == 0
    out = capsys.readouterr().out
    assert "Role: Freelance designer\nworking from home." in out
    assert "warning: these placeholders" not in out
    text = (tmp_path / "o" / "tidyline_prompt.md").read_text(encoding="utf-8")
    assert "Freelance designer\nworking from home." in text


def test_partial_context_warns(fixture_db, tmp_path, capsys):
    context = tmp_path / "context.txt"
    context.write_text("Role: Teacher\n", encoding="utf-8")
    assert run(fixture_db, "--context", str(context)) == 0
    out = capsys.readouterr().out
    assert "Role: Teacher" in out
    assert (
        "fill them with --context: [MAJOR RESPONSIBILITIES AND PRIORITIES], "
        "[KEY DATES AND TRANSITIONS]" in out
    )


@pytest.mark.parametrize("content", ["", "Goals: x\n", "intro\nRole: x\n"])
def test_bad_context_exits_2(fixture_db, tmp_path, capsys, content):
    context = tmp_path / "context.txt"
    context.write_text(content, encoding="utf-8")
    assert run(fixture_db, "--context", str(context)) == 2
    assert "error: --context" in capsys.readouterr().err


def test_missing_context_file_exits_2(fixture_db, tmp_path, capsys):
    assert run(fixture_db, "--context", str(tmp_path / "none.txt")) == 2
    assert "could not read --context" in capsys.readouterr().err


def test_anonymise_none_is_rejected(fixture_db, capsys):
    with pytest.raises(SystemExit) as error:
        run(fixture_db, "--anonymise", "none")
    assert error.value.code == 2
    assert "invalid choice" in capsys.readouterr().err


def test_db_after_the_command(fixture_db, capsys):
    assert cli.main(["prompt", "--db", str(fixture_db)]) == 0


def test_missing_database_exits_3(tmp_path, capsys):
    assert cli.main(["--db", str(tmp_path / "none.sqlite"), "prompt"]) == 3


def test_report_text_is_never_included(fixture_db, tmp_path):
    assert run(fixture_db, "--out", str(tmp_path), "--anonymise", "light") == 0
    combined = (tmp_path / "tidyline_payload.json").read_text("utf-8") + (
        tmp_path / "tidyline_prompt.md"
    ).read_text("utf-8")
    assert "tidyline report" not in combined
    assert "Recurring templates\n---" not in combined


def test_help_lists_prompt(capsys):
    with pytest.raises(SystemExit):
        cli.main(["--help"])
    assert "prompt" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        cli.main(["prompt", "--help"])
    out = capsys.readouterr().out
    for option in ("--anonymise", "--context", "--out", "--copy", "--db"):
        assert option in out


def test_prompt_module_has_no_network_or_print():
    source = open(prompt_module.__file__, encoding="utf-8").read()
    imports = re.findall(r"^\s*(?:import|from)\s+([\w.]+)", source, re.M)
    forbidden = {"socket", "urllib", "http", "requests", "subprocess", "ssl"}
    assert [m for m in imports if m.split(".")[0] in forbidden] == []
    assert not re.search(r"\bprint\(", source)


def test_payload_file_is_compact_json(fixture_db, tmp_path):
    assert run(fixture_db, "--out", str(tmp_path / "p"), "--anonymise", "light") == 0
    text = (tmp_path / "p" / "tidyline_payload.json").read_text("utf-8")
    body = text.removesuffix("\n")
    assert "\n" not in body and "\t" not in body
    assert body.startswith('{"payload_schema_version":"1","anonymisation":"light",')
    data = json.loads(text)
    assert body == json.dumps(data, separators=(",", ":"), ensure_ascii=False)
    assert "pimentón" in body  # non-ASCII kept, not escaped


def test_preview_counts_name_to_do_rows(fixture_db, capsys):
    payload = payload_of(fixture_db, "strict")
    summary = payload["summary"]
    rows = f"{len(payload['tasks'])} to-do rows ({summary['open_todos']} open, "
    rows += f"{summary['open_in_trashed_project']} inside trashed projects)"
    assert rows in build_prompt(payload).counts
    assert run(fixture_db) == 0
    out = capsys.readouterr().out
    assert rows in out
    assert "open to-dos," not in out
