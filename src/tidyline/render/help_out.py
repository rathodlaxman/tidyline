"""The friendly screen shown by `tidyline` with no arguments. Returns a string;
never prints. `tidyline --help` is argparse's own output and is not touched."""

from __future__ import annotations

from tidyline.render.style import PLAIN, Style

GUIDE_URL = "https://github.com/rathodlaxman/tidyline/blob/main/docs/GETTING_STARTED.md"

COMMANDS = (
    ("doctor", "Check that tidyline can find and read your Things data."),
    ("report", "Show counts of your to-dos, with no titles."),
    ("check", "Find untidy things, such as to-dos with no project."),
    ("recurrence", "List your repeating to-dos in plain English."),
    ("export", "Save all your data to a file."),
    ("prompt", "Prepare files to ask an AI assistant to review your system."),
    ("decode", "Put your real titles back into an assistant's answer."),
)

EXAMPLES = (
    ("tidyline doctor", "check that everything works"),
    ("tidyline report", "see counts of your open work"),
    ("tidyline check", "list what could be tidier"),
    ("tidyline export --out ~/tidyline-out/things.json", "save a copy of your data"),
    ("tidyline prompt --out ~/tidyline-out", "make files for an AI review"),
)


def render_help(version: str, style: Style = PLAIN) -> str:
    """The help screen as text, at most 80 characters wide."""

    width = max(len(name) for name, _ in COMMANDS) + 2
    lines = [f"tidyline {version}", ""]
    lines.append("Check your Things 3 setup for problems. Unofficial, read-only.")
    lines += ["", "Commands"]
    lines += [f"  {name:<{width}}{what}" for name, what in COMMANDS]
    lines += ["", "Examples"]
    example_width = max(len(command) for command, _ in EXAMPLES) + 2
    for command, note in EXAMPLES:
        if 2 + example_width + len(note) <= 80:
            lines.append(f"  {command:<{example_width}}{note}")
        else:
            lines += [f"  {command}", f"      {note}"]
    lines += [
        "",
        "Your task titles",
        "  Show them on screen or in the file: check, recurrence, export, decode.",
        "  Never show them: report, check --json.",
        "  export and prompt hide them with --anonymise strict.",
        "  Nothing is sent anywhere.",
        "",
        style.bold("New here? Run tidyline doctor, then tidyline report."),
        style.bold("Step-by-step guide:"),
        f"  {GUIDE_URL}",
        "More detail on any command: tidyline COMMAND --help, or tidyline --help.",
    ]
    return "\n".join(lines) + "\n"
