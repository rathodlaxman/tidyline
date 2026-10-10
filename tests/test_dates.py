import datetime as dt
import random

import pytest

from tidyline import dates


def test_pack_matches_the_thing_py_formula():
    assert dates.pack_date(dt.date(2026, 10, 10)) == (2026 << 16 | 10 << 12 | 10 << 7)


def test_unpack_known_values():
    assert dates.unpack_date(2026 << 16 | 10 << 12 | 10 << 7) == dt.date(2026, 10, 10)
    assert dates.unpack_date(2024 << 16 | 2 << 12 | 29 << 7) == dt.date(2024, 2, 29)
    assert dates.unpack_date(2026 << 16 | 1 << 12 | 1 << 7) == dt.date(2026, 1, 1)


def test_null_is_none():
    assert dates.unpack_date(None) is None
    assert dates.to_datetime(None) is None


def test_round_trip_every_day_for_ten_years():
    day = dt.date(2020, 1, 1)
    for _ in range(3653):
        assert dates.unpack_date(dates.pack_date(day)) == day
        day += dt.timedelta(days=1)


def test_round_trip_random_dates():
    rng = random.Random(20261010)
    for _ in range(2000):
        ordinal = rng.randint(dt.date.min.toordinal(), dt.date.max.toordinal())
        day = dt.date.fromordinal(ordinal)
        assert dates.unpack_date(dates.pack_date(day)) == day


def test_round_trip_random_packed_values_that_are_valid():
    rng = random.Random(7)
    for _ in range(2000):
        packed = (
            rng.randint(1, 9999) << 16
            | rng.randint(0, 15) << 12
            | rng.randint(0, 31) << 7
        )
        day = dates.unpack_date(packed)
        if day is not None:
            assert dates.pack_date(day) == packed


@pytest.mark.parametrize(
    "value",
    [
        2026 << 16 | 13 << 12 | 1 << 7,  # month 13
        2026 << 16 | 0 << 12 | 1 << 7,  # month 0
        2026 << 16 | 2 << 12 | 30 << 7,  # Feb 30
        2025 << 16 | 2 << 12 | 29 << 7,  # Feb 29 in a common year
        2026 << 16 | 4 << 12 | 31 << 7,  # Apr 31
        2026 << 16 | 1 << 12 | 0 << 7,  # day 0
        0 << 16 | 1 << 12 | 1 << 7,  # year 0
        10000 << 16 | 1 << 12 | 1 << 7,  # year 10000
        0,
        -1,
        -(2026 << 16 | 10 << 12 | 10 << 7),
        (2026 << 16 | 10 << 12 | 10 << 7) | 1,  # stray low bit
        2**80,
        True,
        False,
        float("nan"),
        float("inf"),
        1.5,
        "132788096",
        b"x",
        [1],
    ],
)
def test_invalid_packed_dates_are_none(value):
    assert dates.unpack_date(value) is None


def test_integral_float_is_accepted():
    packed = dates.pack_date(dt.date(2026, 10, 10))
    assert dates.unpack_date(float(packed)) == dt.date(2026, 10, 10)


def test_timestamp_converts_to_aware_utc():
    result = dates.to_datetime(1_760_000_000.5)
    assert result == dt.datetime(2025, 10, 9, 8, 53, 20, 500000, tzinfo=dt.timezone.utc)
    assert result.utcoffset() == dt.timedelta(0)


def test_integer_and_zero_and_negative_timestamps():
    assert dates.to_datetime(0) == dates.EPOCH
    assert dates.to_datetime(86400) == dt.datetime(1970, 1, 2, tzinfo=dt.timezone.utc)
    assert dates.to_datetime(-86400).year == 1969


@pytest.mark.parametrize(
    "value",
    [float("nan"), float("inf"), -float("inf"), 1e18, -1e18, 10**30, True, "1", b"1"],
)
def test_invalid_timestamps_are_none(value):
    assert dates.to_datetime(value) is None
