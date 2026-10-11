"""The HTML report (DESIGN.md 7.7). Returns a string; never prints.

One self-contained file: inline CSS, no script, no external resource. It shows
task titles, so it is personal data. Every dynamic string goes through `_e`,
which replaces control characters and escapes for HTML; titles also sit in
`<bdi>` so bidirectional characters cannot reorder the text around them. The
numbers and groups come from `report_data`, as for the text report.
"""

from __future__ import annotations

import datetime as dt
import html
import re
from collections.abc import Mapping, Sequence
from typing import Any

from tidyline.checks import CHECK_IDS, CHECKS
from tidyline.checks.groups import CheckSection, Group, Item
from tidyline.model import Snapshot
from tidyline.render.check_out import FIXING_GUIDE_URL, safe_title
from tidyline.report_data import (
    RECENT_DAYS,
    STATUS_ORDER,
    Counts,
    ReportData,
    TemplatePlace,
    TemplateRow,
    build_report,
)

CSP = (
    "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'"
)
PRIVATE_NOTICE = (
    "This file contains your task titles and the names of your projects and "
    "areas. Keep it private and do not commit or share it."
)
FOOTER = (
    "Made offline by tidyline {version} from a private copy of the database. "
    "Nothing was sent anywhere and nothing in Things was changed."
)
REVIEW_HEADING = "Want a deeper review?"
REVIEW_TEXT = (
    "tidyline itself does not write recommendations. To get a review from an AI "
    "assistant, run <code>tidyline prompt</code>, paste the result into the "
    "assistant, then run <code>tidyline decode</code> on its answer."
)
NOT_AFFILIATED = "tidyline is unofficial and not affiliated with Cultured Code."
STATUS_CLASSES = {
    "Inbox": "inbox",
    "Today": "today",
    "This Evening": "evening",
    "Upcoming": "upcoming",
    "Anytime": "anytime",
    "Someday": "someday",
}
CONFIDENCE_WORDS = {
    "verified": "verified",
    "assumed": "assumed",
    "unrecognised": "not recognised",
}

# Colours: --fg, --muted, --link and the badge pairs are text and keep a
# contrast of at least 4.5:1 on --bg and --card in both themes (a test reads
# these variables). The bar colours carry no text; the legend gives the words.
CSS = """
:root {
  color-scheme: light dark;
  --bg: #ffffff; --card: #f4f4f6; --fg: #1d1d1f; --muted: #55555a;
  --border: #d2d2d7; --link: #0050a8;
  --warn-bg: #fff1cc; --warn-fg: #5c3a00;
  --info-bg: #e3edff; --info-fg: #0a3f8a;
  --mark-bg: #fff6e0;
  --s-inbox: #8e8e93; --s-today: #e0a100; --s-evening: #5e5ce6;
  --s-upcoming: #e8572a; --s-anytime: #0a84ff; --s-someday: #a2845e;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #1c1c1e; --card: #2a2a2d; --fg: #f2f2f7; --muted: #b8b8bf;
    --border: #48484a; --link: #7ab8ff;
    --warn-bg: #443100; --warn-fg: #ffd970;
    --info-bg: #10284d; --info-fg: #b3d1ff;
    --mark-bg: #3a2f14;
  }
}
* { box-sizing: border-box; }
html { -webkit-text-size-adjust: 100%; }
body {
  margin: 0; background: var(--bg); color: var(--fg);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
    "Helvetica Neue", Arial, sans-serif;
  font-size: 16px; line-height: 1.5;
}
.page { max-width: 960px; margin: 0 auto; padding: 24px 16px 48px; }
h1 { font-size: 1.75rem; margin: 0 0 12px; }
h2 { font-size: 1.25rem; margin: 32px 0 12px; }
code, .mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 0.9em; overflow-wrap: anywhere;
}
a { color: var(--link); }
.muted { color: var(--muted); }
.facts { display: flex; flex-wrap: wrap; gap: 4px 24px; margin: 0; }
.facts div { display: flex; gap: 6px; }
.facts dt { color: var(--muted); }
.facts dd { margin: 0; }
.private {
  margin: 16px 0 0; padding: 12px 14px; border-radius: 8px;
  background: var(--warn-bg); color: var(--warn-fg);
}
.lead { font-size: 1.1rem; margin: 0; }
.tiles { display: flex; flex-wrap: wrap; gap: 12px; }
.tile {
  flex: 1 1 150px; padding: 12px 14px; border-radius: 8px;
  background: var(--card); border: 1px solid var(--border);
}
.tile .number { display: block; font-size: 1.75rem; font-weight: 600; }
.bar {
  display: flex; height: 22px; border-radius: 6px; overflow: hidden;
  border: 1px solid var(--border); background: var(--card);
}
.bar span { flex-basis: 0; min-width: 2px; }
.legend {
  display: flex; flex-wrap: wrap; gap: 6px 18px; list-style: none;
  padding: 0; margin: 10px 0 0;
}
.legend li { display: flex; align-items: center; gap: 6px; }
.swatch {
  display: inline-block; width: 12px; height: 12px; border-radius: 3px;
  border: 1px solid var(--border);
}
.inbox { background: var(--s-inbox); } .today { background: var(--s-today); }
.evening { background: var(--s-evening); }
.upcoming { background: var(--s-upcoming); }
.anytime { background: var(--s-anytime); }
.someday { background: var(--s-someday); }
.check {
  border: 1px solid var(--border); border-radius: 8px; margin: 0 0 10px;
  background: var(--card);
}
.check > summary, .check.empty { padding: 10px 14px; }
.check > summary { cursor: pointer; }
.check-body { padding: 0 14px 12px; }
.check-name { font-weight: 600; }
.badge {
  display: inline-block; padding: 0 8px; border-radius: 999px;
  font-size: 0.85em; font-weight: 600;
}
.badge.warning { background: var(--warn-bg); color: var(--warn-fg); }
.badge.info { background: var(--info-bg); color: var(--info-fg); }
.message { margin: 4px 0 8px; font-style: italic; }
.place { margin: 10px 0 2px; font-weight: 600; }
.place .muted { font-weight: 400; }
ul.items { margin: 0; padding-left: 22px; }
ul.items li { margin: 2px 0; overflow-wrap: anywhere; }
.t { white-space: pre-wrap; }
.t::before { content: "\\201C"; }
.t::after { content: "\\201D"; }
.note { color: var(--muted); }
.fix { margin: 10px 0 0; }
.counts { display: flex; flex-wrap: wrap; gap: 4px 20px; margin: 0 0 12px; }
.counts div { display: flex; gap: 6px; }
.counts dt { color: var(--muted); }
.counts dd { margin: 0; font-weight: 600; }
.scroll { overflow-x: auto; border: 1px solid var(--border); border-radius: 8px; }
table { border-collapse: collapse; width: 100%; min-width: 560px; }
th, td {
  text-align: left; vertical-align: top; padding: 6px 10px;
  border-bottom: 1px solid var(--border);
}
th { background: var(--card); }
tr:last-child td { border-bottom: 0; }
tr.marked td { background: var(--mark-bg); }
tr.marked td:first-child { box-shadow: inset 4px 0 0 var(--warn-fg); }
.closed { margin-top: 14px; }
.closed table { min-width: 0; }
.review {
  margin: 32px 0 0; padding: 12px 14px; border-radius: 8px;
  background: var(--info-bg); color: var(--info-fg);
}
.review p { margin: 0; }
.review p + p { margin-top: 4px; }
@media (max-width: 600px) {
  .scroll.cards { overflow-x: visible; border: 0; border-radius: 0; }
  .cards table, .cards tbody, .cards tr, .cards td {
    display: block; width: 100%; min-width: 0;
  }
  .cards thead {
    position: absolute; width: 1px; height: 1px; overflow: hidden;
    clip: rect(0 0 0 0); white-space: nowrap;
  }
  .cards tr {
    margin: 0 0 10px; padding: 8px 12px; border: 1px solid var(--border);
    border-radius: 8px; background: var(--card);
  }
  .cards tr.marked { background: var(--mark-bg); }
  .cards td, .cards tr:last-child td { padding: 2px 0; border: 0; }
  .cards tr.marked td { background: none; }
  .cards tr.marked td:first-child { box-shadow: none; }
  .cards td:first-child { font-weight: 600; }
  .cards td + td::before {
    content: attr(data-label) ": "; color: var(--muted); font-weight: 400;
  }
}
footer {
  margin-top: 40px; padding-top: 16px; border-top: 1px solid var(--border);
  color: var(--muted); font-size: 0.9rem;
}
footer p { margin: 4px 0; }
@media print {
  body { background: none; }
  .tile, .check, .private, .review, th, tr.marked td { background: none; }
  .check, .tile { box-shadow: none; break-inside: avoid; }
}
"""


def render_html(
    snapshot: Snapshot,
    *,
    today: dt.date,
    tool_version: str,
    environment: Mapping[str, Any],
    include_completed: bool = False,
) -> str:
    """The report as one HTML document. `environment` is as for the text
    report. `include_completed` adds the "Closed items" table."""
    data = build_report(
        snapshot, today=today, tool_version=tool_version, environment=environment
    )
    date = data.today.isoformat()
    parts = [
        "<!DOCTYPE html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        f'<meta http-equiv="Content-Security-Policy" content="{_e(CSP)}">',
        '<meta name="referrer" content="no-referrer">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        '<meta name="color-scheme" content="light dark">',
        f"<title>tidyline report, {_e(date)}</title>",
        f"<style>{CSS}</style>",
        "</head>",
        "<body>",
        '<div class="page">',
        _header(data),
        "<main>",
        _attention(data),
        _glance(data, include_completed),
        _where(data.counts),
        _checks(data.checks),
        _repeating(data),
        _warnings(data.warnings),
        _review(),
        "</main>",
        _footer(data),
        "</div>",
        "</body>",
        "</html>",
    ]
    return "\n".join(parts) + "\n"


def _e(text: object) -> str:
    """Make any dynamic value safe to put in HTML text or an attribute."""
    cleaned = safe_title(str(text))
    cleaned = cleaned.encode("utf-8", "replace").decode("utf-8")  # lone surrogates
    return html.escape(cleaned, quote=True)


def _plural(number: int, noun: str) -> str:
    return f"{number} {noun}" + ("" if number == 1 else "s")


def _title(named_title: str | None) -> str:
    if named_title is None:
        return '<span class="muted">(not found)</span>'
    if not named_title:
        return '<span class="muted">(untitled)</span>'
    return f'<bdi class="t">{_e(named_title)}</bdi>'


def _header(data: ReportData) -> str:
    env = data.environment
    tested = "yes" if env.get("tested") else "no (run <code>tidyline doctor</code>)"
    facts = [
        ("Date", _e(data.today.isoformat())),
        ("tidyline", _e(data.tool_version)),
        ("Things", _e(env.get("things_version") or "unknown")),
        ("Database version", _e(env.get("database_version") or "unknown")),
        ("macOS", _e(env.get("macos") or "unknown")),
        ("Tested versions", tested),
    ]
    rows = "".join(
        f"<div><dt>{label}</dt><dd>{value}</dd></div>" for label, value in facts
    )
    return (
        "<header>\n<h1>tidyline report</h1>\n"
        f'<dl class="facts">{rows}</dl>\n'
        f'<p class="private"><strong>Personal data.</strong> {_e(PRIVATE_NOTICE)}</p>\n'
        "</header>"
    )


def _attention(data: ReportData) -> str:
    seen = data.attention
    if seen.warnings:
        checks = _plural(seen.warning_checks, "check")
        where = "in" if seen.warning_checks == 1 else "across"
        check, count = seen.largest
        text = (
            f"{_plural(seen.warnings, 'warning')} {where} {checks}; the largest "
            f"group is <code>{_e(check)}</code> ({count})."
        )
    else:
        text = "No warnings."
        if seen.info:
            text += (
                f" {_plural(seen.info, 'info finding')} in "
                f"{_plural(seen.info_checks, 'check')}."
            )
    return _section("first", "Look at this first", f'<p class="lead">{text}</p>')


def _glance(data: ReportData, include_completed: bool) -> str:
    counts = data.counts
    tiles = [
        ("Open to-dos", counts.open_todos),
        ("Open projects", counts.open_projects),
        ("Areas", counts.areas),
        (f"Completed in the last {RECENT_DAYS} days", counts.completed_recent),
        ("Live repeating to-dos", data.recurrence.live),
    ]
    body = (
        '<div class="tiles">\n'
        + "\n".join(
            f'<div class="tile"><span class="number">{number}</span>{_e(label)}</div>'
            for label, number in tiles
        )
        + "\n</div>"
    )
    if include_completed:
        rows = [
            (f"Completed in last {RECENT_DAYS} days", counts.completed_recent),
            ("Completed earlier", counts.completed_earlier),
            ("Completed, no date", counts.completed_undated),
            ("Completed projects", counts.completed_projects),
            ("Cancelled projects", counts.cancelled_projects),
            ("Trashed projects", counts.trashed_projects),
        ]
        body += (
            '\n<div class="closed"><h3>Closed items</h3>\n'
            '<div class="scroll cards"><table>\n'
            "<thead><tr><th>Item</th><th>Count</th></tr></thead>\n<tbody>\n"
            + "\n".join(
                f"<tr>{_cell('Item', _e(label))}{_cell('Count', str(number))}</tr>"
                for label, number in rows
            )
            + "\n</tbody></table></div></div>"
        )
    return _section("glance", "At a glance", body)


def _where(counts: Counts) -> str:
    labels = dict(STATUS_ORDER)
    entries = [(labels[state], number) for state, number in counts.by_status]
    summary = ", ".join(f"{name} {number}" for name, number in entries)
    segments = "".join(
        f'<span class="{STATUS_CLASSES[name]}" style="flex-grow: {number}" '
        f'title="{_e(name)}: {number}"></span>'
        for name, number in entries
        if number
    )
    legend = "\n".join(
        f'<li><span class="swatch {STATUS_CLASSES[name]}"></span>'
        f"{_e(name)} <strong>{number}</strong></li>"
        for name, number in entries
    )
    body = (
        f'<div class="bar" role="img" aria-label="Open to-dos by list: '
        f'{_e(summary)}">{segments}</div>\n'
        f'<ul class="legend">\n{legend}\n</ul>'
    )
    return _section("where", "Where your open to-dos sit", body)


def _checks(sections: Sequence[CheckSection]) -> str:
    ordered = sorted(sections, key=lambda s: s.severity != "warning")  # stable
    cards = "\n".join(_check_card(section) for section in ordered)
    return _section("checks", "Health checks", cards)


def _check_card(section: CheckSection) -> str:
    badge = f'<span class="badge {_e(section.severity)}">{_e(section.severity)}</span>'
    name = f'<code class="check-name">{_e(section.check)}</code>'
    if not section.findings:
        return (
            f'<div class="check empty">{badge} {name} '
            '<span class="muted">No findings</span></div>'
        )
    opened = " open" if section.severity == "warning" else ""
    parts = [
        f'<details class="check"{opened}>',
        f"<summary>{badge} {name} "
        f'<span class="muted">{_plural(section.findings, "finding")}</span></summary>',
        '<div class="check-body">',
    ]
    if section.message is not None:
        parts.append(f'<p class="message">{_e(section.message)}</p>')
    if section.layout == "groups":
        parts += [_group(group) for group in section.groups]
    else:
        parts.append(_items(section.items))
    parts.append(
        f'<p class="fix"><a href="{_e(fixing_link(section.check))}" '
        f'rel="noopener noreferrer">How to fix {_e(section.check)}</a></p>'
    )
    parts += ["</div>", "</details>"]
    return "\n".join(parts)


def _group(group: Group) -> str:
    count = _e(_plural(len(group.items), group.noun) + group.suffix)
    if group.place is None:
        heading = f'{_e(group.nowhere)} <span class="muted">({count})</span>'
    else:
        heading = (
            f"{_title(group.place.title)} "
            f'<span class="muted">({_e(group.place.kind)}, {count})</span>'
        )
    return (
        f'<div class="group">\n<p class="place">{heading}</p>\n'
        f"{_items(group.items)}\n</div>"
    )


def _items(items: Sequence[Item]) -> str:
    return (
        '<ul class="items">\n'
        + "\n".join(f"<li>{_item(item)}</li>" for item in items)
        + "\n</ul>"
    )


def _item(item: Item) -> str:
    text = " = ".join(_title(named.title) for named in item.things)
    if item.note is not None:
        text += f' <span class="note">&mdash; {_e(item.note)}</span>'
    return text


def _repeating(data: ReportData) -> str:
    counts = data.recurrence
    rows = [
        ("Live", counts.live),
        ("Leftover", counts.leftover),
        ("Recognised", counts.recognised),
        ("Assumed", counts.assumed),
    ]
    if counts.not_recognised:
        rows.append(("Not recognised", counts.not_recognised))
    figures = "".join(f"<div><dt>{label}</dt><dd>{n}</dd></div>" for label, n in rows)
    body = f'<dl class="counts">{figures}</dl>'
    if data.templates:
        body += (
            '\n<div class="scroll cards"><table>\n'
            "<thead><tr><th>Title</th><th>Place</th><th>Rule</th>"
            "<th>Confidence</th></tr></thead>\n<tbody>\n"
            + "\n".join(_template_row(row) for row in data.templates)
            + "\n</tbody></table></div>"
        )
    return _section("repeating", "Repeating to-dos", body)


def _template_row(row: TemplateRow) -> str:
    confidence = CONFIDENCE_WORDS.get(row.confidence, row.confidence)
    marked = row.confidence != "verified"
    shown = f"<strong>{_e(confidence)}</strong>" if marked else _e(confidence)
    attribute = ' class="marked"' if marked else ""
    return (
        f"<tr{attribute}>{_cell('Title', _title(row.title))}"
        f"{_cell('Place', _place(row.place))}{_cell('Rule', _e(row.headline))}"
        f"{_cell('Confidence', shown)}</tr>"
    )


def _cell(label: str, content: str) -> str:
    """A table cell that names its column, for the stacked cards at phone width."""
    return f'<td data-label="{_e(label)}">{content}</td>'


def _place(place: TemplatePlace) -> str:
    if place.kind == "none":
        return "no project or area"
    trashed = " (trashed)" if place.trashed else ""
    return f"{_e(place.kind)} {_title(place.title)}{trashed}"


def _warnings(warnings: Sequence[str]) -> str:
    if not warnings:
        body = "<p>None.</p>"
    else:
        body = (
            f"<p>{_plural(len(warnings), 'value')} could not be read cleanly:</p>\n"
            "<ul>\n"
            + "\n".join(f"<li>{_e(warning)}</li>" for warning in warnings)
            + "\n</ul>"
        )
    return _section("warnings", "Read warnings", body)


def _review() -> str:
    """Points at `prompt` and `decode`; plain text, no link (DESIGN.md 7.7)."""
    return (
        '<aside class="review">\n'
        f"<p><strong>{_e(REVIEW_HEADING)}</strong></p>\n"
        f"<p>{REVIEW_TEXT}</p>\n"
        "</aside>"
    )


def _footer(data: ReportData) -> str:
    return (
        "<footer>\n"
        f"<p>{_e(FOOTER.format(version=data.tool_version))}</p>\n"
        f"<p>{_e(NOT_AFFILIATED)}</p>\n"
        "</footer>"
    )


def _section(ident: str, heading: str, body: str) -> str:
    return (
        f'<section id="{ident}" aria-labelledby="{ident}-h">\n'
        f'<h2 id="{ident}-h">{_e(heading)}</h2>\n{body}\n</section>'
    )


def fixing_link(check: str) -> str:
    """The fixing guide, at the section for `check`. The guide's headings are
    "N. check_id (severity)", numbered in registry order; the anchor is
    GitHub's slug of that heading."""
    number = CHECK_IDS.index(check) + 1
    heading = f"{number}. {check} ({CHECKS[check].SEVERITY})"
    return f"{FIXING_GUIDE_URL}#{github_slug(heading)}"


def github_slug(heading: str) -> str:
    """The anchor GitHub gives a Markdown heading: lower case, punctuation
    other than hyphens and underscores removed, spaces made hyphens."""
    slug = re.sub(r"[^\w\- ]", "", heading.strip().lower())
    return slug.replace(" ", "-")
