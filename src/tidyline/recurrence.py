"""Decode and describe Things recurrence rules (DESIGN.md 7.2, docs/RECURRENCE.md).

Pure functions only: no I/O, no things.py. `parse_rule` never raises.
"""

from __future__ import annotations

import datetime as dt
import math
import plistlib
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

Unit = Literal["day", "week", "month", "year"]
Confidence = Literal["verified", "assumed", "unrecognised"]

UNREADABLE_TEXT = "recurring (rule unreadable)"
NOT_RECOGNISED_TEXT = "recurring (rule not recognised)"

UNITS: dict[int, Unit] = {16: "day", 256: "week", 8: "month", 4: "year"}
SUPPORTED_RULE_VERSION = 4
NEVER_ENDS_THRESHOLD = 6.0e10  # ed at or above this looks like "never ends"
KNOWN_FIELDS = frozenset({"fu", "fa", "tp", "of", "ed", "ia", "rc", "rrv", "sr", "ts"})

# Upper bounds that keep the text sane; real rules are far below them.
MAX_INTERVAL = 10_000
MAX_REPEAT_LIMIT = 1_000_000
MAX_LEAD_DAYS = 1_000_000

WEEKDAYS = ("Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat")
MONTHS = (
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
)  # fmt: skip
DAYS_IN_MONTH = (31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
ORDINALS = {1: "first", 2: "second", 3: "third", 4: "fourth", -1: "last"}

# Offset key sets allowed per unit. Day offsets are ignored entirely.
OFFSET_SHAPES: dict[Unit, tuple[frozenset[str], ...]] = {
    "week": (frozenset({"wd"}),),
    "month": (frozenset({"dy"}), frozenset({"wd", "wdo"})),
    "year": (frozenset({"dy", "mo"}),),
}
OFFSET_RANGES = {
    "wd": range(0, 7),
    "dy": range(-1, 31),
    "mo": range(0, 12),
    "wdo": (-1, 1, 2, 3, 4),
}

_MAX_RAW_DEPTH = 20
_MAX_SHOWN = 60


@dataclass(frozen=True)
class Rule:
    recognised: bool
    text: str
    unit: Unit | None = None
    interval: int | None = None
    after_completion: bool = False
    has_end_date: bool = False
    repeat_limit: int | None = None
    start_days_before_deadline: int | None = None
    confidence: Confidence = "unrecognised"
    notes: tuple[str, ...] = ()
    raw: dict[str, Any] = field(default_factory=dict, hash=False)


def parse_rule(value: object) -> Rule:
    """Describe a rule given as binary-plist bytes or an already-decoded dict."""
    try:
        return _parse(value)
    except Exception as error:  # last resort: parse_rule must never raise
        return Rule(
            recognised=False,
            text=NOT_RECOGNISED_TEXT,
            notes=(f"could not be interpreted: {type(error).__name__}",),
            raw={
                "_decode_error": f"could not be interpreted: {type(error).__name__}",
                "_hex_prefix": "",
            },
        )


def _parse(value: object) -> Rule:
    if isinstance(value, (bytes, bytearray, memoryview)):
        data = bytes(value)
        try:
            decoded = plistlib.loads(data, fmt=plistlib.FMT_BINARY)
        except Exception as error:
            return _unreadable(f"not a binary plist ({_error_text(error)})", data)
        if not isinstance(decoded, Mapping):
            kind = type(decoded).__name__
            return _unreadable(f"plist holds a {kind}, not a dict", data)
        rule = decoded
    elif isinstance(value, Mapping):
        rule = value
    else:
        return Rule(
            recognised=False,
            text=UNREADABLE_TEXT,
            notes=(f"expected bytes or a dict, got {type(value).__name__}",),
            raw={
                "_decode_error": f"unsupported input type {type(value).__name__}",
                "_hex_prefix": "",
            },
        )

    raw = _json_safe(rule, 0, frozenset())
    if not isinstance(raw, dict):  # a Mapping that copied into a cycle marker
        raw = {"_decode_error": "rule could not be copied", "_hex_prefix": ""}
    extra_notes = _unfamiliar_fields(rule) + _unfamiliar_values(rule)

    problems, unit, interval, after_completion, offsets = _check(rule)
    if problems:
        return Rule(
            recognised=False,
            text=NOT_RECOGNISED_TEXT,
            confidence="unrecognised",
            notes=tuple(problems + extra_notes),
            raw=raw,
        )

    assumed: list[str] = []
    calendar_notes: list[str] = []
    if after_completion:
        base = f"{interval} {_plural(unit, interval)} after completion"
    else:
        base = _base_text(unit, interval, offsets, assumed, calendar_notes)

    repeat_limit = _repeat_limit(rule.get("rc"))
    has_end_date = _has_end_date(rule)
    lead_days = _lead_days(rule.get("ts"))
    suffix = []
    if repeat_limit is not None:
        suffix.append(f"ends after {repeat_limit} {_plural('time', repeat_limit)}")
    if has_end_date:
        suffix.append("has an end date")
    if lead_days is not None:
        suffix.append(f"starts {lead_days} {_plural('day', lead_days)} before deadline")
    text = f"{base} ({'; '.join(suffix)})" if suffix else base

    return Rule(
        recognised=True,
        text=text,
        unit=unit,
        interval=interval,
        after_completion=after_completion,
        has_end_date=has_end_date,
        repeat_limit=repeat_limit,
        start_days_before_deadline=lead_days,
        confidence="assumed" if assumed else "verified",
        notes=tuple(extra_notes + calendar_notes + assumed),
        raw=raw,
    )


# --- recognition -----------------------------------------------------------


def _check(rule: Mapping) -> tuple[list[str], Unit | None, int, bool, list[dict]]:
    """Return (problems, unit, interval, after_completion, usable offsets)."""
    problems: list[str] = []

    rrv = rule.get("rrv")
    if "rrv" not in rule:
        problems.append("rule version (rrv) is missing")
    elif not (_is_int(rrv) and rrv == SUPPORTED_RULE_VERSION):
        problems.append(f"unknown rule version: rrv={_show(rrv)}")

    fu = rule.get("fu")
    unit = UNITS.get(fu) if _is_int(fu) else None
    if unit is None:
        problems.append(f"unknown unit: fu={_show(fu)}")

    fa = rule.get("fa")
    if not (_is_int(fa) and 1 <= fa <= MAX_INTERVAL):
        problems.append(
            f"interval is not a whole number from 1 to {MAX_INTERVAL}: fa={_show(fa)}"
        )

    tp = rule.get("tp")
    if not (_is_int(tp) and tp in (0, 1)):
        problems.append(f"unknown schedule type: tp={_show(tp)}")
    after_completion = _is_int(tp) and tp == 1

    offsets: list[dict] = []
    if unit is not None and unit != "day":
        offsets = _check_offsets(rule, unit, after_completion, problems)

    return problems, unit, fa if _is_int(fa) else 0, after_completion, offsets


def _check_offsets(
    rule: Mapping, unit: Unit, after_completion: bool, problems: list[str]
) -> list[dict]:
    if "of" not in rule:
        if not after_completion:
            problems.append(f"offsets (of) are missing for a {_adjective(unit)} rule")
        return []
    entries = rule["of"]
    if not isinstance(entries, list):
        problems.append(f"offsets (of) are a {type(entries).__name__}, not a list")
        return []

    problems_before = len(problems)
    usable = []
    for position, entry in enumerate(entries):
        if not isinstance(entry, Mapping):
            problems.append(f"offset {position} is not a dict ({type(entry).__name__})")
            continue
        keys = frozenset(entry)
        if keys not in OFFSET_SHAPES[unit]:
            shown = ", ".join(sorted(_show_key(k) for k in entry)) or "none"
            problems.append(
                f"offset {position} has keys {{{shown}}}, which do not fit a "
                f"{_adjective(unit)} rule"
            )
            continue
        bad = [
            f"{key}={_show(entry[key])}"
            for key in sorted(keys)
            if not (_is_int(entry[key]) and entry[key] in OFFSET_RANGES[key])
        ]
        if bad:
            problems.append(
                f"offset {position} has values out of range: {', '.join(bad)}"
            )
            continue
        usable.append(dict(entry))

    if not usable and not after_completion and len(problems) == problems_before:
        problems.append(f"no usable offsets for a {_adjective(unit)} rule")
    return usable


# --- text ------------------------------------------------------------------


def _base_text(
    unit: Unit,
    interval: int,
    offsets: list[dict],
    assumed: list[str],
    calendar_notes: list[str],
) -> str:
    if interval == 1:
        prefix = {"day": "Daily", "week": "Weekly", "month": "Monthly"}.get(
            unit, "Yearly"
        )
    else:
        prefix = f"Every {interval} {unit}s"
    if unit == "day":
        return prefix

    if unit == "week":
        parts = [WEEKDAYS[wd] for wd in sorted({e["wd"] for e in offsets})]
    elif unit == "month":
        parts = _month_parts(offsets, assumed)
    else:
        parts = _year_parts(offsets, assumed, calendar_notes)
    return f"{prefix} on {', '.join(parts)}"


def _month_parts(offsets: list[dict], assumed: list[str]) -> list[str]:
    days = sorted({e["dy"] for e in offsets if "dy" in e}, key=lambda d: (d < 0, d))
    ordinals = sorted(
        {(e["wdo"], e["wd"]) for e in offsets if "wdo" in e},
        key=lambda pair: (pair[0] < 0, pair[0], pair[1]),
    )
    parts = ["last day" if dy == -1 else f"day {dy + 1}" for dy in days]
    parts += [f"the {ORDINALS[wdo]} {WEEKDAYS[wd]}" for wdo, wd in ordinals]
    if -1 in days:
        assumed.append(_ASSUMED_LAST_DAY)
    for wdo in sorted({wdo for wdo, _ in ordinals if wdo != -1}):
        assumed.append(
            f"assumed convention: wdo {wdo} read as '{ORDINALS[wdo]}' "
            "(only wdo -1 has been checked against the app)"
        )
    return parts


def _year_parts(
    offsets: list[dict], assumed: list[str], calendar_notes: list[str]
) -> list[str]:
    dates = sorted(
        {(e["mo"], e["dy"]) for e in offsets}, key=lambda p: (p[0], p[1] < 0, p[1])
    )
    parts = []
    for mo, dy in dates:
        if dy == -1:
            parts.append(f"the last day of {MONTHS[mo]}")
            continue
        parts.append(f"{MONTHS[mo]} {dy + 1}")
        if dy + 1 > DAYS_IN_MONTH[mo]:
            calendar_notes.append(
                f"unfamiliar value: {MONTHS[mo]} {dy + 1} is not a calendar date"
            )
    if any(dy == -1 for _, dy in dates):
        assumed.append(_ASSUMED_LAST_DAY)
    return parts


_ASSUMED_LAST_DAY = (
    "assumed convention: dy -1 read as the last day of the month "
    "(not seen on a real database)"
)


# --- suffix fields ---------------------------------------------------------


def _repeat_limit(rc: object) -> int | None:
    if _is_int(rc) and 0 < rc <= MAX_REPEAT_LIMIT:
        return rc
    return None


def _has_end_date(rule: Mapping) -> bool:
    ed = rule.get("ed")
    return _is_number(ed) and ed < NEVER_ENDS_THRESHOLD


def _lead_days(ts: object) -> int | None:
    if _is_int(ts) and -MAX_LEAD_DAYS <= ts < 0:
        return -ts
    return None


def _unfamiliar_fields(rule: Mapping) -> list[str]:
    unknown = [key for key in rule if key not in KNOWN_FIELDS]
    names = sorted(_show_key(key) for key in unknown)
    return [f"unfamiliar field: {name}" for name in names]


def _unfamiliar_values(rule: Mapping) -> list[str]:
    notes = []
    if "rc" in rule:
        rc = rule["rc"]
        if not (_is_int(rc) and 0 <= rc <= MAX_REPEAT_LIMIT):
            notes.append(f"unfamiliar value: rc={_show(rc)}")
    if "ts" in rule:
        ts = rule["ts"]
        if not (_is_int(ts) and -MAX_LEAD_DAYS <= ts <= 0):
            notes.append(f"unfamiliar value: ts={_show(ts)}")
    if "ed" in rule and not _is_number(rule["ed"]):
        notes.append(f"unfamiliar value: ed={_show(rule['ed'])}")
    return notes


# --- helpers ---------------------------------------------------------------


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value: object) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return not isinstance(value, float) or math.isfinite(value)


def _plural(word: str, count: int) -> str:
    return word if count == 1 else f"{word}s"


def _adjective(unit: Unit) -> str:
    return {"day": "daily", "week": "weekly", "month": "monthly"}.get(unit, "yearly")


def _show(value: object) -> str:
    """A short, safe repr of a value for notes. Never raises."""
    if _is_int(value) and value.bit_length() > 64:
        return f"<integer of {value.bit_length()} bits>"
    try:
        text = repr(value)
    except Exception:
        return f"<unprintable {type(value).__name__}>"
    return _shorten(text)


def _show_key(key: object) -> str:
    """A field name as plain text (no quotes for strings). Never raises."""
    return _shorten(key) if isinstance(key, str) else _show(key)


def _shorten(text: str) -> str:
    return text if len(text) <= _MAX_SHOWN else text[: _MAX_SHOWN - 3] + "..."


def _error_text(error: Exception) -> str:
    try:
        message = str(error)
    except Exception:
        message = ""
    text = f"{type(error).__name__}: {message}" if message else type(error).__name__
    return text[:200]


def _unreadable(reason: str, data: bytes) -> Rule:
    return Rule(
        recognised=False,
        text=UNREADABLE_TEXT,
        notes=(reason,),
        raw={"_decode_error": reason, "_hex_prefix": data[:16].hex()},
    )


def _json_safe(value: object, depth: int, seen: frozenset[int]) -> Any:
    """Copy a decoded plist into plain JSON types. Never follows a cycle."""
    if depth > _MAX_RAW_DEPTH:
        return "<nested too deeply>"
    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, int):
        return value if value.bit_length() <= 64 else _show(value)
    if isinstance(value, float):
        return value if math.isfinite(value) else repr(value)
    if isinstance(value, (bytes, bytearray)):
        return {"_bytes_hex": bytes(value[:64]).hex(), "_length": len(value)}
    if isinstance(value, dt.datetime):
        return value.isoformat()
    if isinstance(value, plistlib.UID):
        return {"_uid": _json_safe(value.data, depth + 1, seen)}
    if isinstance(value, (Mapping, list, tuple)):
        if id(value) in seen:
            return "<cycle>"
        inner = seen | {id(value)}
        if isinstance(value, Mapping):
            return {
                _show_key(key): _json_safe(item, depth + 1, inner)
                for key, item in value.items()
            }
        return [_json_safe(item, depth + 1, inner) for item in value]
    return _show(value)
