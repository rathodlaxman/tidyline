from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import platform
import plistlib
import re
import subprocess
import sys
from pathlib import Path

from tidyline import __version__
from tidyline.anonymise import LEVELS, anonymise
from tidyline.checks import CHECK_IDS, CheckOptions, run_checks
from tidyline.db.locate import DatabaseNotFoundError, locate_database
from tidyline.db.schema import (
    SchemaError,
    check_schema,
    is_tested,
    tested_versions_text,
)
from tidyline.db.snapshot import SnapshotError, open_snapshot
from tidyline.decode import DecodeResult, decode_text, label_items, label_map
from tidyline.llm.payload import build_payload
from tidyline.llm.prompt import (
    KEPT,
    LEFT_OUT,
    PAYLOAD_FILE,
    PROMPT_FILE,
    ContextError,
    build_prompt,
    compact_json,
    parse_context,
)
from tidyline.read import ReadError, read_snapshot
from tidyline.render.check_out import check_json, check_text
from tidyline.render.help_out import render_help
from tidyline.render.json_out import build_export
from tidyline.render.recurrence_out import render_recurrence
from tidyline.render.text import ReportOptions, render_report

# Exit codes (DESIGN.md 7.3): 1 is reserved for `check` finding a warning.
EXIT_OK = 0
EXIT_WARNINGS = 1
EXIT_USAGE = 2
EXIT_FAILURE = 3  # the database could not be found or read; a write failed

THINGS_INFO_PLIST = Path("/Applications/Things3.app/Contents/Info.plist")

TERMINAL_APPS = {
    "Apple_Terminal": "Terminal",
    "iTerm.app": "iTerm",
    "vscode": "Visual Studio Code",
    "WarpTerminal": "Warp",
    "ghostty": "Ghostty",
    "WezTerm": "WezTerm",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tidyline",
        description="Offline, read-only audit of a Things 3 database (unofficial).",
    )
    parser.add_argument(
        "--version", action="version", version=f"tidyline {__version__}"
    )
    parser.add_argument("--db", metavar="PATH", help="path to the Things database")
    parser.add_argument(
        "--verbose", action="store_true", help="show extra detail when something fails"
    )
    commands = parser.add_subparsers(dest="command", metavar="COMMAND")
    doctor = commands.add_parser(
        "doctor", help="check the database location, permissions and versions"
    )
    doctor.add_argument(
        "--db",
        metavar="PATH",
        default=argparse.SUPPRESS,
        help="path to the Things database",
    )
    export = commands.add_parser("export", help="write the JSON export")
    export.add_argument(
        "--db",
        metavar="PATH",
        default=argparse.SUPPRESS,
        help="path to the Things database",
    )
    export.add_argument(
        "--out", metavar="PATH", required=True, help="file to write (must not exist)"
    )
    export.add_argument(
        "--anonymise",
        choices=LEVELS,
        default="none",
        help="none (default), light (scrub titles, drop notes) or strict "
        "(replace titles with labels)",
    )
    report = commands.add_parser("report", help="print or write the text report")
    report.add_argument(
        "--db",
        metavar="PATH",
        default=argparse.SUPPRESS,
        help="path to the Things database",
    )
    report.add_argument(
        "--html", action="store_true", help="HTML report (arrives in v0.3)"
    )
    report.add_argument(
        "--out", metavar="PATH", help="write to this file (must not exist)"
    )
    report.add_argument(
        "--include-completed",
        action="store_true",
        help="add a breakdown of completed, cancelled and trashed items",
    )
    report.add_argument(
        "--no-color", action="store_true", help="never use colour (plain text)"
    )
    check = commands.add_parser(
        "check", help="run the health checks; exit code 1 if any warning"
    )
    check.add_argument(
        "--db",
        metavar="PATH",
        default=argparse.SUPPRESS,
        help="path to the Things database",
    )
    check.add_argument(
        "--only",
        metavar="ID",
        nargs="+",
        action="extend",
        choices=CHECK_IDS,
        help=f"run only these checks: {', '.join(CHECK_IDS)}",
    )
    check.add_argument(
        "--pattern",
        metavar="REGEX",
        nargs="+",
        action="extend",
        default=[],
        help="flag titles matching these regular expressions (title_hygiene)",
    )
    check.add_argument(
        "--json", action="store_true", help="print findings as JSON, ids only"
    )
    prompt = commands.add_parser(
        "prompt",
        help="write an anonymised payload and a filled audit prompt for an LLM",
    )
    prompt.add_argument(
        "--db",
        metavar="PATH",
        default=argparse.SUPPRESS,
        help="path to the Things database",
    )
    prompt.add_argument(
        "--anonymise",
        choices=("light", "strict"),
        default="strict",
        help="strict (default): titles replaced by labels; light: titles kept "
        "but scrubbed",
    )
    prompt.add_argument(
        "--context",
        metavar="FILE",
        help="text file with Role:, Priorities: and Dates: sections",
    )
    prompt.add_argument(
        "--out",
        metavar="DIR",
        help=f"write {PAYLOAD_FILE} and {PROMPT_FILE} into this folder",
    )
    prompt.add_argument(
        "--copy", action="store_true", help="put the prompt on the clipboard (pbcopy)"
    )
    recurrence = commands.add_parser(
        "recurrence", help="list every repeating template with its readable rule"
    )
    recurrence.add_argument(
        "--db",
        metavar="PATH",
        default=argparse.SUPPRESS,
        help="path to the Things database",
    )
    recurrence.add_argument(
        "--raw",
        action="store_true",
        help="also show each rule as stored and the fields read from it",
    )
    decode = commands.add_parser(
        "decode",
        help="replace strict labels in an LLM answer with your real titles",
    )
    decode.add_argument("answer_file", metavar="ANSWER_FILE", help="the answer text")
    decode.add_argument(
        "--db",
        metavar="PATH",
        default=argparse.SUPPRESS,
        help="path to the Things database",
    )
    decode.add_argument(
        "--out", metavar="FILE", help="write the decoded text here (must not exist)"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the command. If the reader of standard output has gone (for example
    `tidyline check --json | head`), stop quietly with exit code 0.

    Files are written whole before anything is printed about them, and a failed
    write removes its own file, so a closed pipe never leaves a partial file."""
    try:
        code = _run(argv)
        sys.stdout.flush()  # buffered output fails here, not in print()
        return code
    except BrokenPipeError:
        # The recipe from the Python documentation: point stdout at devnull so
        # the flush at interpreter exit does not raise a second time.
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stdout.fileno())
        return EXIT_OK


def _run(argv: list[str] | None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "doctor":
        return doctor(args)
    if args.command == "export":
        return export(args)
    if args.command == "report":
        return report(args)
    if args.command == "check":
        return check(args)
    if args.command == "prompt":
        return prompt(args)
    if args.command == "decode":
        return decode(args)
    if args.command == "recurrence":
        return recurrence(args)
    color = not os.environ.get("NO_COLOR") and sys.stdout.isatty()
    print(render_help(__version__, color=color), end="")
    return 0


def doctor(args: argparse.Namespace) -> int:
    def show(label: str, value: str) -> None:
        print(f"{label:<18}{value}")

    print("tidyline doctor")
    try:
        source = locate_database(args.db)
    except DatabaseNotFoundError as error:
        show("Database:", "not found")
        print(f"error: {error}", file=sys.stderr)
        return EXIT_FAILURE
    except PermissionError as error:
        show("Database:", "cannot look (permission denied)")
        print(f"error: {_permission_help(error)}", file=sys.stderr)
        return EXIT_FAILURE
    show("Database:", _tilde(source))

    macos = _macos_version()
    things = _things_version()
    arch = platform.machine() or "unknown"

    try:
        with open_snapshot(source) as copy:
            show("Snapshot copy:", "ok")
            report = check_schema(copy, macos_version=macos, things_version=things)
    except SnapshotError as error:
        show("Snapshot copy:", "failed")
        print(f"error: {error}", file=sys.stderr)
        if error.permission_problem:
            print(f"hint: {_permission_help(error)}", file=sys.stderr)
        if args.verbose and error.__cause__:
            print(f"cause: {error.__cause__!r}", file=sys.stderr)
        return EXIT_FAILURE
    except SchemaError as error:
        show("Schema:", "failed")
        print(f"error: {error}", file=sys.stderr)
        return EXIT_FAILURE

    show("Schema:", "ok")
    show("Database version:", str(report.database_version))
    show("Things app:", things or "unknown")
    show("macOS:", macos or "unknown")
    show("Architecture:", arch)
    if is_tested(macos, things, report.database_version):
        show("Tested:", "yes")
    else:
        show("Tested:", f"no. {tested_versions_text()}")
        for warning in report.warnings:
            print(f"warning: {warning}", file=sys.stderr)
    return 0


def export(args: argparse.Namespace) -> int:
    if args.out == "-":
        print(
            "error: writing to standard output (--out -) is not supported. "
            "Give a file path, for example --out things-export.json.",
            file=sys.stderr,
        )
        return EXIT_USAGE
    out = _prepare_out(args.out)
    if out is None:
        return EXIT_USAGE
    loaded = _load(args)
    if loaded is None:
        return EXIT_FAILURE
    snapshot, report, macos, things = loaded

    now = _local_now()
    data = build_export(
        snapshot,
        today=now.date(),
        exported_at=now,
        tool_version=__version__,
        environment={
            "macos": macos,
            "arch": platform.machine() or None,
            "things_version": things,
            "database_version": report.database_version,
        },
    )
    data = anonymise(data, args.anonymise)
    text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    if not _write_out(out, text):
        return EXIT_FAILURE

    print(
        f"Exported {len(data['tasks'])} tasks, {len(data['projects'])} projects and "
        f"{len(data['recurring_templates'])} recurring templates to {out}"
    )
    if snapshot.warnings:
        print(
            f"warning: {len(snapshot.warnings)} values could not be read; "
            'see "warnings" in the file.',
            file=sys.stderr,
        )
    if args.anonymise == "strict":
        print(
            "note: titles and notes are replaced, but structure and dates still "
            "reveal how you work. Share it with care.",
            file=sys.stderr,
        )
    else:
        print(
            "note: this file contains your personal task data. Keep it private "
            "and do not commit or share it.",
            file=sys.stderr,
        )
    return 0


def report(args: argparse.Namespace) -> int:
    if args.html:
        print(
            "error: the HTML report arrives in v0.3. Nothing was written. Run "
            "`tidyline report` for the text report.",
            file=sys.stderr,
        )
        return EXIT_USAGE
    out = None
    if args.out is not None:
        if args.out == "-":
            print(
                "error: --out - is not supported. Leave out --out to print the "
                "report in the terminal, or give a file path.",
                file=sys.stderr,
            )
            return EXIT_USAGE
        out = _prepare_out(args.out)
        if out is None:
            return EXIT_USAGE
    loaded = _load(args)
    if loaded is None:
        return EXIT_FAILURE
    snapshot, schema_report, macos, things = loaded

    color = (
        out is None
        and not args.no_color
        and not os.environ.get("NO_COLOR")
        and sys.stdout.isatty()
    )
    text = render_report(
        snapshot,
        today=dt.date.today(),
        tool_version=__version__,
        environment={
            "macos": macos,
            "things_version": things,
            "database_version": schema_report.database_version,
            "tested": is_tested(macos, things, schema_report.database_version),
        },
        options=ReportOptions(include_completed=args.include_completed, color=color),
    )
    if out is None:
        print(text, end="")
        return 0
    if not _write_out(out, text):
        return EXIT_FAILURE
    print(f"Wrote the report to {out}")
    print(
        "note: this file contains the titles of your recurring tasks. Keep it "
        "private and do not commit or share it.",
        file=sys.stderr,
    )
    return 0


def check(args: argparse.Namespace) -> int:
    patterns = []
    for number, text in enumerate(args.pattern, start=1):
        try:
            patterns.append(re.compile(text))
        except re.error as error:
            print(
                f"error: --pattern {number} is not a valid regular expression "
                f"({error}). Fix it, or quote it so the shell leaves it alone.",
                file=sys.stderr,
            )
            return EXIT_USAGE
    loaded = _load(args)
    if loaded is None:
        return EXIT_FAILURE
    snapshot = loaded[0]
    checks = [c for c in CHECK_IDS if args.only is None or c in args.only]
    findings = run_checks(
        snapshot,
        dt.date.today(),
        only=checks,
        options=CheckOptions(patterns=tuple(patterns)),
    )
    if args.json:
        print(json.dumps(check_json(findings, checks), indent=2, ensure_ascii=False))
    else:
        print(check_text(findings, checks, snapshot, args.pattern), end="")
    if any(f.severity == "warning" for f in findings):
        return EXIT_WARNINGS
    return EXIT_OK


def prompt(args: argparse.Namespace) -> int:
    context = None
    if args.context is not None:
        try:
            context = parse_context(
                Path(args.context).expanduser().read_text(encoding="utf-8")
            )
        except ContextError as error:
            print(f"error: --context {args.context}: {error}", file=sys.stderr)
            return EXIT_USAGE
        except (OSError, UnicodeDecodeError) as error:
            print(
                f"error: could not read --context {args.context} ({error}). Give "
                "a UTF-8 text file.",
                file=sys.stderr,
            )
            return EXIT_USAGE

    out_dir = None
    if args.out is not None:
        out_dir = Path(args.out).expanduser()
        if out_dir.exists() and not out_dir.is_dir():
            print(
                f"error: {out_dir} exists and is not a folder. Choose a folder for "
                "--out.",
                file=sys.stderr,
            )
            return EXIT_USAGE
        taken = [n for n in (PAYLOAD_FILE, PROMPT_FILE) if (out_dir / n).exists()]
        if taken:
            print(
                f"error: {', '.join(taken)} already in {out_dir}, so nothing was "
                "written. Choose another --out folder, or move the old files.",
                file=sys.stderr,
            )
            return EXIT_USAGE

    loaded = _load(args)
    if loaded is None:
        return EXIT_FAILURE
    snapshot = loaded[0]
    now = _local_now()
    payload = build_payload(
        snapshot,
        today=now.date(),
        exported_at=now,
        level=args.anonymise,
    )
    result = build_prompt(payload, context)

    written: list[tuple[Path, int]] = []
    code = EXIT_OK
    problem = None
    if out_dir is not None:
        files = (
            (out_dir / PAYLOAD_FILE, compact_json(payload)),
            (out_dir / PROMPT_FILE, result.text),
        )
        try:
            if not out_dir.exists():
                out_dir.mkdir(parents=True, mode=0o700)
                os.chmod(out_dir, 0o700)  # exact mode whatever the umask
            for path, text in files:
                _write_private(path, text + "\n")
                written.append((path, path.stat().st_size))
        except OSError as error:
            for path, _ in written:
                path.unlink(missing_ok=True)
            written = []
            code = EXIT_FAILURE
            problem = (
                f"could not write into {out_dir}: {error.strerror or error}. Nothing "
                "was kept. Check the folder is writable, or choose another --out."
            )
    copied = False
    if args.copy and code == EXIT_OK:
        try:
            subprocess.run(
                ["pbcopy"],
                input=result.text.encode("utf-8"),
                check=True,
                timeout=10,
            )
            copied = True
        except (OSError, subprocess.SubprocessError) as error:
            code = EXIT_FAILURE
            problem = (
                f"could not copy to the clipboard with pbcopy ({error}). Use --out "
                "DIR to save the prompt to a file instead."
            )

    print(_prompt_preview(result, args, context, written, copied))
    if problem:
        print(f"error: {problem}", file=sys.stderr)
    return code


def recurrence(args: argparse.Namespace) -> int:
    loaded = _load(args)
    if loaded is None:
        return EXIT_FAILURE
    print(render_recurrence(loaded[0], raw=args.raw), end="")
    return EXIT_OK


MAX_ANSWER_BYTES = 5 * 1024 * 1024


def decode(args: argparse.Namespace) -> int:
    answer = Path(args.answer_file).expanduser()
    try:
        size = answer.stat().st_size
        if not answer.is_file():
            raise IsADirectoryError(f"{answer} is not a file")
        if size > MAX_ANSWER_BYTES:
            print(
                f"error: {answer} is {size} bytes; decode reads at most 5 MB. "
                "Save only the answer text in the file.",
                file=sys.stderr,
            )
            return EXIT_USAGE
        text = answer.read_bytes().decode("utf-8")
    except UnicodeDecodeError:
        print(
            f"error: {answer} is not valid UTF-8 text. Save the answer as plain "
            "UTF-8 text and try again.",
            file=sys.stderr,
        )
        return EXIT_USAGE
    except OSError as error:
        print(
            f"error: could not read {answer} ({error.strerror or error}). Check the "
            "path, or save the answer to a text file first.",
            file=sys.stderr,
        )
        return EXIT_USAGE

    out = None
    if args.out is not None:
        out = _prepare_out(args.out)
        if out is None:
            return EXIT_USAGE

    if not text.strip():
        decoded, summary = text, "The answer file is empty; nothing was replaced."
    else:
        loaded = _load(args)
        if loaded is None:
            return EXIT_FAILURE
        snapshot = loaded[0]
        result = decode_text(text, label_map(snapshot), label_items(snapshot))
        decoded = result.text
        summary = _decode_summary(result)

    if out is None:
        print(decoded, end="")
    else:
        if not _write_out(out, decoded):
            return EXIT_FAILURE
        print(f"Wrote the decoded answer to {out}")
    print(summary, file=sys.stderr)
    print(
        "warning: the decoded text contains real titles from your Things database. "
        "It is personal data; keep it private.",
        file=sys.stderr,
    )
    return EXIT_OK


def _decode_summary(result: DecodeResult) -> str:
    """Counts only, never titles or codes."""
    lines = [
        f"Decoded: {result.replaced} labels replaced, {result.bare_replaced} bare "
        f"codes replaced ({result.distinct} distinct items)."
    ]
    if result.ambiguous:
        lines.append(
            f"{len(result.ambiguous)} distinct bare codes were ambiguous (each "
            "matches several items) and were left as they are."
        )
    if result.unmatched:
        lines.append(
            f"{len(result.unmatched)} distinct label-like strings matched nothing "
            "in this database and were left as they are."
        )
    return "\n".join(lines)


def _local_now() -> dt.datetime:
    """Now in local time with its UTC offset. `exported_at` and every date
    derived from it (created, modified, completed windows) use this."""
    return dt.datetime.now().astimezone().replace(microsecond=0)


def _prompt_preview(result, args, context, written, copied) -> str:
    lines = ["tidyline prompt: preview", ""]
    lines.append(f"Anonymisation: {result.level}")
    lines.append(f"Payload counts: {', '.join(result.counts)}")
    lines.append("Removed or replaced at this level:")
    lines += [f"  - {item}" for item in result.removed]
    lines.append(f"Kept: {KEPT}")
    lines.append("Left out (counted in the summary only):")
    lines += [f"  - {item}" for item in LEFT_OUT]
    lines.append("")
    if context is not None:
        lines.append(f"Context from {args.context} (sent exactly as written):")
        for label, value in (
            ("Role", context.role),
            ("Priorities", context.priorities),
            ("Dates", context.dates),
        ):
            if value:
                lines.append(f"{label}: {value}")
    if result.unfilled:
        lines.append(
            "warning: these placeholders stay visible in the prompt; fill them "
            f"with --context: {', '.join(result.unfilled)}"
        )
    lines.append("")
    if written:
        lines.append("Written:")
        lines += [f"  {path}  ({size} bytes)" for path, size in written]
    if copied:
        lines.append("Copied the prompt text to the clipboard.")
        if not written:
            lines.append(
                "The clipboard holds the prompt only. Use --out DIR to get the "
                "payload file the prompt refers to."
            )
    if not written and not copied:
        lines.append(
            "Nothing was written. Use --out DIR to save the payload and prompt, "
            "or --copy to put the prompt on the clipboard."
        )
    lines.append("Nothing has been sent anywhere. You attach or paste these yourself.")
    return "\n".join(lines)


def _prepare_out(argument: str) -> Path | None:
    """Check an --out path before any work is done; print why if it is unusable."""
    out = Path(argument).expanduser()
    if out.exists() or out.is_symlink():
        print(
            f"error: {out} already exists, so nothing was written. Choose a new "
            "--out path, or move or delete the old file first.",
            file=sys.stderr,
        )
        return None
    if not out.parent.is_dir():
        print(
            f"error: the folder {out.parent} does not exist. Create it, or choose "
            "another --out path.",
            file=sys.stderr,
        )
        return None
    return out


def _load(args: argparse.Namespace):
    """Locate, snapshot and read the database. Print the problem and return None."""
    try:
        source = locate_database(args.db)
    except DatabaseNotFoundError as error:
        print(f"error: {error}", file=sys.stderr)
        return None
    except PermissionError as error:
        print(f"error: {_permission_help(error)}", file=sys.stderr)
        return None

    macos = _macos_version()
    things = _things_version()
    try:
        with open_snapshot(source) as copy:
            schema_report = check_schema(
                copy, macos_version=macos, things_version=things
            )
            snapshot = read_snapshot(copy)
    except SnapshotError as error:
        print(f"error: {error}", file=sys.stderr)
        if error.permission_problem:
            print(f"hint: {_permission_help(error)}", file=sys.stderr)
        if args.verbose and error.__cause__:
            print(f"cause: {error.__cause__!r}", file=sys.stderr)
        return None
    except (SchemaError, ReadError) as error:
        print(f"error: {error}", file=sys.stderr)
        return None
    return snapshot, schema_report, macos, things


def _write_out(out: Path, text: str) -> bool:
    try:
        _write_private(out, text)
    except FileExistsError:
        print(
            f"error: {out} appeared while writing, so nothing was written. "
            "Choose a new --out path.",
            file=sys.stderr,
        )
        return False
    except OSError as error:
        print(
            f"error: could not write {out}: {error.strerror or error}. Check the "
            "folder is writable, or choose another --out path.",
            file=sys.stderr,
        )
        return False
    return True


def _write_private(path: Path, text: str) -> None:
    """Create `path` with mode 0600; never overwrite. Remove it if writing fails."""
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            os.fchmod(handle.fileno(), 0o600)  # exact mode whatever the umask
            handle.write(text)
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def _tilde(path: Path) -> str:
    home = Path.home()
    try:
        return f"~/{path.relative_to(home)}"
    except ValueError:
        return str(path)


def _permission_help(error: Exception) -> str:
    app = TERMINAL_APPS.get(os.environ.get("TERM_PROGRAM", ""))
    which = (
        f"the app you ran tidyline from ({app})"
        if app
        else "the terminal app you ran tidyline from (Terminal, iTerm, VS Code, ...)"
    )
    return (
        f"{error}. macOS may be blocking access to Things' data. Open System "
        f"Settings > Privacy & Security > Full Disk Access, turn it on for "
        f"{which}, then quit and reopen that app and try again."
    )


def _macos_version() -> str | None:
    try:
        result = subprocess.run(
            ["sw_vers", "-productVersion"],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() or None


def _things_version() -> str | None:
    try:
        with open(THINGS_INFO_PLIST, "rb") as handle:
            return plistlib.load(handle).get("CFBundleShortVersionString")
    except Exception:  # missing app, unreadable or malformed plist: just unknown
        return None
