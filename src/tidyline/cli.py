from __future__ import annotations

import argparse
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
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "doctor":
        return doctor(args)
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
