"""The HTML report renderer (DESIGN.md 7.7), against the synthetic fixture only.

To regenerate the golden file after a deliberate change, run

    TIDYLINE_UPDATE_GOLDEN=1 uv run pytest tests/test_html_report.py

and review the diff before committing.
"""

import datetime as dt
import html
import os
import re
from html.parser import HTMLParser
from pathlib import Path

import pytest
from checks_helpers import U, edit, set_title, snapshot_of

from tidyline.checks import CHECK_IDS
from tidyline.render import html_out
from tidyline.render.check_out import FIXING_GUIDE_URL, safe_title
from tidyline.render.html_out import CSS, fixing_link, github_slug, render_html
from tidyline.render.text import ReportOptions, render_report
from tidyline.report_data import Attention

TODAY = dt.date(2026, 10, 10)
ENVIRONMENT = {
    "macos": "27.0.1",
    "things_version": "3.24.1",
    "database_version": 29,
    "tested": True,
}
GOLDEN = Path(__file__).parent / "fixtures" / "report_golden.html"
GUIDE = Path(__file__).parents[1] / "docs" / "FIXING_PROBLEMS.md"
ALLOWED_TAGS = {
    "html", "head", "meta", "title", "style", "body", "div", "header", "h1",
    "h2", "h3", "dl", "dt", "dd", "p", "strong", "main", "section", "span",
    "ul", "li", "details", "summary", "code", "bdi", "a", "table", "thead",
    "tbody", "tr", "th", "td", "footer",
}  # fmt: skip


def html_of(path, **options):
    return render_html(
        snapshot_of(path),
        today=TODAY,
        tool_version="0.3.0",
        environment=ENVIRONMENT,
        **options,
    )


def text_of(path, **options):
    return render_report(
        snapshot_of(path),
        today=TODAY,
        tool_version="0.3.0",
        environment=ENVIRONMENT,
        options=ReportOptions(**options),
    )


class Page(HTMLParser):
    """Every start tag with its attributes, and the text, unescaped."""

    def __init__(self, source):
        super().__init__(convert_charrefs=True)
        self.tags = []
        self.text = []
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))

    def handle_startendtag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))

    def handle_data(self, data):
        self.text.append(data)

    def all_text(self):
        return "".join(self.text)


# --- golden ---------------------------------------------------------------------


def test_matches_golden(fixture_db):
    page = html_of(fixture_db)
    if os.environ.get("TIDYLINE_UPDATE_GOLDEN"):
        GOLDEN.write_text(page, encoding="utf-8")
    assert page == GOLDEN.read_text(encoding="utf-8")


# --- safety ---------------------------------------------------------------------

HOSTILE = {
    "project": "<script>alert(1)</script> & co",
    "heading": '"><img src=x onerror=alert(1)>',
    "to-do": "javascript:alert('x') &amp; <b>bold</b>",
    "area": 'Home & "Garden" <iframe src="https://example.com">',
    "template": "‮evil‬ <style>body{display:none}</style>\u0007  é́",
}


@pytest.fixture
def hostile_db(fixture_db):
    set_title(fixture_db, "proj_garden", HOSTILE["project"])
    set_title(fixture_db, "head_plan", HOSTILE["heading"])
    set_title(fixture_db, "t_cables", HOSTILE["to-do"])
    set_title(fixture_db, "tpl_daily", HOSTILE["template"])
    edit(
        fixture_db,
        (
            "UPDATE TMArea SET title = ? WHERE uuid = ?",
            (HOSTILE["area"], U("area_home")),
        ),
        # a trashed heading puts its title (and its to-dos) in the report
        ("UPDATE TMTask SET trashed = 1 WHERE uuid = ?", (U("head_plan"),)),
    )
    return fixture_db


def test_hostile_titles_are_escaped(hostile_db):
    source = html_of(hostile_db)
    page = Page(source)
    assert {tag for tag, _ in page.tags} <= ALLOWED_TAGS
    assert not re.search(r"<\s*script", source, re.I)
    assert source.count("<style>") == 1
    for kind, title in HOSTILE.items():
        assert html.escape(safe_title(title), quote=True) in source, kind
        assert safe_title(title) in page.all_text(), kind
    for _, attrs in page.tags:
        assert not any(name.startswith("on") for name in attrs)
        assert "src" not in attrs
        if "href" in attrs:
            assert attrs["href"].startswith(FIXING_GUIDE_URL + "#")


def test_control_characters_are_replaced(hostile_db):
    assert "\u0007" not in html_of(hostile_db)


def test_no_external_resources(fixture_db):
    source = html_of(fixture_db, include_completed=True)
    lowered = source.lower()
    for forbidden in ("src=", "<link", "@import", "url(", "<script", "<img"):
        assert forbidden not in lowered, forbidden
    page = Page(source)
    hrefs = [attrs["href"] for tag, attrs in page.tags if tag == "a"]
    assert len(hrefs) == len(CHECK_IDS)  # every check has findings here
    for tag, attrs in page.tags:
        if tag == "a":
            assert attrs["rel"] == "noopener noreferrer"
    without_links = re.sub(r'href="[^"]*"', "", source)
    assert not re.search(r"https?:", without_links)


def test_content_security_policy(fixture_db):
    page = Page(html_of(fixture_db))
    csp = [
        attrs["content"]
        for tag, attrs in page.tags
        if tag == "meta" and attrs.get("http-equiv") == "Content-Security-Policy"
    ]
    assert csp == [
        "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; "
        "form-action 'none'"
    ]


def test_document_basics(fixture_db):
    source = html_of(fixture_db)
    assert source.startswith('<!DOCTYPE html>\n<html lang="en">\n')
    assert "<title>tidyline report, 2026-10-10</title>" in source
    assert 'name="viewport"' in source
    assert "prefers-color-scheme: dark" in source


# --- content ----------------------------------------------------------------------


def test_sections_in_order(fixture_db):
    headings = re.findall(r"<h2[^>]*>([^<]+)</h2>", html_of(fixture_db))
    assert headings == [
        "Look at this first",
        "At a glance",
        "Where your open to-dos sit",
        "Health checks",
        "Repeating to-dos",
        "Read warnings",
    ]


def test_warnings_open_and_info_closed(fixture_db):
    source = html_of(fixture_db)
    cards = re.findall(
        r'<details class="check"( open)?>\n<summary><span class="badge (\w+)"', source
    )
    assert cards and all(
        (opened == " open") == (sev == "warning") for opened, sev in cards
    )
    severities = [sev for _, sev in cards]
    assert severities == sorted(severities, key=lambda s: s != "warning")


def test_check_with_no_findings_is_one_row(fixture_db):
    edit(
        fixture_db,
        (
            "UPDATE TMTask SET title = ? WHERE uuid = ?",
            ("Pay the gas bill", U("t_dup_b")),
        ),
    )
    source = html_of(fixture_db)
    assert (
        '<div class="check empty"><span class="badge warning">warning</span> '
        '<code class="check-name">possible_duplicates</code> '
        '<span class="muted">No findings</span></div>'
    ) in source


def test_look_at_this_first_without_warnings():
    data = type("D", (), {"attention": Attention(0, 0, 3, 2, None)})
    assert "No warnings. 3 info findings in 2 checks." in html_out._attention(data)
    data.attention = Attention(0, 0, 0, 0, None)
    assert '<p class="lead">No warnings.</p>' in html_out._attention(data)


def test_look_at_this_first_names_the_largest_group(fixture_db):
    assert (
        "16 warnings across 7 checks; the largest group is "
        "<code>open_in_trashed_project</code> (3)."
    ) in html_of(fixture_db)


def test_include_completed_adds_the_closed_items_table(fixture_db):
    assert "Closed items" not in html_of(fixture_db)
    assert "<h3>Closed items</h3>" in html_of(fixture_db, include_completed=True)


def test_fixing_links_point_at_the_guide_sections():
    slugs = {
        github_slug(line[4:])
        for line in GUIDE.read_text(encoding="utf-8").splitlines()
        if line.startswith("### ")
    }
    for check in CHECK_IDS:
        url = fixing_link(check)
        assert url.startswith(FIXING_GUIDE_URL + "#")
        assert url.split("#", 1)[1] in slugs, check


# --- numbers equal the text report ------------------------------------------------


def text_value(text, label):
    match = re.search(rf"^\s*{re.escape(label)}\s{{2,}}(\S+)", text, re.M)
    assert match, label
    return match.group(1)


def test_numbers_equal_the_text_report(fixture_db):
    text = text_of(fixture_db, include_completed=True)
    source = html_of(fixture_db, include_completed=True)

    tiles = dict(
        (label, number)
        for number, label in re.findall(
            r'<div class="tile"><span class="number">(\d+)</span>([^<]+)</div>', source
        )
    )
    assert tiles["Open to-dos"] == text_value(text, "Open to-dos")
    assert tiles["Open projects"] == text_value(text, "Projects (open)")
    assert tiles["Areas"] == text_value(text, "Areas")
    assert tiles["Completed in the last 30 days"] == text_value(
        text, "Completed in last 30 days"
    )
    recurring = text.split("Recurring templates\n", 1)[1]
    assert tiles["Live repeating to-dos"] == text_value(recurring, "Live")

    legend = dict(
        re.findall(
            r'<li><span class="swatch \w+"></span>([^<]+) <strong>(\d+)</strong></li>',
            source,
        )
    )
    for name in ("Inbox", "Today", "This Evening", "Upcoming", "Anytime", "Someday"):
        assert legend[name] == text_value(text, name), name

    counts = dict(re.findall(r"<div><dt>([^<]+)</dt><dd>(\d+)</dd></div>", source))
    for label in ("Live", "Leftover", "Recognised", "Assumed", "Not recognised"):
        assert counts[label] == text_value(recurring, label), label

    for check in CHECK_IDS:
        severity, number = re.search(rf"^{check}\s+(\w+)\s+(\d+)$", text, re.M).groups()
        card = re.search(
            rf'<span class="badge {severity}">{severity}</span> '
            rf'<code class="check-name">{check}</code> '
            rf'<span class="muted">(\d+) findings?</span>',
            source,
        )
        assert card and card.group(1) == number, check


# --- contrast ---------------------------------------------------------------------


def variables(block):
    return dict(re.findall(r"--([\w-]+):\s*(#[0-9a-f]{6})", block))


def luminance(colour):
    channels = [int(colour[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [
        c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels
    ]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(a, b):
    high, low = sorted((luminance(a), luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_text_contrast_is_at_least_4_5(theme):
    light_block, dark_block = CSS.split("@media (prefers-color-scheme: dark)", 1)
    colours = variables(light_block)
    if theme == "dark":
        colours.update(variables(dark_block.split("}", 1)[0]))
    pairs = [
        (text, background)
        for text in ("fg", "muted", "link")
        for background in ("bg", "card", "mark-bg")
    ] + [("warn-fg", "warn-bg"), ("info-fg", "info-bg")]
    for text, background in pairs:
        ratio = contrast(colours[text], colours[background])
        assert ratio >= 4.5, (theme, text, background, round(ratio, 2))
