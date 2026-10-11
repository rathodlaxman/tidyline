# Changelog

## Unreleased

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
  assumed, and not recognised when there are any); no template title appears. `recurrence` shows
  the titles.
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

## 0.2.0

Commands:

- `doctor`: finds the database and checks permissions, schema and versions.
- `report`: prints or writes a text summary with counts and a health-check summary.
- `check`: runs ten health checks; exits 1 if any warning is found.
- `export`: writes a JSON export at `none`, `light` or `strict` anonymisation.
- `prompt`: writes an anonymised payload and a filled audit prompt for an AI assistant.
- `decode`: replaces `strict` labels in an answer with your real titles.
- `recurrence`: lists every repeating template with its readable rule.
