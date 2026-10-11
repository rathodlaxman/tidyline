# Changelog

## Unreleased

- `decode` is easier to read: bare codes such as `k3f9az` are replaced when
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

## 0.2.0

Commands:

- `doctor`: finds the database and checks permissions, schema and versions.
- `report`: prints or writes a text summary with counts and a health-check summary.
- `check`: runs ten health checks; exits 1 if any warning is found.
- `export`: writes a JSON export at `none`, `light` or `strict` anonymisation.
- `prompt`: writes an anonymised payload and a filled audit prompt for an AI assistant.
- `decode`: replaces `strict` labels in an answer with your real titles.
- `recurrence`: lists every repeating template with its readable rule.
