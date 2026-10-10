"""Convert the date encodings Things uses (DESIGN.md section 5).

Pure functions. Nothing here reads the clock, and nothing raises on bad input:
a value that is not a valid date or timestamp gives None.
"""

from __future__ import annotations

import datetime as dt
import math

EPOCH = dt.datetime(1970, 1, 1, tzinfo=dt.timezone.utc)

_DAY_MASK = 0b11111
_MONTH_MASK = 0b1111


def _as_int(value: object) -> int | None:
    """An int, or a float with no fractional part; anything else is None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and math.isfinite(value) and value.is_integer():
        return int(value)
    return None


def unpack_date(value: object) -> dt.date | None:
    """Unpack `year << 16 | month << 12 | day << 7` into a date.

    NULL gives None. So does anything that is not a valid calendar date, such
    as month 13, Feb 30, year 0, a negative number, or a value with stray low
    bits set (real values always have them clear). Callers that must tell NULL
    from invalid should test for NULL first.
    """
    packed = _as_int(value)
    if packed is None or packed < 0:
        return None
    if packed & 0b1111111:  # bits below the day field
        return None
    year = packed >> 16
    month = (packed >> 12) & _MONTH_MASK
    day = (packed >> 7) & _DAY_MASK
    try:
        return dt.date(year, month, day)
    except (ValueError, OverflowError):  # year 0 or huge, month 0 or 13+, day 0
        return None


def pack_date(day: dt.date) -> int:
    """Pack a date the way Things stores it."""
    return day.year << 16 | day.month << 12 | day.day << 7


def to_datetime(value: object) -> dt.datetime | None:
    """Convert a Unix timestamp in seconds (a REAL column) to an aware UTC datetime.

    NULL gives None. So do NaN, infinity, booleans, strings and values outside
    the range a datetime can hold.
    """
    if value is None or isinstance(value, bool):
        return None
    if not isinstance(value, (int, float)):
        return None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    try:
        return EPOCH + dt.timedelta(seconds=value)
    except (OverflowError, ValueError):
        return None
