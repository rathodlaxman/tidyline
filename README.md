# tidyline

An offline, read-only command-line tool that audits a Things 3 database on macOS.

> **Unofficial.** tidyline is not affiliated with or endorsed by Cultured Code.
> "Things" is a trademark of its owner. This project uses the name only to say
> which app it reads. It uses no logo or icon.

## Your data is personal

The Things database, the JSON export, the text report and any decoded file
contain your personal data: task titles, notes, checklists and dates. Never
commit them to a repository, and never post them in a public issue.

Anonymised exports reduce the risk. They cannot remove all of it.

- `light` keeps titles but replaces emails, phone numbers, URLs, money amounts
  and long digit runs with placeholders. It removes notes. It is a best-effort
  scrub. It cannot catch names, addresses or alphanumeric account numbers.
- `strict` replaces every title and name with a label such as `Task k3f9az`. It
  removes notes and replaces checklist items with a count. Only `strict`
  removes all titles.
- At every level, ids are kept. Anyone who also has your database can map them
  back to titles. Dates, counts and findings stay too, and they reveal how you
  work.

## What it does

tidyline reads your Things database and reports on it: counts, health checks,
a decoded view of your repeating tasks, a JSON export, and an anonymised
prompt you can give to an AI assistant yourself.

What it does not do:

- It never writes to the Things database.
- It never reads the database file directly. It makes a private copy (a
  snapshot) with the SQLite backup API and reads that, then deletes the copy.
  Things can stay open while it runs.
- It makes no network calls. None of the current commands needs a network.
- It never reads or exports the URL-scheme auth token.
- It never changes, completes or opens anything in Things.

## Install

From source:

```
git clone https://github.com/rathodlaxman/tidyline.git
cd tidyline
uv sync
uv run tidyline --version
```

You need [uv](https://docs.astral.sh/uv/) and Python 3.10 or later.

Once published: `pipx install tidyline` or `uv tool install tidyline`.

macOS may block Terminal from reading Things' data folder. If `doctor` says so,
open System Settings, Privacy & Security, Full Disk Access, turn it on for your
terminal app, then quit and reopen the terminal.

## Quick start

Run these from the folder you cloned. Write outputs outside any git folder, so
they cannot be committed by accident. The examples use `~/tidyline-out/`, which
must exist first:

```
mkdir -p -m 700 ~/tidyline-out
uv run tidyline doctor
uv run tidyline report
uv run tidyline check
uv run tidyline recurrence
uv run tidyline export --out ~/tidyline-out/export.json
uv run tidyline prompt --out ~/tidyline-out/prompt
uv run tidyline decode ~/tidyline-out/answer.md --out ~/tidyline-out/answer-decoded.md
```

- `doctor` finds the database and checks permissions, the schema and versions.
- `report` prints a text summary. It shows counts only, except for repeating
  templates, which are listed with their titles.
- `check` runs the health checks.
- `recurrence` lists every repeating template with its readable rule.
- `export` writes a JSON export. Add `--anonymise light` or `--anonymise strict`
  to anonymise it.
- `prompt` and `decode` are described below.

Every command accepts `--db PATH` for a database in a non-standard place. You
can also set the `THINGSDB` environment variable. Add `--verbose` before the
command for more detail when something fails.

## Commands

| Command | What it does | Options |
|---|---|---|
| `doctor` | Finds the database and checks permissions, schema and versions. | `--db` |
| `report` | Prints a text summary, or writes it to a new file. | `--out PATH`, `--include-completed`, `--no-color`, `--db` |
| `check` | Runs the health checks. | `--only ID [ID ...]`, `--pattern REGEX [REGEX ...]`, `--json`, `--db` |
| `export` | Writes a JSON export to a new file. | `--out PATH` (required), `--anonymise {none,light,strict}`, `--db` |
| `recurrence` | Lists every repeating template with its readable rule. | `--raw`, `--db` |
| `prompt` | Writes an anonymised payload and a filled audit prompt. | `--anonymise {light,strict}`, `--context FILE`, `--out DIR`, `--copy`, `--db` |
| `decode` | Replaces `strict` labels in an answer with your real titles. | `ANSWER_FILE`, `--out FILE`, `--db` |

Files written with `--out` get mode 0600, and an existing file is never
overwritten.

Exit codes:

| Code | Meaning |
|---|---|
| 0 | Success. For `check`: no warnings. |
| 1 | Only `check` uses this: at least one warning-level finding. |
| 2 | Usage error, such as a bad option, a bad regular expression or an output path that already exists. |
| 3 | The run failed: the database could not be found or read, or a file could not be written. |

## Using an AI assistant without sending anything automatically

tidyline never sends your data anywhere. `prompt` prepares two files, and you
decide whether to attach or paste them into an assistant yourself.

```
uv run tidyline prompt --context my-context.txt --out ~/tidyline-out/prompt
```

- The default is `--anonymise strict`. There is no `none` option for `prompt`.
- `--context FILE` is a plain text file with sections labelled `Role:`,
  `Priorities:` and `Dates:`. It is added to the prompt exactly as you wrote it.
  A section you leave out stays as a visible placeholder, and the preview warns
  you.
- `--out DIR` writes `tidyline_payload.json` (the anonymised export) and
  `tidyline_prompt.md` (the filled prompt). `--copy` puts the prompt on the
  clipboard with `pbcopy`. With neither option, nothing is written.
- `prompt` always prints a preview first: the level, the counts, what was
  removed or replaced, and your context text. The last line says nothing has
  been sent anywhere.
- The text report is never part of the output.

At `strict`, titles are hidden, so the assistant cannot judge how your tasks are
worded. The prompt tells it to skip that part. Use `--anonymise light` if you
want task wording reviewed, and accept that `light` leaves titles in place.

To turn the answer back into real titles, save it to a file and run:

```
uv run tidyline decode ~/tidyline-out/answer.md
```

`decode` recomputes each label from the current database, so it needs no
mapping file. Labels it cannot match stay as they are, and it reports how many.
It needs the same database the prompt was made from, and `light` output needs no
decoding. Titles go in exactly as stored, so a title containing `|` can break a
markdown table cell. The decoded text contains real titles, so treat it as
personal data.

## Health checks

`tidyline check` exits with 1 if any warning is found. Info findings do not
change the exit code. Findings carry ids and fixed messages, never titles. The
text output shows titles on your own screen only. `check --json` prints ids
only.

| Check | Severity | What it finds |
|---|---|---|
| `open_in_trashed_project` | warning | Open to-dos inside a trashed project. The other checks leave these out. |
| `unfiled_open` | warning | Open to-dos with no area and no project, outside the Inbox. |
| `title_hygiene` | warning | A stray `·` at either end, leading or trailing spaces, doubled spaces, and matches of your own `--pattern` regular expressions. |
| `possible_duplicates` | warning | Open to-dos whose titles match after Unicode normalisation, case folding, apostrophes removed and other punctuation treated as spaces. |
| `dated_in_someday_project` | warning | To-dos with a start date inside a Someday project. They will never surface. |
| `active_project_no_open_tasks` | warning | Active projects with no open to-dos and no live repeating template. |
| `recurrence_not_recognised` | warning | Repeating templates whose rule tidyline cannot read or does not recognise. |
| `leftover_templates` | info | Repeating templates whose project is trashed or missing. |
| `someday_in_active_project` | info | Someday to-dos inside active projects. |
| `outside_heading` | info | To-dos outside any heading in projects that use headings. |

A finding for one of your own patterns says only "matches user pattern N".
The text output on your screen shows the pattern next to it; the JSON does not.

## Things does not document its database

tidyline reads columns that Things does not document, because there is no
public API for this. These include:

- the repeating-task columns `rt1_recurrenceRule`, `rt1_repeatingTemplate` and
  `rt1_instanceCreationPaused`;
- `startBucket`, which marks This Evening;
- `deadlineSuppressionDate`, which keeps an overdue deadline out of Today.

Repeat rules are stored as property lists whose meaning was worked out by
comparing them with what Things shows. A rule tidyline does not understand is
reported as not recognised. It is never guessed.

Before reading, tidyline checks that the tables and columns it needs exist. If
they do not, it stops with a message that names what is missing, the versions
it was tested with, and what to do next. See
[docs/COMPATIBILITY.md](https://github.com/rathodlaxman/tidyline/blob/main/docs/COMPATIBILITY.md) for what has been tested and
what has not.

Not yet built: the HTML report and the opt-in model integration.

## Development

```
uv sync
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

Tests use only a synthetic database built by `tests/fixtures/build_fixture.py`.
The real Things database is never used in tests, and no database, export or
report is ever committed. Network sockets are blocked while the tests run.

Golden files under `tests/fixtures/` are regenerated with
`TIDYLINE_UPDATE_GOLDEN=1 uv run pytest`. Review the diff before committing.

The design and the decisions behind it are in [docs/DESIGN.md](https://github.com/rathodlaxman/tidyline/blob/main/docs/DESIGN.md).
How repeat rules are read is in [docs/RECURRENCE.md](https://github.com/rathodlaxman/tidyline/blob/main/docs/RECURRENCE.md).

## Licence

MIT. See [LICENSE](https://github.com/rathodlaxman/tidyline/blob/main/LICENSE). tidyline depends on
[things.py](https://github.com/thingsapi/things.py), which is licensed under
Apache 2.0.
