# Changelog

## Unreleased

## 0.2.2 - 2026-10-11

- Fixed the SyntaxWarning that pip printed at install time (an invalid escape
  in a docstring). A test now compiles every module with warnings as errors.
- `tidyline` with no arguments prints a short, friendly help screen: the
  commands in plain words, examples, which commands show your titles, and a
  link to the getting-started guide. `tidyline --help` is unchanged.
- The text output of `check` is easier to scan: each check has a heading with
  its severity and count, and open to-dos inside a trashed project are grouped
  under their project. Findings, counts, `check --json` and exit codes are the
  same.
- Piping output to a command that closes early (for example
  `tidyline check --json | head`) ends quietly, with exit code 0 and no
  traceback.
- The last level of an `--out` folder is created for you, readable only by you
  (mode 0700), when its parent exists. tidyline never creates a chain of
  folders, never changes a folder that already exists (it warns if group or
  others can read it), and still never overwrites a file. Do not use a folder
  that is synced or backed up to a cloud service.

## 0.2.1 - 2026-10-11

- `decode` is easier to read: bare codes such as `k3f7az` are replaced when
  they match one item, titles go in quotes, long titles are cut to 80
  characters, `|` is escaped in table rows, and titles shared by open items get
  their project or area.
- `prompt` payload holds open work only, with a ready-made `summary`,
  `checks_run` and per-area, per-project and per-tag counts. Completed,
  cancelled and trashed items are counted, not listed. Written as compact JSON.
- Export (`export_schema_version` 1.1): projects, headings and to-dos gain
  `created` and `modified`; the export gains `checks_run`. At `strict`, the raw
  recurrence timestamps `ed`, `ia` and `sr` are withheld (null).
- `exported_at` and every date derived from it use local time with its UTC
  offset, in both `export` and `prompt`.
- `report` shows recurring-template counts only (live, leftover, recognised,
  assumed, and not recognised when there are any); no template title appears.
  `recurrence` shows the titles.
- The audit prompt is revised for the new payload: it asks for a "Start here"
  section first, full item names, one item per table row, a short answer (at
  most 40 migration rows), and numbers only from the data, and it explains the
  `summary`, `checks_run` and `created`/`modified` fields.
- Corrected statements about `check` output: the text output lists real titles
  on your own screen, so it is personal data; `check --json` has ids and fixed
  messages only, and `report` is counts only. The README, DESIGN and both guides
  now say so.
- The example label in the prompt, preview, README and design notes is now
  `Task k3f7az`; the old example contained a digit that real labels never have.
- Two guides: `docs/GETTING_STARTED.md` (for people new to the command line) and
  `docs/FIXING_PROBLEMS.md` (what each check means and how to fix it in Things).
  The README links both, and the text output of `tidyline check` ends with a
  link to the fixing guide. `check --json` is unchanged.
- Compatibility note on the prompt and decode flow, and a privacy tip in the
  README and the getting started guide: use a private chat with memory switched
  off, and also check the assistant's profile and personal-preference settings,
  which can still reach the answer. The compatibility note records one test in
  which the answer used the user's first name, likely from the chat app's
  profile.
- Compatibility note: Cultured Code changed how repeating to-dos behave in
  Things 3.23 (August 2026). tidyline's recurrence reading was checked on Things
  3.24.1, which is after that change; earlier versions were not tested.

## 0.2.0

Commands:

- `doctor`: finds the database and checks permissions, schema and versions.
- `report`: prints or writes a text summary with counts and a health-check summary.
- `check`: runs ten health checks; exits 1 if any warning is found.
- `export`: writes a JSON export at `none`, `light` or `strict` anonymisation.
- `prompt`: writes an anonymised payload and a filled audit prompt for an AI assistant.
- `decode`: replaces `strict` labels in an answer with your real titles.
- `recurrence`: lists every repeating template with its readable rule.
