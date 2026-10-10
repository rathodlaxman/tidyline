"""Fill the packaged audit template for `tidyline prompt` (DESIGN.md 8, 3).

Offline and pure: the only I/O is reading the packaged template through
importlib.resources. Nothing here prints, reads the clock or opens a socket.
The payload must already be anonymised (`light` or `strict`); the text report
is never part of the output.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from importlib import resources
from typing import Any

TEMPLATE_NAME = "audit_prompt.md"
LEVELS = ("light", "strict")
PAYLOAD_FILE = "tidyline_payload.json"
PROMPT_FILE = "tidyline_prompt.md"

DATA_NOTES = {
    "strict": (
        'Titles and names in this file are replaced by labels such as "Task '
        'k3f9az", "Project 7qm2xd" or "Area x3k2qa". Notes are removed, and '
        "checklist items are replaced by a count (`checklist_count`). Refer to "
        "items by their label."
    ),
    "light": (
        "Titles and names are kept, but emails, phone numbers, URLs, money "
        "amounts and long numbers are replaced by placeholders such as `<email>`, "
        "`<phone>`, `<url>`, `<amount>` and `<number>`. Notes are removed."
    ),
}

PART5_BODIES = {
    "light": (
        "Review task titles. For tasks that are genuinely vague or non-actionable, "
        "rewrite them as:\n"
        "\n"
        "**ACTION VERB + SPECIFIC OBJECT + CLEAR OUTCOME**\n"
        "\n"
        "Examples:\n"
        "\n"
        '- Vague: "Work on CV". Better: "Rewrite professional summary in 2-page '
        'CV"\n'
        '- Vague: "Study Python". Better: "Complete Pandas filtering exercise"\n'
        '- Vague: "Research certifications". Better: "Compare 3 certification '
        'options on fees, duration and eligibility"\n'
        "\n"
        "Do not rewrite every task unnecessarily. Only rewrite where the wording "
        "is genuinely unclear."
    ),
    "strict": (
        "Titles are hidden in this data, so task wording cannot be judged. Skip "
        "this part and write one line saying so. Do not guess at task wording."
    ),
}

# Context fields: label in the --context file, token, text shown when unfilled.
CONTEXT_FIELDS = (
    ("role", "CONTEXT_ROLE", "[ROLE AND SITUATION]"),
    ("priorities", "CONTEXT_PRIORITIES", "[MAJOR RESPONSIBILITIES AND PRIORITIES]"),
    ("dates", "CONTEXT_DATES", "[KEY DATES AND TRANSITIONS]"),
)
NO_AREAS = "(no areas)"

REMOVED = {
    "strict": (
        'titles and names replaced by labels such as "Task k3f9az"',
        "notes removed",
        "checklist items replaced by a count",
        "free text in raw recurrence rules and read warnings replaced",
    ),
    "light": (
        "emails, phone numbers, URLs, money amounts and long numbers in titles "
        "and checklist items replaced by placeholders",
        "notes removed",
        "free text in raw recurrence rules and read warnings replaced",
    ),
}
KEPT = "ids, structure, dates, status fields, recurrence text and findings"

_TOKEN = re.compile(r"\{\{([A-Z0-9_]+)\}\}")
_LABEL = re.compile(r"^([A-Za-z]+)[ \t]*:(.*)$")


class ContextError(ValueError):
    """The --context file is not in the expected form."""


@dataclass(frozen=True)
class Context:
    role: str | None = None
    priorities: str | None = None
    dates: str | None = None


@dataclass(frozen=True)
class PromptResult:
    text: str
    level: str
    unfilled: tuple[
        str, ...
    ]  # placeholder texts left visible, e.g. "[ROLE AND SITUATION]"
    counts: dict[str, int] = field(default_factory=dict)
    removed: tuple[str, ...] = ()
    area_list: str = ""


def load_template() -> str:
    return resources.files("tidyline.llm").joinpath(TEMPLATE_NAME).read_text("utf-8")


def parse_context(text: str) -> Context:
    """Read "Role:", "Priorities:" and "Dates:" sections.

    A label starts a line (any case); its value runs until the next label.
    Blank lines at the start and end of a value are dropped; everything else
    is kept as written. Indent a line to keep a colon in it as plain text.
    """
    if not text.strip():
        raise ContextError(
            "the context file is empty. Add Role:, Priorities: and Dates: "
            "sections, or leave out --context."
        )
    known = {name for name, _, _ in CONTEXT_FIELDS}
    values: dict[str, list[str]] = {}
    current: str | None = None
    for number, line in enumerate(text.splitlines(), start=1):
        match = _LABEL.match(line)
        if match:
            label = match.group(1).casefold()
            if label not in known:
                raise ContextError(
                    f"line {number}: unknown label {match.group(1)!r}. Use Role:, "
                    "Priorities: or Dates:, or indent the line to keep it as text."
                )
            if label in values:
                raise ContextError(
                    f"line {number}: {match.group(1)}: appears twice. Give each "
                    "label once."
                )
            current = label
            values[label] = [match.group(2).lstrip(" \t")]
        elif current is None:
            if line.strip():
                raise ContextError(
                    f"line {number}: text before the first label. Start the file "
                    "with Role:, Priorities: or Dates:."
                )
        else:
            values[current].append(line)

    def tidy(lines: list[str]) -> str | None:
        while lines and not lines[0].strip():
            lines = lines[1:]
        while lines and not lines[-1].strip():
            lines = lines[:-1]
        return "\n".join(lines) if lines else None

    return Context(**{label: tidy(lines) for label, lines in values.items()})


def build_prompt(
    payload: dict[str, Any],
    context: Context | None = None,
    template: str | None = None,
) -> PromptResult:
    """Fill the template for an anonymised payload."""
    level = payload.get("anonymisation")
    if level not in LEVELS:
        raise ValueError(
            f"the payload must be anonymised as light or strict, not {level!r}"
        )
    template = load_template() if template is None else template
    context = context or Context()

    areas = [area["title"] or "" for area in payload["areas"]]
    area_list = ", ".join(areas) if areas else NO_AREAS
    values = {
        "DATA_NOTE": DATA_NOTES[level],
        "PART5_BODY": PART5_BODIES[level],
        "AREA_LIST": area_list,
    }
    unfilled = []
    for name, token, placeholder in CONTEXT_FIELDS:
        given = getattr(context, name)
        values[token] = given if given else placeholder
        if not given:
            unfilled.append(placeholder)

    unknown = sorted(set(_TOKEN.findall(template)) - set(values))
    if unknown:
        raise ValueError(f"the template has unknown tokens: {', '.join(unknown)}")
    # One pass, so text put in (context, area names) is never scanned again.
    text = _TOKEN.sub(lambda match: values[match.group(1)], template)
    assert "{{" not in _TOKEN.sub("", template), "template braces left unfilled"

    counts = {
        "areas": len(payload["areas"]),
        "projects": len(payload["projects"]),
        "headings": len(payload["headings"]),
        "tasks": len(payload["tasks"]),
        "recurring templates": len(payload["recurring_templates"]),
        "findings": len(payload["findings"]),
    }
    return PromptResult(
        text=text,
        level=level,
        unfilled=tuple(unfilled),
        counts=counts,
        removed=REMOVED[level],
        area_list=area_list,
    )
