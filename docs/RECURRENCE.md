# Recurrence rules

How tidyline reads the repeat settings of Things 3 to-dos, what has been checked against a real database, and what is still an assumption. The code is `src/tidyline/recurrence.py`; the design is in `DESIGN.md` section 7.2.

This file contains no personal data. "Verified" means the convention was checked against a real Things database and, where noted, against what the Things app shows in its Repeat dialog.

## Where rules live

A repeating to-do has a hidden **template** row in `TMTask` with `rt1_recurrenceRule` set. The rule is a binary property list (plist) holding one dictionary. The to-dos you see are **instances**; each points to its template through `rt1_repeatingTemplate`. Templates do not always have an open instance, so tidyline builds its list from templates.

## Fields

| Field | Type | Meaning | Status |
|---|---|---|---|
| `fu` | int | Unit: 16 day, 256 week, 8 month, 4 year | Verified |
| `fa` | int | Interval: every N units | Verified |
| `tp` | int | 0 fixed schedule, 1 repeat after completion | Verified |
| `of` | list of dicts | Offsets: which weekday, day or month (see below) | Verified, except where noted |
| `rrv` | int | Rule format version. Only 4 has been seen; tidyline describes version 4 only | Verified (value 4) |
| `rc` | int | Repeat limit: "Ends after N times". 0 means no limit | Verified in the Repeat dialog |
| `ts` | int | Deadline lead time: -3 means "Add deadlines and start 3 days earlier" | Verified in the Repeat dialog for a negative value |
| `ed` | float | End. Values at or above 6.0e10 look like "never ends"; an ordinary value looks like an end date; missing means no end date | Partly assumed |
| `ia` | float | Not interpreted. Kept in the raw rule | Unknown |
| `sr` | float | Not interpreted. Kept in the raw rule | Unknown |

Any other top-level field is listed as `unfamiliar field: <name>` and does not change the description.

### Offsets (`of`)

| Unit | Shape | Meaning | Status |
|---|---|---|---|
| day | anything | Ignored | Verified (`[{dy: 0}]` seen) |
| week | `{wd}` | Weekday, 0 Sunday to 6 Saturday | Verified |
| month | `{dy}` | Day of the month, from zero: `dy` 14 is day 15 | Verified |
| month | `{dy: -1}` | Last day of the month | **Assumed**: never seen |
| month | `{wd, wdo}` | Ordinal weekday: `wdo` -1 is the last one | Verified for -1 |
| month | `{wd, wdo}` with `wdo` 1 to 4 | First to fourth weekday | **Assumed**: only checked for -1 |
| year | `{dy, mo}` | Day and month, both from zero: `mo` 2, `dy` 9 is Mar 10 | Verified |

For repeat-after-completion rules (`tp` 1), Things shows only the interval and unit ("Repeat 1 year after the previous to-do has been completed"). Real rules of this kind still carry offsets; tidyline ignores them in the text and keeps them in the raw rule.

## Descriptions

| Rule | Text |
|---|---|
| Daily, every N days | `Daily`, `Every 3 days` |
| Weekly | `Weekly on Sun`, `Every 2 weeks on Sun`, `Weekly on Mon, Fri, Sat` |
| Monthly on a day | `Monthly on day 15`, `Every 3 months on day 1`, `Monthly on last day` |
| Monthly on a weekday | `Monthly on the last Sun`, `Every 3 months on the first Sun` |
| Yearly | `Yearly on Feb 28`, `Every 2 years on Feb 28` |
| After completion | `1 year after completion`, `3 weeks after completion` |

One parenthetical is added when any of these apply, in this order: `ends after N times` (`rc` above 0), `has an end date` (`ed` below 6.0e10; the date is not converted), `starts N days before deadline` (`ts` below 0). Example: `Every 3 months on day 1 (ends after 3 times; starts 3 days before deadline)`.

A rule that cannot be read gives `recurring (rule unreadable)`. A rule whose fields tidyline does not understand gives `recurring (rule not recognised)`, with the reasons in the notes. The raw rule is always kept in the export.

Each rule has a **confidence**:

- `verified`: every convention the description relies on was checked on a real database.
- `assumed`: the description relies on `dy` -1 or on a `wdo` other than -1.
- `unrecognised`: the rule was not described.

## Known unknowns

- **`ts` 0.** It appeared where "Add deadlines" was unticked, but "Add deadlines" with 0 days earlier may also be stored as 0. tidyline treats 0 as "no lead time" and says nothing.
- **Ordinary `ed` values.** One has been seen. It is not yet confirmed that it matches "Ends on date" in the dialog, and its unit is unknown, so tidyline says only `has an end date`.
- **`dy` -1.** Read as the last day of the month. Never seen in a real rule.
- **`wdo` 1 to 4.** Read as first to fourth. Only -1 (last) has been checked against the app.
- **Positive `ts`, negative `rc`.** Never seen. Noted as `unfamiliar value`, and the text is unchanged.
- **`ia` and `sr`.** Not interpreted.

## Reporting an unfamiliar rule

If tidyline shows `recurring (rule not recognised)`, an `unfamiliar field`, an `unfamiliar value` or `assumed`, a report helps. You can send one without sharing any task titles or notes.

1. Run this from a checkout of tidyline (`uv run python report_rules.py`). It reads a private snapshot copy, selects only the rule column, and prints nothing from titles or notes:

   ```python
   import sqlite3

   from tidyline.db.locate import locate_database
   from tidyline.db.snapshot import open_snapshot
   from tidyline.recurrence import parse_rule

   with open_snapshot(locate_database()) as copy:
       conn = sqlite3.connect(copy)
       rows = conn.execute(
           "SELECT rt1_recurrenceRule FROM TMTask "
           "WHERE rt1_recurrenceRule IS NOT NULL AND trashed = 0"
       ).fetchall()
       conn.close()

   for (blob,) in rows:
       rule = parse_rule(blob)
       if not rule.recognised or rule.notes or rule.confidence != "verified":
           print(rule.text, rule.confidence, list(rule.notes), rule.raw)
   ```

2. Before sending, you may replace the values of `ia`, `sr` and `ed` with 0. They may be timestamps, so they can reveal when you created or scheduled a task, and tidyline does not need them to understand the rule's shape.
3. In Things, open the same to-do's Repeat dialog and write down, in your own words, what it shows (for example "Monthly, on the second Wednesday, ends after 5 times"). Leave out the to-do's title.
4. Open an issue with the printed line, the dialog description, your Things version and your macOS version (`tidyline doctor` shows both).
