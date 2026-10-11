"""Anonymise a JSON export (DESIGN.md 7.5). Pure functions: no I/O, no clock.

Levels:
- `none`: the export unchanged.
- `light`: titles and names are kept but scrubbed: URLs, emails, money amounts,
  phone numbers and runs of 8 or more digits become `<url>`, `<email>`,
  `<amount>`, `<phone>` and `<number>`. Dates such as 2026-10-10 survive.
  Notes are removed (null). Checklist item titles are scrubbed the same way.
- `strict`: every title and name becomes a label derived from the item's id
  alone (`Task k3f7az`, `Project 7qm2xd`, `Area x3k2qa`, ...), so a label never
  changes when other items are added, removed or reordered. Notes are removed
  (null) and checklists are replaced by their count (`checklist` null,
  `checklist_count` kept).

At light and strict, free text that could hide in technical fields is removed
too: string values inside a raw recurrence rule become `<text>`, quoted values
in recurrence notes become `<text>`, the hex prefix of an unreadable rule is
dropped (its length is kept), and non-number values quoted in read warnings
become `<value>`. At strict, the raw rule's timestamps `ed`, `ia` and `sr` are
withheld (null); light keeps them. Ids, structure, dates, status fields,
recurrence text and findings are kept at every level.

Known limitations:
- light is a best-effort scrub. It cannot catch names, addresses or
  alphanumeric account numbers. Only strict removes all titles.
- Ids are kept. Anyone who also has the database can map them back to titles.
- Structure reveals habits: dates, counts and findings stay. A
  possible_duplicates finding shows that two tasks share a title, and a
  title_hygiene finding shows properties of a title, without the title itself.
"""

from __future__ import annotations

import copy
import hashlib
import re
from base64 import b32encode
from collections.abc import Callable, Iterable
from typing import Any

LEVELS = ("none", "light", "strict")
LABEL_LENGTH = 6  # 30 bits per kind: a collision is very unlikely
COLLISION_SUFFIX_LENGTH = 4

KIND_LABELS = {
    "area": "Area",
    "project": "Project",
    "heading": "Heading",
    "task": "Task",
    "tag": "Tag",
    "template": "Template",
}

# --- light scrubbing ----

_URL = re.compile(r"(?i)\b(?:https?://|www\.)[^\s<>\"']+")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_NUMBER = r"\d+(?:[.,]\d+)*"
_CURRENCY_SIGN = r"[$€£¥₹]"
_CURRENCY_CODE = r"\b(?:USD|EUR|GBP|INR|JPY|CHF|AUD|CAD)\b"
_AMOUNT = re.compile(
    rf"(?:{_CURRENCY_SIGN}|{_CURRENCY_CODE}|\bRs\.?)\s?{_NUMBER}"
    rf"|{_NUMBER}\s?(?:{_CURRENCY_SIGN}|{_CURRENCY_CODE})"
)
_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}[/-]\d{1,2}[/-]\d{4}\b")
_PHONE = re.compile(r"(?<![\w+])\+?\(?\d[\d \t().-]*\d(?!\w)")
_LONG_DIGITS = re.compile(r"\d{8,}")
_DATE_MARK = "\x00{}\x00"
_DATE_MARK_RE = re.compile(r"\x00(\d+)\x00")


def scrub(text: str | None) -> str | None:
    """Replace URLs, emails, amounts, phone numbers and long digit runs."""
    if not text:
        return text
    text = _URL.sub("<url>", text)
    text = _EMAIL.sub("<email>", text)
    text = _AMOUNT.sub("<amount>", text)
    dates: list[str] = []

    def hide_date(match: re.Match[str]) -> str:
        dates.append(match.group(0))
        return _DATE_MARK.format(len(dates) - 1)

    text = _DATE.sub(hide_date, text)
    text = _PHONE.sub(_phone, text)
    text = _LONG_DIGITS.sub("<number>", text)
    return _DATE_MARK_RE.sub(lambda m: dates[int(m.group(1))], text)


def _phone(match: re.Match[str]) -> str:
    candidate = match.group(0)
    digits = sum(c.isdigit() for c in candidate)
    separated = candidate.startswith("+") or any(c in " \t().-" for c in candidate)
    if digits >= 7 and separated:
        return "<phone>"
    return candidate


# --- strict labels ----


def _code(identifier: str) -> str:
    digest = hashlib.sha256(identifier.encode("utf-8")).digest()
    return b32encode(digest).decode("ascii").rstrip("=").lower()


def make_labels(
    kind: str, ids: Iterable[str], length: int = LABEL_LENGTH
) -> dict[str, str]:
    """A label per id, from the id alone.

    Ids whose short codes collide within the kind all get a longer code (the
    next characters of the same hash), so the result never depends on which
    other ids exist or on their order, except for the colliding ids themselves.
    """
    name = KIND_LABELS[kind]
    unique = sorted(set(ids))
    codes = {i: _code(i) for i in unique}
    short: dict[str, list[str]] = {}
    for identifier in unique:
        short.setdefault(codes[identifier][:length], []).append(identifier)
    labels = {}
    for prefix, members in short.items():
        if len(members) == 1:
            labels[members[0]] = f"{name} {prefix}"
            continue
        longer = {m: codes[m][: length + COLLISION_SUFFIX_LENGTH] for m in members}
        for member in members:
            clash = list(longer.values()).count(longer[member]) > 1
            suffix = codes[member] if clash else longer[member]
            labels[member] = f"{name} {prefix}-{suffix[length:]}"
    return labels


_CODE = "[a-z2-7]"
_FULL_CODE_LENGTH = 52  # base32 of a sha256 digest, without padding
# A whole label as make_labels writes it: kind, one space, the short code, and
# for a collision "-" plus the longer code. Used by `decode` to find labels. A
# letter or digit next to it means it is part of a longer word; punctuation and
# markdown marks, including "_", do not.
_CODE_PART = (
    rf"{_CODE}{{{LABEL_LENGTH}}}"
    + rf"(?:-(?:{_CODE}{{{_FULL_CODE_LENGTH - LABEL_LENGTH}}}"
    + rf"|{_CODE}{{{COLLISION_SUFFIX_LENGTH}}}))?"
)
LABEL_PATTERN = re.compile(
    r"(?<![^\W_])(?:"
    + "|".join(sorted(KIND_LABELS.values(), key=len, reverse=True))
    + rf") {_CODE_PART}"
    + r"(?![^\W_])"
)
# The code part of a label on its own ("k3f7az"), as assistants often write it.
BARE_CODE_PATTERN = re.compile(rf"(?<![^\W_]){_CODE_PART}(?![^\W_])")


# --- the export ----


def anonymise(export: dict[str, Any], level: str) -> dict[str, Any]:
    """Return a new export at `level`. The input is not changed."""
    if level not in LEVELS:
        raise ValueError(f"unknown anonymisation level {level!r}")
    result = copy.deepcopy(export)
    result["anonymisation"] = level
    if level == "none":
        return result
    if level == "light":
        _rewrite(result, lambda kind, ref: scrub(ref.get("title")), strict=False)
    else:
        labels = _labels(result)
        _rewrite(result, lambda kind, ref: labels[kind].get(ref["id"]), strict=True)
    for entry in result["tasks"] + result["recurring_templates"]:
        if entry.get("recurrence"):
            entry["recurrence"] = _clean_recurrence(
                entry["recurrence"], strict=level == "strict"
            )
    result["warnings"] = [_clean_warning(w) for w in result.get("warnings", [])]
    return result


def _labels(export: dict[str, Any]) -> dict[str, dict[str, str]]:
    """Labels for every id that appears, by kind, including dangling refs."""
    seen: dict[str, set[str]] = {kind: set() for kind in KIND_LABELS}
    for area in export["areas"]:
        seen["area"].add(area["id"])
    for kind, key in (("project", "projects"), ("heading", "headings")):
        seen[kind].update(entry["id"] for entry in export[key])
    seen["task"].update(entry["id"] for entry in export["tasks"])
    seen["template"].update(entry["id"] for entry in export["recurring_templates"])
    for entry in _entries(export):
        for kind, ref in _refs(entry):
            seen[kind].add(ref["id"])
    return {kind: make_labels(kind, ids) for kind, ids in seen.items()}


def _entries(export: dict[str, Any]) -> list[dict[str, Any]]:
    return (
        export["projects"]
        + export["headings"]
        + export["tasks"]
        + export["recurring_templates"]
    )


def _refs(entry: dict[str, Any]):
    """(kind, reference) for every {id, title} reference inside an entry."""
    for key, kind in (
        ("area", "area"),
        ("project", "project"),
        ("heading", "heading"),
        ("recurring_template", "template"),
    ):
        if entry.get(key):
            yield kind, entry[key]
    for tag in entry.get("tags") or []:
        yield "tag", tag


def _rewrite(
    export: dict[str, Any],
    title_for: Callable[[str, dict[str, Any]], str | None],
    *,
    strict: bool,
) -> None:
    """Replace every title through `title_for(kind, {id, title})`."""
    for area in export["areas"]:
        area["title"] = title_for("area", area)
    for key, kind in (
        ("projects", "project"),
        ("headings", "heading"),
        ("tasks", "task"),
        ("recurring_templates", "template"),
    ):
        for entry in export[key]:
            entry["title"] = title_for(kind, entry)
            entry["notes"] = None
            for ref_kind, ref in _refs(entry):
                if ref.get("title") is not None or strict:
                    ref["title"] = title_for(ref_kind, ref)
            if "checklist" not in entry:
                continue
            if strict:
                entry["checklist"] = None
            else:
                for item in entry["checklist"]:
                    item["title"] = scrub(item["title"])


# --- the prompt payload ----

PAYLOAD_LISTS = (
    ("areas", "area"),
    ("projects", "project"),
    ("headings", "heading"),
    ("tasks", "task"),
    ("tags", "tag"),
    ("recurring_templates", "template"),
)


def anonymise_payload(
    payload: dict[str, Any],
    level: str,
    labels: dict[str, dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Return a new prompt payload at `light` or `strict`, by the same rules as
    the export. At strict, `labels` (kind -> {id: label}) must cover the whole
    database, as `decode.labels_by_kind` does, so that `decode` maps them back.
    The input is not changed."""
    if level not in ("light", "strict"):
        raise ValueError(f"the payload must be light or strict, not {level!r}")
    if level == "strict" and labels is None:
        raise ValueError("strict needs labels for the whole database")
    strict = level == "strict"
    if strict:
        assert labels is not None

        def title_for(kind: str, ref: dict[str, Any]) -> str | None:
            return labels[kind].get(ref["id"])
    else:

        def title_for(kind: str, ref: dict[str, Any]) -> str | None:
            return scrub(ref.get("title"))

    result = copy.deepcopy(payload)
    result["anonymisation"] = level
    for key, kind in PAYLOAD_LISTS:
        for entry in result[key]:
            entry["title"] = title_for(kind, entry)
            if "notes" in entry:
                entry["notes"] = None
            for ref_kind, ref in _refs(entry):
                if ref.get("title") is not None or strict:
                    ref["title"] = title_for(ref_kind, ref)
            if entry.get("recurrence"):
                entry["recurrence"] = _clean_recurrence(
                    entry["recurrence"], strict=strict
                )
    result["data_read_warnings"] = [
        _clean_warning(w) for w in result.get("data_read_warnings", [])
    ]
    return result


# --- technical fields ----

_QUOTED = re.compile(r"""[bB]?(['"])(?:\\.|(?!\1).)*\1""")
_NUMBER_VALUE = re.compile(r"-?\d+(?:\.\d+)?(?:e[+-]?\d+)?", re.I)


WITHHELD_RULE_FIELDS = ("ed", "ia", "sr")  # end, anchor and start timestamps


def _clean_recurrence(recurrence: dict[str, Any], *, strict: bool) -> dict[str, Any]:
    raw = recurrence.get("raw")
    if isinstance(raw, dict):
        raw = {k: v for k, v in raw.items() if k != "_hex_prefix"}
        if strict:
            raw = {k: None if k in WITHHELD_RULE_FIELDS else v for k, v in raw.items()}
    return {
        **recurrence,
        "notes": [_QUOTED.sub("<text>", note) for note in recurrence.get("notes", [])],
        "raw": _strip_strings(raw),
    }


def _strip_strings(value: Any) -> Any:
    if isinstance(value, str):
        return "<text>"
    if isinstance(value, dict):
        return {key: _strip_strings(inner) for key, inner in value.items()}
    if isinstance(value, list):
        return [_strip_strings(inner) for inner in value]
    return value


_WARNINGS = (
    re.compile(
        r"^(?P<head>TMTask \S+: \w+ )(?P<value>.+)"
        r"(?P<tail> could not be decoded; treated as missing)$"
    ),
    re.compile(
        r"^(?P<head>TMTask \S+: unknown type )(?P<value>.+)(?P<tail>; skipped)$"
    ),
    re.compile(r"^(?P<head>TMTask \S+: unknown \w+ )(?P<value>.+)(?P<tail>)$"),
    re.compile(
        r"^(?P<head>TMTask \S+: (?:area|project|heading) )(?P<value>.+)"
        r"(?P<tail> does not exist; ignored)$"
    ),
)
_FIXED_WARNINGS = re.compile(
    r"^TMTask \S+: (?:listed by things\.py but not found|"
    r"not listed by things\.py; skipped)$"
)


def _clean_warning(warning: str) -> str:
    """Keep the id and column; replace a value that is not a number."""
    if _FIXED_WARNINGS.match(warning):
        return warning
    for pattern in _WARNINGS:
        match = pattern.match(warning)
        if match:
            value = match.group("value")
            if not _NUMBER_VALUE.fullmatch(value):
                value = "<value>"
            return match.group("head") + value + match.group("tail")
    head = warning.split(":", 1)[0] if warning.startswith("TMTask ") else "warning"
    return f"{head}: <warning text withheld>"
