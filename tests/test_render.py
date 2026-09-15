#!/usr/bin/env python3
"""Regression tests for the renderer, which is where the no-fabrication
guarantee is actually enforced.

Everything else in this repo is a prompt asking the agent to behave.
`format_brief.py` is the one place that refuses, so the cases that matter are
the ones where it must say no: a link nobody collected, a corroborating outlet
nobody collected, a story missing the field that makes it a brief rather than a
headline dump.

No test framework required:

    python3 tests/test_render.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tb-brief" / "scripts"))

import collect_news  # noqa: E402
import format_brief  # noqa: E402

FAILURES: list[str] = []


def check(condition: bool, label: str) -> None:
    print(f"  {'PASS' if condition else 'FAIL'}  {label}")
    if not condition:
        FAILURES.append(label)


REAL = "https://blog.rust-lang.org/2026/09/09/Rust-1.95.0/"
OTHER = "https://www.infoq.com/news/2026/09/rust-1-95/"
ALLOWED = {format_brief.canonical_url(REAL), format_brief.canonical_url(OTHER)}


def brief_with(**story_overrides) -> dict:
    story = {
        "id": "abc123",
        "title": "Rust 1.95 is released",
        "summary": "The release stabilises async closures.",
        "why_it_matters": "Your tokio services can drop a workaround.",
        "url": REAL,
        "source": "Rust Blog",
        "published": "2026-09-09T09:00:00+00:00",
    }
    story.update(story_overrides)
    return {
        "date": "2026-09-09",
        "owner": "Caio",
        "sections": [{"name": "Affects your stack", "stories": [story]}],
    }


def test_canonicalizer_parity() -> None:
    """The two implementations are compared to each other at runtime.

    `collect_news.py` canonicalises into candidates.json; `format_brief.py`
    canonicalises into history.json; `filter_news.py` matches one against the
    other to decide what the reader has already been sent. If they disagree on
    a single URL, that story is delivered twice and nothing reports it.
    """
    print("\nthe two canonicalisers agree, so history dedupe works")
    cases = [
        "https://www.theverge.com/2026/9/9/openai-gpt-5-5?utm_source=rss&utm_medium=feed",
        "https://techcrunch.com/2026/09/09/story/?mc_cid=abc123&mc_eid=def456",
        "https://www.bbc.co.uk/news/tech-123?at_medium=RSS&at_campaign=KARANGA",
        "https://example.com/post?ref=hn&id=42",
        "http://EXAMPLE.com/Path/",
        "https://blog.rust-lang.org/2026/09/09/Rust-1.95.0/?fbclid=x&gclid=y",
        "not a url at all",
        "",
    ]
    for url in cases:
        a = collect_news.canonical_url(url)
        b = format_brief.canonical_url(url)
        check(a == b, f"identical canonical form for {url[:52]!r}")


def test_unverified_links_are_refused() -> None:
    print("\na link nobody collected does not render")
    fake = "https://totally-invented-outlet.example/rust-1-95"

    check(format_brief.validate(brief_with(), ALLOWED) == [],
          "a story whose url was collected passes")

    problems = format_brief.validate(brief_with(url=fake), ALLOWED)
    check(any("not among the collected candidates" in p for p in problems),
          "a fabricated story url is rejected")

    problems = format_brief.validate(
        brief_with(also_covered_by=[{"source": "Invented Weekly", "url": fake}]), ALLOWED
    )
    check(any("also_covered_by" in p and "cannot be verified" in p for p in problems),
          "a fabricated corroborating outlet is rejected too")

    check(format_brief.validate(
        brief_with(also_covered_by=[{"source": "InfoQ", "url": OTHER}]), ALLOWED) == [],
        "a corroborating outlet that was collected passes")

    check(any("http(s)" in p for p in
              format_brief.validate(brief_with(url="javascript:alert(1)"), ALLOWED)),
          "a non-http scheme is rejected before it reaches the reader")

    check(format_brief.validate(brief_with(url=fake), None) == [],
          "with no shortlist to verify against, nothing is claimed about the url")


def test_required_fields() -> None:
    print("\nthe fields that make it a brief rather than a headline dump")
    for field in ("title", "summary", "why_it_matters", "source"):
        problems = format_brief.validate(brief_with(**{field: "  "}), ALLOWED)
        check(any(f"missing required field {field!r}" in p for p in problems),
              f"a blank {field} is rejected")


def test_continuity_rendering() -> None:
    """A story lifted from ranked.json carries continuity as an object."""
    print("\ncontinuity renders as prose, never as a Python repr")
    from_shortlist = {
        "previous_title": "Rust 1.94 is released",
        "previous_url": "https://blog.rust-lang.org/2026/08/07/Rust-1.94.0/",
        "previous_day": "2026-08-07",
        "similarity": 0.61,
    }
    markdown = format_brief.render(brief_with(continuity=from_shortlist))
    check("*Follow-up: develops Rust 1.94 is released, first sent 2026-08-07*" in markdown,
          "a continuity object becomes a sentence")
    check("similarity" not in markdown and "{" not in markdown,
          "no dict repr leaks into the delivered brief")

    markdown = format_brief.render(brief_with(continuity="the RC became the release"))
    check("*Follow-up: the RC became the release*" in markdown,
          "a continuity sentence is rendered as written")

    check("Follow-up" not in format_brief.render(brief_with()),
          "no continuity, no follow-up line")


def test_render_shape() -> None:
    print("\nthe rendered brief carries what the reader was promised")
    markdown = format_brief.render(
        brief_with(stack_matches=["rust"], also_covered_by=[{"source": "InfoQ", "url": OTHER}])
    )
    check(markdown.startswith("# Daily Tech Brief — 2026-09-09"), "dated heading")
    check("**Why it matters.** Your tokio services" in markdown, "why it matters is labelled")
    check(f"Source: [Rust Blog]({REAL})" in markdown, "the source is a link")
    check("2026-09-09 09:00 UTC" in markdown, "the publication date is shown")
    check("Touches: `rust`" in markdown, "stack matches are shown")
    check(f"Also covered by: [InfoQ]({OTHER})" in markdown, "corroboration is shown")


def main() -> int:
    test_canonicalizer_parity()
    test_unverified_links_are_refused()
    test_required_fields()
    test_continuity_rendering()
    test_render_shape()
    print()
    if FAILURES:
        print(f"{len(FAILURES)} failing check(s)")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())