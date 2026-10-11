"""A reader that closes early (`tidyline check --json | head`) ends the run
quietly with exit code 0 and no traceback."""

import subprocess
import sys

from tidyline import cli

RUN = "import sys; from tidyline.cli import main; sys.exit(main())"


def test_closed_pipe_in_a_real_process(fixture_db):
    process = subprocess.Popen(
        [sys.executable, "-c", RUN, "check", "--json", "--db", str(fixture_db)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    process.stdout.close()  # the reader has gone before anything is written
    stderr = process.stderr.read().decode()
    assert process.wait(timeout=60) == 0
    assert stderr == ""


def test_broken_pipe_while_printing_exits_0_and_redirects_stdout(monkeypatch):
    calls = []

    def run(argv):
        raise BrokenPipeError

    monkeypatch.setattr(cli, "_run", run)
    monkeypatch.setattr(cli.os, "dup2", lambda src, dst: calls.append((src, dst)))
    monkeypatch.setattr(cli.os, "open", lambda path, flags: 99)
    monkeypatch.setattr(cli.sys.stdout, "fileno", lambda: 1, raising=False)
    assert cli.main([]) == 0
    assert calls == [(99, 1)]


def test_broken_pipe_at_flush_is_also_quiet(monkeypatch):
    class Gone:
        def flush(self):
            raise BrokenPipeError

        def fileno(self):
            return 1

    calls = []
    monkeypatch.setattr(cli, "_run", lambda argv: 1)
    monkeypatch.setattr(cli.sys, "stdout", Gone())
    monkeypatch.setattr(cli.os, "dup2", lambda src, dst: calls.append((src, dst)))
    monkeypatch.setattr(cli.os, "open", lambda path, flags: 99)
    assert cli.main([]) == 0
    assert calls == [(99, 1)]


def test_a_closed_pipe_leaves_no_partial_file(fixture_db, tmp_path):
    """`report --out FILE` writes the file whole before it prints a line."""
    out = tmp_path / "report.txt"
    process = subprocess.Popen(
        [
            sys.executable,
            "-c",
            RUN,
            "report",
            "--out",
            str(out),
            "--db",
            str(fixture_db),
        ],  # fmt: skip
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    process.stdout.close()
    stderr = process.stderr.read().decode()
    assert process.wait(timeout=60) == 0
    assert "Traceback" not in stderr
    text = out.read_text(encoding="utf-8")
    assert "Health checks" in text or "checks" in text.lower()
    assert text.endswith("\n")
