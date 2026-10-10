import datetime as dt
import json
import plistlib
import random
import sqlite3
from collections.abc import Mapping

import pytest
from fixtures import build_fixture as bf

from tidyline.recurrence import (
    MAX_BLOB_BYTES,
    NOT_RECOGNISED_TEXT,
    UNREADABLE_TEXT,
    Rule,
    parse_rule,
)

FIXED_TODAY = dt.date(2026, 10, 10)
NEVER = 64092211200.0
bf_limit = MAX_BLOB_BYTES


def rule(fu=8, fa=1, tp=0, of=None, **extra):
    """A rule shaped like a real one: every observed key, never-ending ed."""
    base = {
        "fu": fu,
        "fa": fa,
        "tp": tp,
        "of": [{"dy": 0}] if of is None else of,
        "ia": 700000000.0,
        "sr": 700003600.0,
        "rc": 0,
        "rrv": 4,
        "ts": 0,
        "ed": NEVER,
    }
    base.update(extra)
    return base


def text(**kwargs):
    return parse_rule(rule(**kwargs)).text


def assert_never_raises_and_is_well_formed(value):
    result = parse_rule(value)
    assert isinstance(result, Rule)
    assert isinstance(result.text, str) and result.text
    assert result.confidence in ("verified", "assumed", "unrecognised")
    assert all(isinstance(note, str) for note in result.notes)
    json.dumps(result.raw, allow_nan=False)  # JSON-safe
    if result.recognised:
        assert result.confidence != "unrecognised"
        assert not result.text.startswith("recurring (")
    else:
        assert result.confidence == "unrecognised"
        assert result.text in (UNREADABLE_TEXT, NOT_RECOGNISED_TEXT)
    return result


# --- every fixture rule, read back through sqlite3 ----------------------------

FIXTURE_TEXT = {
    "tpl_daily": ("Daily", "verified", ()),
    "tpl_weekly_sun": ("Weekly on Sun", "verified", ()),
    "tpl_weekly_fri": ("Weekly on Fri", "verified", ()),
    "tpl_weekly_sat": ("Weekly on Sat", "verified", ()),
    "tpl_biweekly_sun": ("Every 2 weeks on Sun", "verified", ()),
    "tpl_monthly_first": ("Monthly on day 1", "verified", ()),
    "tpl_monthly_15": ("Monthly on day 15", "verified", ()),
    "tpl_monthly_last": (
        "Monthly on last day",
        "assumed",
        (
            "assumed convention: dy -1 read as the last day of the month "
            "(not seen on a real database)",
        ),
    ),
    "tpl_every3_months": ("Every 3 months on day 5", "verified", ()),
    "tpl_every6_months": ("Every 6 months on day 14", "verified", ()),
    "tpl_monthly_first_sun": (
        "Monthly on the first Sun",
        "assumed",
        (
            "assumed convention: wdo 1 read as 'first' "
            "(only wdo -1 has been checked against the app)",
        ),
    ),
    "tpl_monthly_last_sun": ("Monthly on the last Sun", "verified", ()),
    "tpl_yearly_feb28": ("Yearly on Feb 28", "verified", ()),
    "tpl_yearly_jan1": ("Yearly on Jan 1", "verified", ()),
    "tpl_after_completion": ("1 year after completion", "verified", ()),
    "tpl_no_ed": ("Weekly on Sun", "verified", ()),
    "tpl_end_date": ("Monthly on day 1 (has an end date)", "verified", ()),
    "tpl_repeat_count": ("Weekly on Sat (ends after 12 times)", "verified", ()),
    "tpl_lead_time": (
        "Monthly on day 14 (starts 7 days before deadline)",
        "verified",
        (),
    ),
    "tpl_rrv5": (NOT_RECOGNISED_TEXT, "unrecognised", ("unknown rule version: rrv=5",)),
    "tpl_unknown_unit": (
        NOT_RECOGNISED_TEXT,
        "unrecognised",
        ("unknown unit: fu=999",),
    ),
    "tpl_extra_key": ("Weekly on Sun", "verified", ("unfamiliar field: zz",)),
    "tpl_paused": ("Weekly on Sat", "verified", ()),
    "tpl_trashed": ("Monthly on day 14", "verified", ()),
    "tpl_leftover": ("Monthly on day 1", "verified", ()),
    "tpl_invalid_plist": (
        UNREADABLE_TEXT,
        "unrecognised",
        ("not a readable plist (InvalidFileException: Invalid file)",),
    ),
}


@pytest.fixture
def fixture_rules(tmp_path):
    path = tmp_path / "fixture.sqlite"
    bf.build_fixture(path, FIXED_TODAY)
    conn = sqlite3.connect(path)
    try:
        blobs = dict(
            conn.execute(
                "SELECT uuid, rt1_recurrenceRule FROM TMTask "
                "WHERE rt1_recurrenceRule IS NOT NULL"
            ).fetchall()
        )
    finally:
        conn.close()
    keys = {bf.make_uuid(key): key for key in FIXTURE_TEXT}
    return {keys[uuid]: blob for uuid, blob in blobs.items()}


def test_fixture_covers_every_template(fixture_rules):
    assert set(fixture_rules) == set(FIXTURE_TEXT)


@pytest.mark.parametrize("key", sorted(FIXTURE_TEXT))
def test_fixture_rule(fixture_rules, key):
    expected_text, confidence, notes = FIXTURE_TEXT[key]
    result = assert_never_raises_and_is_well_formed(fixture_rules[key])
    assert result.text == expected_text
    assert result.confidence == confidence
    assert result.notes == notes


def test_fixture_rule_fields(fixture_rules):
    after = parse_rule(fixture_rules["tpl_after_completion"])
    assert (after.unit, after.interval, after.after_completion) == ("year", 1, True)
    limited = parse_rule(fixture_rules["tpl_repeat_count"])
    assert limited.repeat_limit == 12
    assert not limited.has_end_date
    lead = parse_rule(fixture_rules["tpl_lead_time"])
    assert lead.start_days_before_deadline == 7
    assert parse_rule(fixture_rules["tpl_end_date"]).has_end_date
    assert not parse_rule(fixture_rules["tpl_no_ed"]).has_end_date
    biweekly = parse_rule(fixture_rules["tpl_biweekly_sun"])
    assert (biweekly.unit, biweekly.interval) == ("week", 2)


def test_raw_is_a_json_safe_copy(fixture_rules):
    result = parse_rule(fixture_rules["tpl_extra_key"])
    assert result.raw == plistlib.loads(fixture_rules["tpl_extra_key"])
    assert json.loads(json.dumps(result.raw)) == result.raw


def test_unreadable_raw_has_error_and_hex_prefix(fixture_rules):
    result = parse_rule(fixture_rules["tpl_invalid_plist"])
    assert set(result.raw) == {"_decode_error", "_hex_prefix", "_length"}
    assert result.raw["_hex_prefix"] == bf.INVALID_RULE_BLOB[:16].hex()
    assert result.raw["_length"] == len(bf.INVALID_RULE_BLOB)


# --- text formats -----------------------------------------------------------


@pytest.mark.parametrize(
    "kwargs, expected",
    [
        ({"fu": 16, "of": [{"dy": 0}]}, "Daily"),
        ({"fu": 16, "fa": 3, "of": [{"dy": 0}]}, "Every 3 days"),
        ({"fu": 256, "of": [{"wd": 0}]}, "Weekly on Sun"),
        ({"fu": 256, "fa": 2, "of": [{"wd": 0}]}, "Every 2 weeks on Sun"),
        (
            {"fu": 256, "of": [{"wd": 6}, {"wd": 1}, {"wd": 5}, {"wd": 1}]},
            "Weekly on Mon, Fri, Sat",
        ),
        ({"fu": 8, "of": [{"dy": 14}]}, "Monthly on day 15"),
        ({"fu": 8, "fa": 3, "of": [{"dy": 0}]}, "Every 3 months on day 1"),
        ({"fu": 8, "of": [{"dy": -1}]}, "Monthly on last day"),
        ({"fu": 8, "of": [{"dy": 30}]}, "Monthly on day 31"),
        ({"fu": 8, "of": [{"wd": 0, "wdo": -1}]}, "Monthly on the last Sun"),
        (
            {"fu": 8, "fa": 3, "of": [{"wd": 0, "wdo": 1}]},
            "Every 3 months on the first Sun",
        ),
        ({"fu": 8, "of": [{"wd": 3, "wdo": 2}]}, "Monthly on the second Wed"),
        ({"fu": 8, "of": [{"wd": 5, "wdo": 3}]}, "Monthly on the third Fri"),
        ({"fu": 8, "of": [{"wd": 1, "wdo": 4}]}, "Monthly on the fourth Mon"),
        (
            {"fu": 8, "of": [{"dy": -1}, {"dy": 14}, {"dy": 0}]},
            "Monthly on day 1, day 15, last day",
        ),
        ({"fu": 4, "of": [{"dy": 27, "mo": 1}]}, "Yearly on Feb 28"),
        ({"fu": 4, "fa": 2, "of": [{"dy": 27, "mo": 1}]}, "Every 2 years on Feb 28"),
        ({"fu": 4, "of": [{"dy": 9, "mo": 2}]}, "Yearly on Mar 10"),
        (
            {"fu": 4, "of": [{"dy": 0, "mo": 11}, {"dy": 0, "mo": 0}]},
            "Yearly on Jan 1, Dec 1",
        ),
        ({"fu": 4, "of": [{"dy": -1, "mo": 1}]}, "Yearly on the last day of Feb"),
    ],
)
def test_text_formats(kwargs, expected):
    assert text(**kwargs) == expected


def test_units_and_intervals_are_reported():
    result = parse_rule(rule(fu=8, fa=3, of=[{"dy": 0}]))
    assert (result.recognised, result.unit, result.interval) == (True, "month", 3)
    assert not result.after_completion


def test_daily_offsets_are_ignored():
    assert text(fu=16, of=[{"anything": "goes"}]) == "Daily"
    assert text(fu=16, of="not even a list") == "Daily"
    no_of = rule(fu=16)
    del no_of["of"]
    assert parse_rule(no_of).text == "Daily"


@pytest.mark.parametrize(
    "kwargs, expected",
    [
        ({"fu": 4, "tp": 1, "of": [{"dy": 0, "mo": 7}]}, "1 year after completion"),
        ({"fu": 256, "fa": 3, "tp": 1, "of": [{"wd": 2}]}, "3 weeks after completion"),
        ({"fu": 16, "tp": 1}, "1 day after completion"),
        ({"fu": 8, "fa": 2, "tp": 1, "of": []}, "2 months after completion"),
        # dy -1 is not used in the text, so the rule stays verified
        ({"fu": 8, "tp": 1, "of": [{"dy": -1}]}, "1 month after completion"),
    ],
)
def test_after_completion_ignores_offsets(kwargs, expected):
    result = parse_rule(rule(**kwargs))
    assert result.text == expected
    assert result.after_completion
    assert result.confidence == "verified"


def test_after_completion_without_offsets_is_recognised():
    no_of = rule(fu=256, tp=1)
    del no_of["of"]
    assert parse_rule(no_of).text == "1 week after completion"


def test_after_completion_still_rejects_malformed_offsets():
    result = parse_rule(rule(fu=256, tp=1, of=[{"dy": 3}]))
    assert not result.recognised


# --- not recognised ---------------------------------------------------------


@pytest.mark.parametrize(
    "kwargs, note",
    [
        ({"rrv": 5}, "unknown rule version: rrv=5"),
        ({"rrv": 3}, "unknown rule version: rrv=3"),
        ({"rrv": "4"}, "unknown rule version: rrv='4'"),
        ({"rrv": True}, "unknown rule version: rrv=True"),
        ({"fu": 999}, "unknown unit: fu=999"),
        ({"fu": 32}, "unknown unit: fu=32"),
        ({"fa": 0}, "interval is not a whole number from 1 to 10000: fa=0"),
        ({"fa": 1.0}, "interval is not a whole number from 1 to 10000: fa=1.0"),
        ({"tp": 2}, "unknown schedule type: tp=2"),
        ({"fu": 256, "of": [{"wd": 7}]}, "offset 0 has values out of range: wd=7"),
        ({"fu": 256, "of": [{"wd": -1}]}, "offset 0 has values out of range: wd=-1"),
        ({"fu": 8, "of": [{"dy": 31}]}, "offset 0 has values out of range: dy=31"),
        ({"fu": 8, "of": [{"dy": -2}]}, "offset 0 has values out of range: dy=-2"),
        (
            {"fu": 8, "of": [{"wd": 0, "wdo": 5}]},
            "offset 0 has values out of range: wdo=5",
        ),
        (
            {"fu": 8, "of": [{"wd": 0, "wdo": 0}]},
            "offset 0 has values out of range: wdo=0",
        ),
        (
            {"fu": 4, "of": [{"dy": 0, "mo": 12}]},
            "offset 0 has values out of range: mo=12",
        ),
        (
            {"fu": 256, "of": [{"dy": 0}]},
            "offset 0 has keys {dy}, which do not fit a weekly rule",
        ),
        (
            {"fu": 8, "of": [{"wd": 0}]},
            "offset 0 has keys {wd}, which do not fit a monthly rule",
        ),
        (
            {"fu": 4, "of": [{"dy": 0}]},
            "offset 0 has keys {dy}, which do not fit a yearly rule",
        ),
        ({"fu": 256, "of": []}, "no usable offsets for a weekly rule"),
        ({"fu": 8, "of": {"dy": 0}}, "offsets (of) are a dict, not a list"),
        ({"fu": 8, "of": [0]}, "offset 0 is not a dict (int)"),
    ],
)
def test_not_recognised(kwargs, note):
    result = parse_rule(rule(**kwargs))
    assert not result.recognised
    assert result.text == NOT_RECOGNISED_TEXT
    assert result.confidence == "unrecognised"
    assert note in result.notes
    assert result.unit is None and result.repeat_limit is None


def test_missing_rule_version_and_offsets():
    no_rrv = rule()
    del no_rrv["rrv"]
    assert "rule version (rrv) is missing" in parse_rule(no_rrv).notes
    no_of = rule(fu=256)
    del no_of["of"]
    assert "offsets (of) are missing for a weekly rule" in parse_rule(no_of).notes


def test_every_problem_is_listed():
    result = parse_rule(rule(rrv=9, fu=1, fa=0, tp=7))
    assert len(result.notes) == 4


# --- confidence -------------------------------------------------------------


@pytest.mark.parametrize(
    "of, confidence",
    [
        ([{"dy": 14}], "verified"),
        ([{"wd": 0, "wdo": -1}], "verified"),
        ([{"dy": -1}], "assumed"),
        ([{"wd": 0, "wdo": 1}], "assumed"),
        ([{"wd": 2, "wdo": 4}], "assumed"),
        ([{"dy": 3}, {"wd": 0, "wdo": -1}], "verified"),
    ],
)
def test_confidence(of, confidence):
    assert parse_rule(rule(fu=8, of=of)).confidence == confidence


def test_assumed_yearly_last_day():
    assert parse_rule(rule(fu=4, of=[{"dy": -1, "mo": 1}])).confidence == "assumed"


# --- suffix -----------------------------------------------------------------


def test_end_date_present_ordinary_and_missing():
    ordinary = parse_rule(rule(ed=1_800_000_000.0))
    assert ordinary.has_end_date
    assert ordinary.text == "Monthly on day 1 (has an end date)"
    never = parse_rule(rule(ed=NEVER))
    assert not never.has_end_date and never.text == "Monthly on day 1"
    at_threshold = parse_rule(rule(ed=6.0e10))
    assert not at_threshold.has_end_date
    missing = rule()
    del missing["ed"]
    assert not parse_rule(missing).has_end_date
    assert parse_rule(rule(ed=1_800_000_000)).has_end_date  # an int counts too


@pytest.mark.parametrize(
    "rc, expected",
    [
        (1, "Monthly on day 1 (ends after 1 time)"),
        (50, "Monthly on day 1 (ends after 50 times)"),
        (0, "Monthly on day 1"),
    ],
)
def test_repeat_limit(rc, expected):
    result = parse_rule(rule(rc=rc))
    assert result.text == expected
    assert result.repeat_limit == (rc or None)


@pytest.mark.parametrize(
    "ts, expected",
    [
        (-1, "Monthly on day 1 (starts 1 day before deadline)"),
        (-3, "Monthly on day 1 (starts 3 days before deadline)"),
        (0, "Monthly on day 1"),
    ],
)
def test_start_before_deadline(ts, expected):
    result = parse_rule(rule(ts=ts))
    assert result.text == expected
    assert result.start_days_before_deadline == (-ts or None)


def test_combined_suffix_in_order():
    result = parse_rule(
        rule(fu=8, fa=3, of=[{"dy": 0}], rc=3, ts=-3, ed=1_800_000_000.0)
    )
    assert result.text == (
        "Every 3 months on day 1 "
        "(ends after 3 times; has an end date; starts 3 days before deadline)"
    )
    assert result.text.count("(") == 1
    spec_example = parse_rule(rule(fu=8, fa=3, of=[{"dy": 0}], rc=3, ts=-3))
    assert spec_example.text == (
        "Every 3 months on day 1 (ends after 3 times; starts 3 days before deadline)"
    )


def test_suffix_applies_to_after_completion():
    result = parse_rule(rule(fu=4, tp=1, of=[{"dy": 0, "mo": 0}], rc=2))
    assert result.text == "1 year after completion (ends after 2 times)"


# --- unfamiliar fields and values --------------------------------------------


def test_unfamiliar_fields_are_noted_without_changing_the_text():
    result = parse_rule(rule(zz=1, aa="x"))
    assert result.text == "Monthly on day 1"
    assert result.recognised
    assert result.notes == ("unfamiliar field: aa", "unfamiliar field: zz")


def test_unfamiliar_field_on_unrecognised_rule_is_still_noted():
    result = parse_rule(rule(fu=999, zz=1))
    assert "unfamiliar field: zz" in result.notes


@pytest.mark.parametrize(
    "extra, note",
    [
        ({"rc": -1}, "unfamiliar value: rc=-1"),
        ({"rc": 2.5}, "unfamiliar value: rc=2.5"),
        ({"rc": "3"}, "unfamiliar value: rc='3'"),
        ({"rc": True}, "unfamiliar value: rc=True"),
        ({"ts": 2}, "unfamiliar value: ts=2"),
        ({"ts": -1.5}, "unfamiliar value: ts=-1.5"),
        ({"ts": None}, "unfamiliar value: ts=None"),
        ({"ed": "soon"}, "unfamiliar value: ed='soon'"),
    ],
)
def test_unfamiliar_values_add_a_note_only(extra, note):
    result = parse_rule(rule(**extra))
    assert result.text == "Monthly on day 1"
    assert result.recognised
    assert note in result.notes
    assert result.repeat_limit is None
    assert result.start_days_before_deadline is None
    assert not result.has_end_date


def test_non_calendar_yearly_date_is_noted():
    result = parse_rule(rule(fu=4, of=[{"dy": 30, "mo": 3}]))
    assert result.text == "Yearly on Apr 31"
    assert "unfamiliar value: Apr 31 is not a calendar date" in result.notes
    leap_day = parse_rule(rule(fu=4, of=[{"dy": 28, "mo": 1}]))
    assert leap_day.notes == ()


# --- unreadable input -------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    [
        b"",
        b"not a plist",
        b"bplist00",
        b"bplist00" + bytes(range(64)),
        b"<?xml version='1.0'?><plist>",  # truncated XML
        b"\x00" * 100,
        b"x" * (bf_limit + 1),  # oversized
        plistlib.dumps([1, 2, 3], fmt=plistlib.FMT_BINARY),  # not a dict
        plistlib.dumps("text", fmt=plistlib.FMT_BINARY),
        None,
        42,
        "fu=8",
        [rule()],
        object(),
    ],
)
def test_unreadable_input(value):
    result = assert_never_raises_and_is_well_formed(value)
    assert result.text == UNREADABLE_TEXT
    assert not result.recognised
    assert "_decode_error" in result.raw
    assert "_hex_prefix" in result.raw


def test_xml_plist_is_accepted():
    blob = plistlib.dumps(rule(), fmt=plistlib.FMT_XML)
    assert parse_rule(blob).text == "Monthly on day 1"


def test_xml_and_binary_give_identical_rules():
    for fmt_rule in (rule(), rule(fu=256, of=[{"wd": 0}], rc=3, ts=-2)):
        xml = parse_rule(plistlib.dumps(fmt_rule, fmt=plistlib.FMT_XML))
        binary = parse_rule(plistlib.dumps(fmt_rule, fmt=plistlib.FMT_BINARY))
        assert xml.recognised
        assert xml == binary
        for name in ("text", "unit", "interval", "confidence", "notes", "raw"):
            assert getattr(xml, name) == getattr(binary, name)


def test_fixture_uses_both_plist_formats():
    blobs = bf.rule_blobs(FIXED_TODAY)
    assert blobs["tpl_weekly_fri"].startswith(b"bplist00")
    assert blobs["tpl_weekly_sat"].startswith(b"<?xml")


def test_oversized_blob_is_rejected_with_a_note():
    blob = plistlib.dumps(rule(pad="x" * (bf_limit + 1)), fmt=plistlib.FMT_XML)
    result = assert_never_raises_and_is_well_formed(blob)
    assert not result.recognised
    assert "byte limit" in result.notes[0]


def test_blob_at_the_limit_is_still_read():
    blob = plistlib.dumps(rule(), fmt=plistlib.FMT_XML)
    padded = blob + b" " * (bf_limit - len(blob))
    assert len(padded) == bf_limit
    assert parse_rule(padded).text == "Monthly on day 1"


def test_bytes_like_inputs_are_accepted():
    blob = plistlib.dumps(rule(), fmt=plistlib.FMT_BINARY)
    for value in (blob, bytearray(blob), memoryview(blob)):
        assert parse_rule(value).text == "Monthly on day 1"


def test_rule_is_frozen_and_hashable():
    result = parse_rule(rule())
    with pytest.raises(AttributeError):
        result.text = "changed"
    assert hash(result) == hash(parse_rule(rule()))


# --- never raises -----------------------------------------------------------


class ExplodingMapping(Mapping):
    def __getitem__(self, key):
        raise RuntimeError("boom")

    def __iter__(self):
        raise RuntimeError("boom")

    def __len__(self):
        return 1


class BadRepr:
    def __repr__(self):
        raise RuntimeError("no repr")


HUGE = 10**5000  # str() of this raises ValueError on recent Pythons


def test_hostile_inputs():
    cyclic = rule()
    cyclic["of"] = [cyclic]
    nested = rule()
    deep = nested
    for _ in range(200):
        deep["x"] = {}
        deep = deep["x"]
    for value in (
        ExplodingMapping(),
        cyclic,
        nested,
        rule(fa=HUGE),
        rule(rc=HUGE, ts=-HUGE, ed=HUGE),
        rule(rrv=HUGE),
        rule(of=[{"dy": HUGE}]),
        rule(**{"zz": BadRepr()}),
        {BadRepr(): 1},
        {HUGE: 1},
        rule(ed=float("nan")),
        rule(ed=float("inf")),
        rule(ia=float("nan")),
    ):
        assert_never_raises_and_is_well_formed(value)


def test_nan_and_huge_values_do_not_count_as_end_dates():
    assert not parse_rule(rule(ed=float("nan"))).has_end_date
    assert parse_rule(rule(ed=float("nan"))).notes == ("unfamiliar value: ed=nan",)
    huge = parse_rule(rule(rc=HUGE))
    assert huge.repeat_limit is None
    assert any(note.startswith("unfamiliar value: rc=<integer") for note in huge.notes)


def _random_value(rng: random.Random, depth: int = 0):
    choices = [
        lambda: None,
        lambda: rng.choice([True, False]),
        lambda: rng.randint(-10, 300),
        lambda: rng.choice([HUGE, -HUGE, 2**63, -(2**64), 2**200]),
        lambda: rng.uniform(-1e12, 1e12),
        lambda: rng.choice([float("nan"), float("inf"), -float("inf"), 6.0e10]),
        lambda: "".join(rng.choice("abcé日 ") for _ in range(rng.randint(0, 8))),
        lambda: bytes(rng.getrandbits(8) for _ in range(rng.randint(0, 8))),
        lambda: dt.datetime(2026, 1, 1),
        lambda: BadRepr(),
    ]
    if depth < 3:
        choices += [
            lambda: [_random_value(rng, depth + 1) for _ in range(rng.randint(0, 3))],
            lambda: _random_dict(rng, depth + 1),
            lambda: [_random_offset(rng) for _ in range(rng.randint(0, 3))],
        ]
    return rng.choice(choices)()


def _random_offset(rng: random.Random):
    keys = rng.choice([("wd",), ("dy",), ("wd", "wdo"), ("dy", "mo"), ("x",), ()])
    return {
        key: rng.choice([rng.randint(-3, 32), _random_value(rng, 3)]) for key in keys
    }


def _random_dict(rng: random.Random, depth: int):
    keys = ["fu", "fa", "tp", "of", "ed", "ia", "rc", "rrv", "sr", "ts", "zz", 7]
    return {
        key: _random_value(rng, depth)
        for key in rng.sample(keys, rng.randint(0, len(keys)))
    }


def _mutated_rule(rng: random.Random):
    value = rule(
        fu=rng.choice([16, 256, 8, 4]),
        fa=rng.randint(1, 4),
        tp=rng.choice([0, 1]),
        of=[_random_offset(rng)],
        rc=rng.randint(-2, 60),
        ts=rng.randint(-30, 3),
    )
    key = rng.choice(list(value))
    if rng.random() < 0.5:
        value[key] = _random_value(rng)
    else:
        del value[key]
    return value


def _encodable(value):
    """Try to turn a random dict into a binary plist; plistlib rejects some values."""
    try:
        return plistlib.dumps(value, fmt=plistlib.FMT_BINARY)
    except Exception:
        return None


def test_fuzz_never_raises():
    rng = random.Random(20261010)
    inputs = []
    for _ in range(400):
        inputs.append(bytes(rng.getrandbits(8) for _ in range(rng.randint(0, 120))))
    for _ in range(200):
        tail = bytes(rng.getrandbits(8) for _ in range(rng.randint(0, 200)))
        inputs.append(b"bplist00" + tail)
    for _ in range(300):
        inputs.append(_random_dict(rng, 0))
    for _ in range(300):
        mutated = _mutated_rule(rng)
        inputs.append(mutated)
        encoded = _encodable(mutated)
        if encoded is not None:
            inputs.append(encoded)
            # flip a few bytes of a valid plist
            corrupted = bytearray(encoded)
            for _ in range(rng.randint(1, 4)):
                corrupted[rng.randrange(len(corrupted))] = rng.getrandbits(8)
            inputs.append(bytes(corrupted))
    for _ in range(100):
        inputs.append(_random_value(rng))

    assert len(inputs) >= 1000
    recognised = 0
    for value in inputs:
        recognised += assert_never_raises_and_is_well_formed(value).recognised
    assert recognised > 0  # the fuzz also reaches the describing code
