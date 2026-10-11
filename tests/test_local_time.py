"""Local time for `exported_at` and every date derived from it (DESIGN.md 7.4,
7.6). The timezone is pinned per test, never taken from the machine."""

import datetime as dt
import json

import pytest
from checks_helpers import edit, snapshot_of
from fixtures import build_fixture as bf

from tidyline import cli
from tidyline.llm.payload import build_payload

U = bf.make_uuid
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
EST = dt.timezone(dt.timedelta(hours=-5))
# 2026-10-01 20:00 UTC is 2 October in India; 2026-10-02 02:00 UTC is still
# 1 October at UTC-5. Each zone moves one of the two dates off its UTC date.
CREATED = dt.datetime(2026, 10, 1, 20, tzinfo=dt.timezone.utc)
MODIFIED = dt.datetime(2026, 10, 2, 2, tzinfo=dt.timezone.utc)
ZONES = [
    ("IST-5:30", "+05:30", ("2026-10-02", "2026-10-02")),
    ("EST+5", "-05:00", ("2026-10-01", "2026-10-01")),
    ("UTC0", "+00:00", ("2026-10-01", "2026-10-02")),
]


@pytest.fixture(autouse=True)
def no_real_app(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "THINGS_INFO_PLIST", tmp_path / "missing.plist")


def stamp_measure(path):
    edit(path, (
        "UPDATE TMTask SET creationDate = ?, userModificationDate = ? WHERE uuid = ?",
        (CREATED.timestamp(), MODIFIED.timestamp(), U("t_measure")),
    ))  # fmt: skip


def by_id(rows):
    return {row["id"]: row for row in rows}


@pytest.mark.parametrize(("zone", "offset", "dates"), ZONES)
def test_export_uses_local_time(fixture_db, tmp_path, pinned_timezone, zone, offset,
                                dates):  # fmt: skip
    pinned_timezone(zone)
    stamp_measure(fixture_db)
    out = tmp_path / "export.json"
    assert cli.main(["--db", str(fixture_db), "export", "--out", str(out)]) == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["exported_at"].endswith(offset)
    task = by_id(data["tasks"])[U("t_measure")]
    assert (task["created"], task["modified"]) == dates


@pytest.mark.parametrize(("zone", "offset", "dates"), ZONES)
def test_prompt_payload_uses_local_time(fixture_db, tmp_path, pinned_timezone,
                                        zone, offset, dates):  # fmt: skip
    pinned_timezone(zone)
    stamp_measure(fixture_db)
    out = tmp_path / "prompt"
    assert cli.main(["--db", str(fixture_db), "prompt", "--out", str(out)]) == 0
    data = json.loads((out / "tidyline_payload.json").read_text(encoding="utf-8"))
    assert data["exported_at"].endswith(offset)
    task = by_id(data["tasks"])[U("t_measure")]
    assert (task["created"], task["modified"]) == dates


def completed_counts(path, stopped, exported_at):
    edit(path, (
        "UPDATE TMTask SET stopDate = ? WHERE uuid = ?",
        (stopped.timestamp(), U("t_done")),
    ))  # fmt: skip
    payload = build_payload(
        snapshot_of(path),
        today=exported_at.date(),
        exported_at=exported_at,
        level="light",
    )
    return payload["summary"]["completed_todos"]["last_14_days"]


def test_completed_window_uses_the_local_date_ahead_of_utc(fixture_db):
    # 00:30 on 10 October in India is still 9 October in UTC. The local window
    # starts on 27 September; the stop falls on 26 September locally (23:30),
    # so it is out, though its UTC date is inside a UTC-based window.
    exported_at = dt.datetime(2026, 10, 10, 0, 30, tzinfo=IST)
    inside_utc_only = dt.datetime(2026, 9, 26, 18, tzinfo=dt.timezone.utc)
    base = completed_counts(fixture_db, exported_at - dt.timedelta(days=60),
                            exported_at)  # fmt: skip
    assert completed_counts(fixture_db, inside_utc_only, exported_at) == base


def test_completed_window_uses_the_local_date_behind_utc(fixture_db):
    # 20:00 on 10 October at UTC-5 is 11 October in UTC. The local window
    # starts on 27 September; a stop at 18:00 local that day (23:00 UTC) is
    # in, though a UTC-based window would start on 28 September.
    exported_at = dt.datetime(2026, 10, 10, 20, tzinfo=EST)
    inside_local_only = dt.datetime(2026, 9, 27, 18, tzinfo=EST)
    base = completed_counts(fixture_db, exported_at - dt.timedelta(days=60),
                            exported_at)  # fmt: skip
    assert completed_counts(fixture_db, inside_local_only, exported_at) == base + 1
