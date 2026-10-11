# Compatibility

What tidyline has been tested with, and how. Anything not listed here has not
been tested.

## Tested environment

| Item | Value |
|---|---|
| Things | 3.24.1 |
| Database version | 29 |
| macOS | 27.0.1 |
| Hardware | Apple silicon (M1) |
| Real databases | One: the maintainer's own, on the maintainer's own Mac |

## Automated tests

| Item | Value |
|---|---|
| CI | macOS (`macos-latest`) |
| Python | 3.10 and 3.13 |
| Data | A synthetic fixture only |
| Network | Sockets blocked |

## Checked on the real database

These checks were run by hand by the maintainer. They are not part of the
automated tests, and no real data is stored in the repository.

- All 36 repeating templates were recognised. The counts matched the
  maintainer's earlier script.
- Three recurrence patterns were compared by hand with what Things shows, and
  they matched:
  - "1 year after completion"
  - "every 2 weeks on a weekday"
  - "every 3 months on the last weekday of that name"
- The anonymised exports were checked for leaks. A decode round trip also
  worked: 2,057 labels were decoded correctly.
- tidyline 0.2.0 was installed from PyPI with `uv tool install tidyline`, and
  `tidyline doctor` reported schema ok, database version 29, tested yes, on the
  maintainer's Mac.

## Not checked

- A day offset of -1 in a monthly rule (read as the last day of the month).
- Weekday ordinals other than "last" (read as first to fourth).
- Whether a deadline lead time of 0 can mean a deadline on the same day.
- Rule 5 for deadlines (an overdue deadline with no start date counts as
  Today) on real data.
- Dated tasks inside Someday projects on real data.
- Whether macOS shows a privacy prompt when a terminal reads Things' data
  folder.
- Other versions of Things or macOS.
- Other people's databases.

tidyline warns when it runs against a version it has not been tested with.

## The prompt and decode flow

The prompt and decode flow has been tried once each with two AI assistants on one real database. Answers differ between assistants and between runs and can contain mistakes. Check the numbers against `tidyline report` and check any change before making it in Things.

## Reporting a mismatch

If a rule is described wrongly, or marked as not recognised:

1. Run `tidyline recurrence --raw`. It shows each rule as stored and the fields
   tidyline read from it.
2. Check the raw text before you paste it anywhere. It may contain personal
   data. Remove anything you do not want to share.
3. In your report, include the Things version and the macOS version. `tidyline
   doctor` shows both.
4. Say what the Repeat dialog in Things shows for that task, in your own words,
   without the task title.

See [RECURRENCE.md](RECURRENCE.md) for how rules are read.
