from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import platform
import plistlib
import subprocess
import sys
from pathlib import Path

from tidyline import __version__
from tidyline.db.locate import DatabaseNotFoundError, locate_database
from tidyline.db.schema import (
    SchemaError,
    check_schema,
    is_tested,
    tested_versions_text,
)
from tidyline.db.snapshot import SnapshotError, open_snapshot
from tidyline.read import ReadError, read_snapshot
from tidyline.render.json_out import build_export

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
        choices=("none", "light", "strict"),
        default="none",
        help="anonymisation level; only none is available in v0.1",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "doctor":
        return doctor(args)
    if args.command == "export":
        return export(args)
    parser.print_help()
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
        return 1
    except PermissionError as error:
        show("Database:", "cannot look (permission denied)")
        print(f"error: {_permission_help(error)}", file=sys.stderr)
        return 1
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
        return 1
    except SchemaError as error:
        show("Schema:", "failed")
        print(f"error: {error}", file=sys.stderr)
        return 1

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
    if args.anonymise != "none":
        print(
            f"error: --anonymise {args.anonymise} arrives in v0.2. Nothing was "
            "exported. Use --anonymise none (the default) for a full export, and "
            "keep the file private.",
            file=sys.stderr,
        )
        return 2
    if args.out == "-":
        print(
            "error: writing to standard output (--out -) is not supported in v0.1. "
            "Give a file path, for example --out things-export.json.",
            file=sys.stderr,
        )
        return 2
    out = Path(args.out).expanduser()
    if out.exists() or out.is_symlink():
        print(
            f"error: {out} already exists, so nothing was written. Choose a new "
            "--out path, or move or delete the old file first.",
            file=sys.stderr,
        )
        return 1
    if not out.parent.is_dir():
        print(
            f"error: the folder {out.parent} does not exist. Create it, or choose "
            "another --out path.",
            file=sys.stderr,
        )
        return 1

    try:
        source = locate_database(args.db)
    except DatabaseNotFoundError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    except PermissionError as error:
        print(f"error: {_permission_help(error)}", file=sys.stderr)
        return 1

    macos = _macos_version()
    things = _things_version()
    try:
        with open_snapshot(source) as copy:
            report = check_schema(copy, macos_version=macos, things_version=things)
            snapshot = read_snapshot(copy)
    except SnapshotError as error:
        print(f"error: {error}", file=sys.stderr)
        if error.permission_problem:
            print(f"hint: {_permission_help(error)}", file=sys.stderr)
        if args.verbose and error.__cause__:
            print(f"cause: {error.__cause__!r}", file=sys.stderr)
        return 1
    except (SchemaError, ReadError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    data = build_export(
        snapshot,
        today=dt.date.today(),
        exported_at=dt.datetime.now(dt.timezone.utc).replace(microsecond=0),
        tool_version=__version__,
        environment={
            "macos": macos,
            "arch": platform.machine() or None,
            "things_version": things,
            "database_version": report.database_version,
        },
    )
    text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    try:
        _write_private(out, text)
    except FileExistsError:
        print(
            f"error: {out} appeared while exporting, so nothing was written. "
            "Choose a new --out path.",
            file=sys.stderr,
        )
        return 1
    except OSError as error:
        print(
            f"error: could not write {out}: {error.strerror or error}. Check the "
            "folder is writable, or choose another --out path.",
            file=sys.stderr,
        )
        return 1

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
    print(
        "note: this file contains your personal task data. Keep it private and "
        "do not commit or share it.",
        file=sys.stderr,
    )
    return 0


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
