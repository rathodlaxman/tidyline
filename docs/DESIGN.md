# tidyline: Design

Status: agreed plan, 10 October 2026. Covers v0.1 to v0.4.
This file is safe to publish: it contains no personal task data.

## 1. Purpose

tidyline is an offline, read-only command-line tool that audits a Things 3 database on macOS. It produces:

- a health report (text now, HTML from v0.3)
- a full, versioned JSON export
- an anonymised, LLM-ready export with an audit prompt

Things 3 is made by Cultured Code. tidyline is unofficial and not affiliated with them.

Similar tools already exist (things.py, things-cli, several Things MCP servers). tidyline differs by focusing on the audit: health checks, readable recurrence, an anonymised export for LLM review, and an HTML report.

## 2. Standing rules

| Rule | Consequence in code |
|---|---|
| Read-only | Never write to the database. Never call things.py functions that act on the app (`complete`, `show`, `url`, `token`). Never read or export the URL-scheme auth token. |
| Things may stay open | Read a consistent snapshot copy, never the live file directly (section 6). |
| Offline | Nothing outside `tidyline.llm.ollama` and `tidyline.llm.cloud` may open a network connection. Tests enforce this with sockets blocked. |
| Honest about the schema | Check required tables and columns first. Fail with a clear message that names the tested versions. Unknown recurrence rules are reported as unknown, never guessed. |
| No personal data in the repo | Tests and screenshots use a synthetic fixture database only. |
| LLM use is opt-in | Three levels. Anonymised by default. Always show what will be sent before anything is sent. |

## 3. Decisions log

| Date | Decision |
|---|---|
| 2026-10-10 | Name: **tidyline** (PyPI, Homebrew core and GitHub checked; free). |
| 2026-10-10 | Keep **things.py** (1.0.1, Apache 2.0) for areas, projects, tasks and dates, pointed at the snapshot copy. Raw SQL only for recurrence, This Evening and the schema check, all inside `read.py` so it can be replaced later. |
| 2026-10-10 | Minimum Python **3.10**. CI tests 3.10 to 3.13. Development uses `uv`. |
| 2026-10-10 | Anonymisation default depends on level: local Ollama `light`, cloud API `strict`. Always overridable, always previewed. |
| 2026-10-10 | HTML report: single offline file, follows system light/dark, native `<details>` for folding, one small optional inline script for search/filter, print stylesheet. No CDN, no web fonts. |
| 2026-10-10 | Repo starts private and goes public when v0.1 works. |
| 2026-10-10 | Runtime dependencies: **things.py only** through v0.2. CLI built on the standard library `argparse`. HTML templating decided at v0.3. |
| 2026-10-10 | Default anonymisation for `prompt` (level 0): **strict**. `--anonymise light` is available for a fuller audit. |
| 2026-10-10 | `read.py` is a **hybrid**: things.py (trashed=None, status=None) supplies identity and structure of to-dos, projects, headings, areas and tags. One read-only SQL pass over the same snapshot supplies what things.py lacks: packed dates, suppression date, raw timestamps, `startBucket`, `rt1_*`, tag UUIDs, checklist items, template rows, ordering. Rows are matched by UUID. If the two sources disagree, a warning is recorded and the row is skipped. Verified on the maintainer's database: 0 warnings. |
| 2026-10-10 | v0.2 choices: title-hygiene patterns come from a repeatable `--pattern REGEX` option on `check` (no config file, no new dependency); new warning check "open to-dos inside a trashed project", with those to-dos excluded from all other checks; `strict` anonymisation labels are derived from the id alone (kind plus a short hash code, for example `Task k3f7az`), so a label never changes when other items are added, removed or reordered. (Corrected 2026-10-10: numbering by sorted id was first chosen but shifts whenever an item is added.) |
| 2026-10-10 | Exit codes: runtime failures (database not found or unreadable, output not writable) exit 3 on every command and an unusable `--out` path found up front exits 2, so `check` can use 1 for "warnings found". `check` accepts `--db` after the command like `doctor`, `export` and `report`. Finding messages never contain titles or user pattern text. Duplicate normalisation replaces punctuation with a space instead of deleting it. |
| 2026-10-10 | `prompt` and `decode` (settled 2026-10-10): `prompt` always prints a preview (level, counts, what is removed, the context text if given) and writes `tidyline_payload.json` and `tidyline_prompt.md` into `--out DIR`; `--copy` puts the prompt text on the clipboard (macOS `pbcopy`, no dependency); with neither option nothing is written. `--context FILE` fills the three context fields of the template; the area list is filled from the anonymised area labels; unfilled placeholders stay visible and the preview warns. Only the anonymised payload and the filled template leave the tool; the text report is never included because it lists recurring task titles. The packaged template (`llm/audit_prompt.md`) is adapted from the maintainer's own template: one attached payload file, a short data note, and a level-dependent Part 5. At `strict` titles are hidden, so Part 5 (task wording) is replaced by an instruction to skip it; `light` keeps scrubbed titles and supports Part 5. New command `decode` maps labels back to titles using the current database, possible because labels derive from ids. |
| 2026-10-10 | JSON export 7.4 open points settled: all rows included with flags (open, completed, cancelled, trashed); coded fields written as a name plus the raw code (`status` and `status_code`, `start` and `start_code`); `completion_date` is `stopDate` as ISO 8601 with UTC offset for completed and cancelled alike; areas, projects and headings use the same shape as tasks. Export file is created with mode 0600, an existing path is never overwritten, and `light` and `strict` are refused until v0.2. |
| 2026-10-11 | v0.2 release: the author shown on PyPI is the name only, with no email. Releases are uploaded by hand with `uv publish` using a project-scoped token. TestPyPI is used first. |
| 2026-10-11 | `export_schema_version` 1.1 (additive): projects, headings and to-dos gain `created` and `modified` (`creationDate` and `userModificationDate` as ISO dates in the timezone of `exported_at`, null when absent); the export gains `checks_run`, one `{check, severity, findings}` entry per check in registry order, including checks with 0 findings. |
| 2026-10-11 | The raw recurrence timestamps `ed`, `ia` and `sr` are withheld (null) at `strict`; `light` keeps them. `recurrence.text` is unchanged at every level. |
| 2026-10-11 | The `prompt` payload is no longer the anonymised export. It holds open work only, plus a precomputed `summary` and `checks_run` (section 7.6), so the assistant does not count rows itself. Completed, cancelled and trashed to-dos, and completed or trashed projects that hold no open to-dos, are counted in the summary only. It is anonymised by the same rules and labels as the export, so `decode` still works. |
| 2026-10-11 | In the `prompt` payload, the export's `warnings` are renamed `data_read_warnings`, so they are not read as problems with the user's system. |
| 2026-10-11 | `exported_at` and all derived dates use local time with offset (was UTC in export). `export` and `prompt` follow one rule: `exported_at` is a local ISO 8601 timestamp with its UTC offset, "today" is its date, and every `created` and `modified` date and every completed-to-do window uses that local date. Part of `export_schema_version` 1.1 (not released before this change). |
| 2026-10-11 | `decode` readability (replaces "titles go in exactly as stored"): bare codes are replaced when they match exactly one label, ambiguous ones are left and counted; titles are whitespace-collapsed and cut to 80 characters; `|` is escaped on table lines; titles are wrapped in double quotes unless already quoted; titles shared by items in the payload's scope get `(in Parent)` inside the quotes. All in one pass over the original text. Rules in 7.5. |
| 2026-10-11 | `report` shows recurring-template counts only (live, leftover, recognised, assumed, and not recognised when any; "assumed" counts rules that rest on an unverified convention); titles are shown by `tidyline recurrence`. No other part of `report` prints a task, project, heading or area title. |
| 2026-10-11 | Two user guides are part of the docs: `GETTING_STARTED.md` and `FIXING_PROBLEMS.md`. The README links both with absolute GitHub URLs (PyPI does not resolve relative links), and `tidyline check` (text output only, not `--json`) ends with one line linking the fixing guide. Things 3 steps in the guides are marked [checked] (read on a Cultured Code help page) or [not verified]. |
| 2026-10-11 | Output folders (changes the 2026-10-10 exit-code row, where a missing `--out` folder was exit 2): tidyline creates the last level of an `--out` folder when it is missing. Only that one level, never a chain; only when the parent exists and is a folder, else exit 2 with a message that says what is wrong and what to do; created with mode 0700 (`prompt`: the `--out` folder itself; `report`, `export` and `decode`: the folder of the file); an existing folder is never changed, and a warning goes to stderr when group or others can read it; one line "Created folder PATH (readable only by you)." goes to stderr when a folder is made. The folder is made just before writing, not before the database is read, and is removed again if the write fails. `--out` stays required for `export` and has no default location anywhere. Existing files are still never overwritten (exit 2). |
| 2026-10-11 | `tidyline` with no arguments prints a help screen (title with version, commands in plain words, examples, which commands show task titles, a first-time hint, and a link to `GETTING_STARTED.md`) and exits 0. No new command; `--help` is argparse's output as before. The text is in `render/help_out.py`. |
| 2026-10-11 | Styling (`render/style.py`): `bold`, `notice` (bold yellow) and `danger` (bold red), using only the 16 standard ANSI colours so the terminal theme decides the shades. Applied only when the target stream is a terminal and `NO_COLOR` is not set; stdout and stderr are judged separately. Used for: the `error:` prefix (red; the message stays plain); `warning:` labels (yellow); privacy notes on stderr (blank line before and after, the label yellow and the sentence "Keep it private and do not commit or share it." red); in the help screen only the "New here?" line and "Step-by-step guide:"; in the `prompt` preview the section labels, "warning:" and the closing "Nothing has been sent anywhere" line; in `check` the heading per check and the link line; in `report` the section headings (off with `--no-color`). Nothing else is styled. |
| 2026-10-11 | The text output of `check` changes layout only (replaces the first version of this row): a total line, then a heading per check (`id (severity, N findings)`), then the items grouped under their place with a count: a trashed project or heading (`open_in_trashed_project`), the project (`dated_in_someday_project`, `someday_in_active_project`, `outside_heading`), the project or area, or "No project or area" (`title_hygiene`), the area or "No area" (`active_project_no_open_tasks`). A message that is the same for every finding is printed once under the heading; a message that differs follows its item after a dash. `possible_duplicates` is one line per set of matching titles joined by `=`; templates are one line each. `unfiled_open` has one place by definition, so it is one list under its message. `check --json`, finding ids, messages, counts and exit codes are unchanged. |
| 2026-10-11 | A reader of standard output that closes early (`| head`) ends the run quietly with exit 0: `main` catches `BrokenPipeError` and points stdout at devnull, as the Python documentation recipe does. Files are written whole before anything is printed about them, so no partial file is left. |

## 4. Tested environment

| Item | Value |
|---|---|
| macOS | 27.0.1 |
| Hardware | Apple Silicon (M1) |
| Things | 3.24.1 |
| Database version (`Meta.databaseVersion`) | 29 |

The value of `databaseVersion` is stored as an XML plist, not a plain number. things.py decodes it with `plistlib` and refuses versions of 21 or below.

Recurrence offset conventions (section 7) were verified against this one database only.

## 5. Facts about things.py 1.0.1 that the design relies on

- Every API function accepts `filepath=`. The `THINGSDB` environment variable does the same.
- It opens the file with `mode=ro`.
- `today()` predicts what Today will show if the app is opened now. It combines three groups:
  - tasks with `start` set to Anytime and a start date
  - tasks with `start` set to Someday and a start date in the past
  - tasks with no start date and an overdue deadline (unless the deadline is suppressed)
- Dates are stored as packed integers: `year << 16 | month << 12 | day << 7`.
- It does not expose This Evening. That needs raw SQL (believed to be the `startBucket` column; to be verified in v0.1).
- `complete()` and `show()` send `things:///` URLs to the app. tidyline must never call them.
- Importing things.py runs a glob over `~/Library/Group Containers/...` at import time to find a default path. It opens no database, but it does list another app's container, which may trigger the macOS privacy prompt. Rules: import things.py lazily (inside `read.py`, after the snapshot exists), never use its default path, always pass `filepath=`. `--version`, `--help` and the permission-error handling in `doctor` must work without importing it.
- `today()` and `upcoming()` ignore the parent project's status. A task with a past start date inside a Someday project appears in `today()`, but the app keeps it hidden. They also read the real clock inside SQL. Rule: tidyline never calls `today()` or `upcoming()`. `status.py` computes effective status itself from raw fields, with `today` passed in as an argument.

## 6. Reading the database safely

1. Locate the database: `--db` option, then the `THINGSDB` variable, then the standard `ThingsData-*` path.
2. Open the source with `mode=ro` and copy it with the SQLite backup API into a private temporary directory (`tempfile.TemporaryDirectory`, permissions 0700).
   - The backup API copies a consistent snapshot, including changes still in the write-ahead log.
   - If the database is busy, retry up to three times with a short wait, then fail with a clear message.
3. Run the schema check against the copy.
4. Point things.py and the raw SQL at the copy. Delete the copy on exit, including on error.
5. Record the Things app version (from the app's `Info.plist`), the database version, the macOS version and the CPU architecture.

Risk to verify early: on recent macOS versions, reading another app's Group Container from Terminal may trigger an "access data from other apps" prompt or need Full Disk Access. `doctor` must detect a permission error and explain what to do.

## 7. Behaviour specification

### 7.1 Effective status

Resolved in this order. "Today" means the local date at run time.

1. `start` is Inbox: **Inbox**
2. The parent project is Someday: **Someday** (everything inside a Someday project is parked)
3. Has a start date later than today: **Upcoming**
4. Has a start date of today or earlier: **This Evening** if `startBucket` = 1, otherwise **Today**
5. No start date, deadline today or earlier, deadline not suppressed: **Today**
6. `start` is Someday: **Someday**
7. Otherwise: **Anytime**

This fixes the earlier personal script, which labelled every dated task Upcoming, including tasks in Today.

Checked against the maintainer's database on 2026-10-10 (counts only):
- Rule 4 holds. All 12 open dated tasks with a start date of today or earlier have `start` = 1 (Anytime). Things stores Today tasks this way.
- Rule 3 holds. All 8 open tasks with `start` = 2 and a start date have future dates.
- This Evening: one throwaway task set to This Evening in the app showed `start` = 1, `startBucket` = 1 and a start date of today. All other open tasks had `startBucket` = 0. Not yet seen: an evening task with a past date, or one inside a Someday project.
- Rule 5 is untested on real data: the database had no open task with an overdue deadline and no start date. It comes from things.py's prediction logic and is covered only by the fixture.

### 7.2 Recurrence

Templates are hidden rows with `rt1_recurrenceRule` (a property list; the real database stores it in the **XML** plist format, not binary. Verified 2026-10-10: a decoder that accepted only binary plists read none of 40 real rules). The decoder accepts both XML and binary plists. Each visible instance points to its template through `rt1_repeatingTemplate`.

| Field | Meaning |
|---|---|
| `fu` | Unit: 16 day, 256 week, 8 month, 4 year |
| `fa` | Interval (every N units) |
| `tp` | 0 fixed schedule, 1 repeats after completion |
| `of` | Offsets: `wd` weekday (0 Sunday to 6 Saturday), `dy` day of month (from zero; -1 is the last day), `mo` month (from zero) |

Output examples: `Daily`, `Weekly on Sun`, `Every 2 weeks on Sun`, `Monthly on day 15`, `Every 3 months on day 1`, `Monthly on last day`, `Every 3 months on the last Sun`, `Yearly on Mar 10`, `1 year after completion`, `3 weeks after completion`.

Repeat-after-completion rules (`tp` = 1) are described only by interval and unit, because Things shows only "Repeat 1 year after the previous to-do has been completed". Real rules of this kind still carry `of` values (for a yearly one, a day and a month); those are ignored in the description and kept in the raw rule.

- A rule is described only when the fields that tidyline interprets are understood: `fu` is a known unit, and the `of` entries use known key sets. Otherwise the output is `recurring (rule not recognised)`. The raw rule is always kept in the export.
- Observed on a real database (40 rules): every rule also carries `ia` (float), `rc` (int), `rrv` (int), `sr` (float), `ts` (int) and, in 36 of 40, `ed` (float). None of these makes a rule "not recognised"; all stay in the raw rule. Any other top-level key is listed as an unfamiliar field, without changing the description.
- `rrv` was 4 in all 40 rules. tidyline understands rule version 4 only; any other value gives `recurring (rule not recognised)`.
- `ed`: 35 of 36 present values are far in the future (at or above 6.0e10), which looks like "never ends". One rule has an ordinary value, which looks like an end date. A rule with an ordinary `ed` is described with `(has an end date)`; the date is not converted. A missing `ed` means no end date.
- `rc` is the repeat limit. Verified on two rules from the app's Edit Repeat dialog: `rc` 50 shows "Ends after 50 times" and `rc` 3 shows "Ends after 3 times". `rc` 0 means no limit. It was non-zero in 4 of 40 rules (values 3, 12, 28, 50).
- `ts` is the deadline lead time. Verified on one rule: `ts` -3 shows "Add deadlines and start 3 days earlier" (each instance gets a deadline on its scheduled date and starts 3 days before). It was negative in 9 of 40 rules (-2, -3, -7, -14, -22, -27). A positive `ts` has not been seen. `ts` 0 is ambiguous: it was seen where the dialog had "Add deadlines" unticked, but "Add deadlines" with 0 days earlier may also be stored as 0.
- Description suffix, one parenthetical with parts in this order: `ends after N times` (rc > 0), `has an end date` (ordinary ed), `starts N days before deadline` (ts < 0). Example: `Every 3 months on day 1 (ends after 3 times; starts 3 days before deadline)`. A non-integer `rc` or `ts`, a negative `rc` or a positive `ts` becomes a note and does not change the text.
- Observed `of` shapes by unit:
  - day: `[{dy: 0}]` (7 of 7 rules). Ignored.
  - week: `[{wd}]`, with wd 0, 5 and 6 seen.
  - month: `[{dy}]` (dy 0, 4, 5, 13, 14 seen) or ordinal weekday `[{wd, wdo}]` (2 rules, both wd 0; wdo 1 and -1 seen). `dy` = -1 (last day) was not seen in this database.
  - year: `[{dy, mo}]`.
- Checked against what Things shows for real tasks (2026-10-10): weekly on Sunday = `wd` 0; day 15 = `dy` 14; day 6 = `dy` 5; day 1 = `dy` 0; March 10 = `mo` 2, `dy` 9; January 28 reported for a yearly rule; "every 3 months on the last Sunday" = `wd` 0, `wdo` -1, fa 3.
- Not verified: `wdo` 1 to 4 as first to fourth (only -1 was confirmed; the other ordinal rule in the database is in the trash), and `dy` -1 as the last day of the month.
- Each parsed rule carries a `confidence`: `verified` when every convention it uses was seen on a real database, `assumed` when it uses `dy` -1 or a `wdo` other than -1, and `unrecognised` otherwise.
- Templates whose project is in the trash are listed as **leftovers**, not as live recurring tasks.
- Templates under a heading report the heading's project.
- A template is a row with `rt1_recurrenceRule` set and `trashed = 0` (as in the earlier personal script). Its project is the `project` column, or the heading's project when `heading` is set.
- Templates carry `rt1_instanceCreationPaused`. A paused template is reported as `(paused)`.
- Verified on a real database: template rows have type 0, status 0, start 2 and no start date. Templates with `trashed` = 1 exist (4 of 40) and are ignored; they are not leftovers.
- Templates do not each have an open instance. In the checked database, 36 live templates had only 5 open instances (Things creates instances shortly before they are due), plus 136 completed instances. The recurrence list is built from templates; instances are optional extra information.
- The paused flag was 0 on every template, so `(paused)` is covered only by the fixture.

### 7.3 Health checks (v0.2)

Each check returns findings with a severity: `warning` (probably a problem) or `info` (a judgement list).

| Check | Severity |
|---|---|
| Open to-dos inside a trashed project (added 2026-10-10; these are excluded from every other check) | warning |
| Unfiled open tasks (no area, no project) | warning |
| Title hygiene: stray `·` at the start or end, leading or trailing whitespace, doubled spaces, plus user-configured patterns (empty by default) | warning |
| Possible duplicates: same title after Unicode NFKC normalisation, case folding and removing punctuation | warning |
| Dated tasks inside Someday projects (will never surface) | warning |
| Active projects with no open tasks | warning |
| Recurrence rules not recognised | warning |
| Leftover recurring templates | info |
| Someday tasks inside active projects | info |
| Tasks outside any heading in projects that use headings | info |

User-configured title patterns are passed as a repeatable `--pattern REGEX` option on `check`. There is no config file in v0.2 (a TOML reader would be a new dependency on Python 3.10).

Definitions (settled 2026-10-10):
- Scope: a check looks at open, non-trashed to-dos that are not inside a trashed project (directly or through a heading). Only `open_in_trashed_project` looks at the others.
- Unfiled: in scope, no area and no project (directly or through a heading), and effective status is not Inbox.
- Duplicates: NFKC, casefold, apostrophes removed, every other Unicode punctuation character replaced by a space, whitespace collapsed and trimmed. Titles that become empty never group. A group whose members are all instances of one recurring template is not flagged.
- Dated in Someday project: in-scope to-do with a start date whose project (directly or through a heading) is open and has start Someday.
- Active project with no open tasks: a project that is open, not trashed and not Someday, with no in-scope open to-do and no live recurring template in it (directly or through a heading).
- Recurrence not recognised: live templates whose rule is unreadable or unrecognised.
- Leftover templates (info): live templates whose project is trashed or missing.
- Someday inside active project (info): in-scope to-do with effective status Someday in a project that is open and not Someday.
- Outside any heading (info): one finding per project that has at least one non-trashed heading, with the project as the first ref and each in-scope open to-do directly under it, with no heading, as the other refs.
- Findings carry ids and fixed-wording messages only, never titles, notes or user pattern text. The text output of `check` looks the titles up and shows them (with the user's own pattern next to "matches user pattern N") on the user's own screen, so it is personal data. `check --json` has ids and fixed messages only, and `check_schema_version` "1".
- Exit codes: 0 success, 1 `check` found at least one warning, 2 usage error (including an unusable `--out` path found before any work: the file exists, or the folder cannot be used: its parent is missing, or a file is in the way; a missing last folder level is created, see the 2026-10-11 decision on output folders), 3 the run failed (database could not be found or read, schema check failed, output could not be written). All commands.

All joins use UUIDs, never titles. Candidates for later, not committed: overdue deadlines, Inbox size, stale tasks.

### 7.4 JSON export

```
{
  "export_schema_version": "1.1",
  "tool": {"name": "tidyline", "version": "..."},
  "exported_at": "...",
  "environment": {"macos": "...", "arch": "...", "things_version": "...", "database_version": 29},
  "anonymisation": "none | light | strict",
  "areas": [...], "projects": [...], "headings": [...], "tasks": [...],
  "recurring_templates": [...],
  "checks_run": [...],
  "findings": [...],
  "warnings": [...]
}
```

Tasks carry: id, title, notes, area, project, heading (as ids plus titles), effective status, start, start date, deadline, status, completion date, created, modified, tags, checklist items, recurrence text and raw rule. Projects and headings have the same shape without checklist and recurrence.

- `exported_at` is local time as ISO 8601 with its UTC offset (since 1.1; it was UTC before). "Today" for effective status and the checks is its date.
- `created` and `modified` (added in 1.1) are `creationDate` and `userModificationDate` as ISO dates (`YYYY-MM-DD`) in the timezone of `exported_at`, or null when the column is empty or does not decode.
- `checks_run` (added in 1.1) has one `{"check", "severity", "findings"}` entry per check, in registry order. `findings` is the number of findings; a check that found nothing is listed with 0.

### 7.5 Anonymisation levels

| Level | Titles and names | Notes | Checklist items | Kept |
|---|---|---|---|---|
| `none` | as is | as is | as is | everything |
| `light` | kept, with emails, phone numbers, URLs, money amounts and long digit runs replaced by placeholders | removed | kept, scrubbed the same way | structure, dates, tags, recurrence |
| `strict` | replaced by stable labels derived from the id alone (kind plus a short base32 hash code of the id, such as `Task k3f7az`, `Project 7qm2xd`), so a label is the same in every export and for as long as the item exists, and says nothing about list order. Collisions are resolved deterministically | removed | replaced by count | structure, dates, recurrence, counts |

Every key is present at every level. `notes` is null at `light` and `strict`; `checklist` is null at `strict` and every to-do has `checklist_count`. At `strict`, the raw rule's timestamps `ed`, `ia` and `sr` are withheld (null); `light` keeps them. At `light` and `strict`, string values inside the raw recurrence rule and its notes become `<text>`, the hex prefix of an unreadable rule is dropped (its length is kept), and non-number values in read warnings become placeholders. Known limits: `light` is a best-effort scrub that cannot catch names, addresses or alphanumeric account numbers; ids are kept at every level, so anyone with the database can map labels back; dates, counts and findings still reveal habits.

The URL-scheme auth token is never read or exported at any level.

Known limits of `decode`:
- Labels exist only in `strict` output. `light` output keeps real titles and needs no decoding.
- `decode` needs the same database the prompt was made from. A label whose item was deleted since, or that comes from another database, stays unchanged and is counted as unmatched. A kind word followed by a six-character lowercase word (for example "Project review") looks like a label and is also counted as unmatched.
- Only whole labels and whole bare codes are replaced: a letter or digit next to one means it is part of a longer word (underscores and markdown characters do not). Lowercase only. Replacement is one pass over the original text, so a title that looks like a label or contains a code is never replaced again.

Decode rules (settled 2026-10-11):
- Bare codes: a code written without its kind word (`k3f7az`, or a collision form such as `abcdef-ghij`) is replaced when it is the code of exactly one label. A code shared by several labels is left unchanged and counted as ambiguous. A six-letter word that equals no code is left alone and not counted.
- Length and whitespace: whitespace runs and newlines in a title collapse to one space; a title over 80 characters becomes its first 79 characters plus "…".
- Tables: on a line whose first non-space character is `|`, a `|` in an inserted title (or location) is written `\|`. Elsewhere titles go in unescaped; `*` or a backtick in a title can still start emphasis or code.
- Quotes: a title goes in straight double quotes, unless the label in the answer is directly surrounded by quote characters (`"` `“` `”` `'`) or backticks.
- Shared titles: when two or more items still in the payload's scope (7.6: not completed, cancelled or trashed themselves; open to-dos in trashed projects and recurring templates count) share a title after whitespace is collapsed, each gets its location inside the quotes: `"Title (in Parent)"`. Parent is the project for to-dos and headings, the area for projects and for to-dos with no project, nothing for areas and tags; it is shortened to 40 characters. A completed or trashed twin adds no location.
- The summary on stderr gives counts only: labels replaced, bare codes replaced, distinct items, ambiguous bare codes, unmatched label-like strings.

### 7.6 Prompt payload

`prompt` writes this payload, not the export. It is built from the same snapshot and export entries, and anonymised by the same rules (7.5) and the same id-derived labels, so `decode` maps strict labels back.

```
{
  "payload_schema_version": "1",
  "anonymisation": "light | strict",
  "exported_at": "...",
  "scope": "Open work only: ...",
  "summary": {...},
  "areas": [...], "projects": [...], "headings": [...], "tasks": [...],
  "tags": [...], "recurring_templates": [...],
  "checks_run": [...], "findings": [...], "data_read_warnings": [...]
}
```

Definitions:
- An open to-do is a to-do (not a template) that is not completed, cancelled or trashed. It is in a trashed project when its project or heading is trashed. `open_todos` and `by_status` count open to-dos not in a trashed project; `open_in_trashed_project` counts the others.
- A completed to-do has status completed and is not trashed; cancelled to-dos are not counted. The 14- and 30-day windows end on the local date of `exported_at`, that day included.
- A to-do counts towards an area through its own area, or else its project's area. The task row's `area` stays the to-do's own column (7.4).
- `by_status` has `inbox`, `today`, `this_evening`, `upcoming`, `anytime` and `someday` (7.1).

Contents:
- `summary`: `open_todos`, `by_status`, `open_in_trashed_project`, `areas` (count), `projects` {`open`, `someday`, `active`, `completed`, `trashed`}, `completed_todos` {`total`, `last_14_days`, `last_30_days`}, `recurring_templates` {`live`, `leftover`}, `tagged_open_todos`. `open` is `active` plus `someday` (untrashed, status open); `completed` counts untrashed completed projects; `trashed` counts trashed projects of any status.
- `areas`: id, title, `open_projects`, `open_todos`, `by_status`, `completed_last_14_days`, `completed_last_30_days`, `completed_total`.
- `projects`: open, untrashed projects, plus any other project that still holds an open to-do. Each has id, title, area, `state` (`active` or `someday`, from its start), deadline, created, modified, `open_todos`, `by_status`, `headings` and `empty_headings` (open, untrashed headings, and those with no open to-do), `live_templates`, `completed_last_30_days`, `completed_total`, `trashed`.
- `headings`: open, untrashed headings of listed projects: id, title, project, `open_todos`.
- `tasks`: open to-dos only, including those in a trashed project. Each has id, title, notes (null), area, project, heading, `effective_status`, start date, deadline, created, modified, tags (`{id, title}`), `checklist_count`, recurrence, `in_trashed_project`. No checklist items.
- `tags`: id, title, `open_todos`, `completed_total`.
- `recurring_templates`: the export's entries without notes; `instances` lists open instances only.
- `checks_run` and `findings` as in the export; `data_read_warnings` is the export's `warnings`.

`prompt --out` writes the payload as compact JSON (one line, no indentation, separators `,` and `:`, non-ASCII kept); the export stays indented. No completed, cancelled or trashed to-do appears as a row or an id anywhere in the payload. The preview says what was left out and that it is counted in the summary only.

## 8. Architecture

```
src/tidyline/
  __init__.py
  db/locate.py        find the database (--db, THINGSDB, standard path)
  db/snapshot.py      backup-API copy into a private temp dir; cleanup
  db/schema.py        required tables/columns, version read, tested-versions table
  model.py            frozen dataclasses: Area, Project, Heading, Task, Template, Snapshot
  read.py             builds a Snapshot (things.py + raw SQL)
  status.py           effective status (7.1)
  recurrence.py       decode and describe rules (7.2)
  checks/             one module per check, a Finding type and a registry
  anonymise.py        levels (7.5)
  render/json_out.py  export (7.4)
  render/text.py      text report
  render/check_out.py text and JSON output of `check`
  render/help_out.py  the help screen shown with no arguments
  render/html/        v0.3
  llm/payload.py      the open-work payload for `prompt` (7.6)
  llm/prompt.py       v0.2: fill the audit template, write payload and prompt
  llm/ollama.py       v0.4
  llm/cloud.py        v0.4
  cli.py
tests/
  fixtures/schema.sql        DDL only, dumped from a real database, no rows
  fixtures/build_fixture.py  generates the synthetic database
docs/
  DESIGN.md, COMPATIBILITY.md, RECURRENCE.md
  GETTING_STARTED.md  step-by-step guide for people new to the command line
  FIXING_PROBLEMS.md  what each check means and how to fix it in Things 3
```

The core returns data and never prints. The CLI only parses options and calls the core and renderers.

### CLI

| Command | Purpose | Main options |
|---|---|---|
| `doctor` | Locate the database, check permissions and schema, show versions and whether they are tested | `--db` |
| `report` | Text summary; HTML from v0.3 | `--html`, `--out`, `--include-completed`, `--no-color` |
| `check` | Health checks only; exit code 1 if any warning. Text output: a total line, a heading per check with severity and count, items grouped by project, area or trashed project with a count (decisions log, 2026-10-11) | `--only`, `--json` |
| `export` | JSON export | `--out`, `--anonymise {none,light,strict}` |
| `recurrence` | List every repeating template with its readable rule, so it can be checked against what Things shows: one block per template (rule text or "not recognised", title, project or area, state live / leftover / not recognised) sorted by state, rule text and id, then a summary line. Exit 0 even when rules are not recognised. `--raw` adds the rule as stored (XML text, or hex and length for a binary plist), the decoded fields and, for an unrecognised rule, the reason, after a personal-data warning line. | `--raw`, `--db` |
| `prompt` | Level 0: anonymised open-work payload (7.6) plus filled audit prompt, with preview | `--anonymise {light,strict}` (default strict), `--context FILE`, `--out DIR`, `--copy` |
| `decode` | Replace strict labels (`Task k3f7az`) in an LLM answer with the real titles from the current database. Reads the answer from a UTF-8 file of at most 5 MB; writes the decoded text to stdout, or to `--out` (mode 0600, never overwrites). Bare codes, long titles, `|` in tables, quotes and shared titles follow the decode rules in 7.5. A summary (labels and bare codes replaced, distinct items, ambiguous codes, unmatched; never titles) and a personal-data warning go to stderr. | `ANSWER_FILE`, `--out FILE`, `--db` |
| `ask` | v0.4: levels 1 and 2, after preview and confirmation | `--provider`, `--model`, `--yes` |

Global: `--db PATH`, `--version`, `--verbose`. With no command, a help screen is printed (exit 0).

`--out` (`report`, `export`, `prompt`, `decode`): the last folder level is created when missing (decisions log, 2026-10-11): mode 0700, parent must exist, existing folders untouched.

## 9. Milestones

### v0.1: core and parity (private repo, or TestPyPI). DONE 2026-10-10, tagged v0.1.0

Scope: snapshot reader, schema check, `doctor`, model, effective status, recurrence, `export` (none level), text `report`.

Done when:
- The synthetic fixture covers: headings, area-level tasks, unfiled tasks, a Someday project with dated tasks, Today and This Evening tasks, an overdue deadline, every recurrence type in 7.2, a leftover template, two projects with the same title, and non-English titles. All tests pass against it.
- On the real database, counts match the earlier personal script except for the intended fixes, and every difference is explained. The comparison script stays outside the repo.
- Works while Things is running.

### v0.2: audit and first public release (PyPI). DONE 2026-10-11, published to PyPI as 0.2.0

Scope: all checks in 7.3, `check`, `recurrence`, anonymisation, `prompt`, `decode`.

Done when:
- `pipx install tidyline` and `uv tool install tidyline` work on a clean Mac.
- Every check has a fixture test.
- A test confirms that no fixture title, note or checklist text appears in a `strict` export.
- The README states the limitations, non-affiliation and personal-data warning. COMPATIBILITY.md lists tested versions.
- CI runs on macOS with sockets blocked for the core tests.

### v0.3: HTML report and Homebrew tap

Done when:
- `report --html` writes one file that opens offline in Safari and Chrome and reads well at phone width.
- Snapshot tests of the HTML pass against the fixture.
- `brew install <user>/tap/tidyline` works on a clean Mac.
- Screenshots use only fixture data.

### v0.4: opt-in LLM levels 1 and 2

Done when:
- `ask` works with Ollama and one cloud provider.
- Nothing is sent without a preview and confirmation (or `--yes`).
- Keys come only from environment variables and are never written to disk.
- Network code is tested with mocks. The core still passes the offline test suite.
- The docs state exactly what each level sends and where.

Later, only after v0.4: Raycast extension, MCP server, menu-bar app.

## 10. v0.1 build order

1. Scaffold with uv: package layout, `requires-python = ">=3.10"`, things.py as the only runtime dependency, pytest, ruff and pytest-socket as development dependencies.
2. Dump the schema only: `sqlite3 -readonly "<path>" .schema > tests/fixtures/schema.sql`. Read it before committing.
3. Fixture builder that inserts synthetic rows using the real encodings (packed dates, XML plist recurrence rules).
4. `db/locate.py`, `db/snapshot.py`, `db/schema.py`, then `doctor`.
5. `model.py`, `read.py`, `status.py`.
6. `recurrence.py`.
7. `render/json_out.py`, `render/text.py`, then `report` and `export`.
8. Parity run against the real database, outside the repo.

## 11. Verify during v0.1

- Which column marks This Evening, and its values.
- That the backup API copy works while Things is writing.
- A task inside a trashed or closed project is classified from its own fields (status ignores closed parents). Candidate health check for v0.2.
- Real database read check, 2026-10-10 (counts only): 36 live templates all recognised, 2 leftover templates, 0 warnings, effective status counts sum to the open to-do total.
- Works while Things is running: confirmed 2026-10-10. Doctor, export, report and the parity run all read a snapshot while the Things app was open.
- Parity run against the personal v6 script, 2026-10-10 (counts only, outside the repo): 22 of 24 checks identical (areas, projects, open/completed/cancelled to-dos, Inbox/Anytime/Someday, deadlines, notes, checklists, tags, area sizes, unfiled, live and leftover templates, repeating instances). Explained differences: (1) v6 labels every dated task Upcoming; tidyline splits them into Today (11) and Upcoming (8), as intended. (2) tidyline reports 33 open to-dos inside trashed projects that v6 cannot see. (3) tidyline lists 5 completed headings of completed projects that v6 omits (things.py does not return them in project items). (4) tidyline recurrence text is more specific (ends after, end date, lead time), so it forms more distinct groups; both total 36 templates.
- Done 2026-10-10: template row shape; keys real rules carry; daily offsets; `startBucket` = 1 for This Evening (7.1, 7.2).
- Verify with counts-only queries against the maintainer's own database, run by hand and never committed. Output contains numbers and key names, no titles.

### Still open

- Whether overdue-deadline tasks without a start date should count as Today (rule 5).
- Whether macOS shows a privacy prompt when Terminal reads the Group Container while Things is running.
- Meaning of `wdo` values other than 1 and -1, and of `dy` = -1 (last day).
- Whether `ts` 0 can mean a deadline on the same day, and whether `ed` ordinary values correspond to "ends on date" in the dialog.
- Whether an evening task can carry a past date or sit in a Someday project.
- Rule 5 also applies to Someday tasks (7.1 order): a Someday task with no start date and an overdue deadline is Today. Not seen on real data.
- In the export, a task's `area` is its own column and is not inherited from its project. Deferred to v0.3: decide when building the HTML report whether consumers need an inherited area.
