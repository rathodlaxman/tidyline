# CLAUDE.md

Instructions for Claude Code in this repository. The full plan is in `docs/DESIGN.md`. Read it before structural work.

## What this is

tidyline: an offline, read-only command-line tool that audits a Things 3 database on macOS and produces a health report, a JSON export and an anonymised LLM-ready export. Unofficial; not affiliated with Cultured Code.

## Hard rules

- **Read-only.** Never write to the Things database. Never call things.py's `complete`, `show`, `url` or `token`. Never read or export the URL-scheme auth token.
- **Snapshot only.** Read the database through `tidyline.db.snapshot`, never the live file directly.
- **Offline.** No network access anywhere except `tidyline/llm/ollama.py` and `tidyline/llm/cloud.py`. Do not add code that opens sockets or makes HTTP requests elsewhere.
- **No personal data.** Never read the real Things database in tests. Never commit database files, exports or reports. Tests, examples and screenshots use only the synthetic fixture in `tests/fixtures/`.
- **Honest about the schema.** Undocumented columns are read. Check the schema first, fail with a clear message, and report unknown recurrence rules as unknown instead of guessing.
- **Ask before:** adding a runtime dependency, changing the CLI surface, changing the JSON export format, or changing anything listed in the decisions log in `docs/DESIGN.md`.

## Conventions

- Python 3.10 or later. src layout: `src/tidyline/`.
- Core modules return data and never print. Only `cli.py` and `render/` produce output.
- Frozen dataclasses for the model. Join by UUID, never by title.
- Normalise text with Unicode NFKC and `casefold()`; never assume ASCII.
- Every health check has a fixture test.
- Error messages say what went wrong and what the user can do next.

## Commands

```bash
uv sync                      # install dependencies
uv run pytest                # tests (core tests run with sockets blocked)
uv run ruff check .          # lint
uv run ruff format .         # format
uv run tidyline --help       # run the CLI
```

## Commits

Small, focused commits with a one-line summary in the imperative ("Add schema check").
