#!/usr/bin/env python3
"""Render the agent's brief into Markdown, verify its sources, and archive it.

The agent writes the editorial judgement as JSON; this script owns everything
that must not be left to judgement:

  * every story carries a real link that came from the collected candidates,
    which is what stops a fabricated source from ever reaching the reader
  * the file lands in a dated archive
  * delivered stories are recorded in history.json so tomorrow's run can skip
    them and recognise follow-ups

Standard library only.

Usage:
    format_brief.py --in brief.json --verify-against ranked.json \
        --outdir ~/.hermes/tech-brief --history ~/.hermes/tech-brief/history.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

REQUIRED_STORY_FIELDS = ("title", "summary", "why_it_matters", "url", "source")

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

def default_outdir() -> Path:
    """Archive under the agent's home, which is where its state belongs.

    HERMES_HOME is set inside the container and is the only place that
    survives a rebuild, because it is the mounted volume.
    """
    import os
    home = os.environ.get("HERMES_HOME")
    return (Path(home) if home else Path.home()) / "tb"

# validation

TRACKING_PARAMS = re.compile(
    r"^(utm_[a-z_]+|ref|ref_src|source|fbclid|gclid|mc_cid|mc_eid|at_medium|at_campaign)$",
    re.IGNORECASE,
)

def canonical_url(url: str) -> str:
    """Mirror of collect_news.canonical_url, kept local so each script stands alone."""
    url = (url or "").strip()
    if not url:
        return ""
    try:
        parts = urllib.parse.urlsplit(url)
    except ValueError:
        return url
    netloc = parts.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    query = [
        (k, v)
        for k, v in urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
        if not TRACKING_PARAMS.match(k)
    ]
    path = parts.path.rstrip("/") or "/"
    return urllib.parse.urlunsplit(
        (parts.scheme.lower() or "https", netloc, path, urllib.parse.urlencode(query), "")
    )


def iter_stories(brief: dict):
    for section in brief.get("sections", []):
        for story in section.get("stories", []):
            yield section, story


def validate(brief: dict, allowed: set[str] | None) -> list[str]:
    problems: list[str] = []
    if not brief.get("sections"):
        problems.append("brief has no sections")

    ate = str(brief.get("date", "")).strip()
    if date and not DATE_RE.match(date):
        problems.append(f"date must be YYYY-MM-DD, got {date!r}")

    for section, story in iter_stories(brief):
        label = story.get("title") or "<untitled story>"
        for field in REQUIRED_STORY_FIELDS:
            if not str(story.get(field, "")).strip():
                problems.append(f"{label!r}: missing required field {field!r}")

        url = str(story.get("url", "")).strip()
        if url and not url.lower().startswith(("http://", "https://")):
            problems.append(f"{label!r}: url is not an http(s) link: {url}")
        elif url and allowed is not None and canonical_url(url) not in allowed:
            problems.append(
                f"{label!r}: url was not among the collected candidates, so it cannot be "
                f"verified: {url}"
            )

        for other in story.get("also_covered_by") or []:
            if not isinstance(other, dict):
                problems.append(f"{label!r}: also_covered_by entries must be objects")
                continue
            other_url = str(other.get("url", "")).strip()
            if not other_url:
                continue
            if not other_url.lower().startswith(("http://", "https://")):
                problems.append(
                    f"{label!r}: also_covered_by url is not an http(s) link: {other_url}"
                )
            elif allowed is not None and canonical_url(other_url) not in allowed:
                problems.append(
                    f"{label!r}: also_covered_by url was not among the collected candidates, "
                    f"so it cannot be verified: {other_url}"
                )

        if not str(section.get("name", "")).strip():
            problems.append(f"{label!r}: belongs to a section with no name")
    return problems

# rendering

def format_date(raw: str | None) -> str:
    if not raw:
        return ""
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M UTC")
    except ValueError:
        return raw


def continuity_line(raw) -> str:
    """The contract asks for a sentence; ranked.json carries a dict.

    `filter_news.py` writes `continuity` as {previous_title, previous_url,
    previous_day, similarity}, and a story copied across from the shortlist
    brings that object with it. Rendering it through str() put a Python repr --
    braces, quotes and a similarity float -- into a brief somebody reads over
    breakfast. Prose is still what we want, so a dict is turned into a sentence
    rather than rejected.
    """
    if not raw:
        return ""
    if isinstance(raw, dict):
        title = str(raw.get("previous_title", "")).strip()
        day = str(raw.get("previous_day", "")).strip()
        if not title:
            return ""
        return f"develops {title}" + (f", first sent {day}" if day else "")
    return str(raw).strip()


def render(brief: dict) -> str:
    date = brief.get("date") or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lines: list[str] = [f"# Daily Tech Brief — {date}", ""]

    owner = str(brief.get("owner", "")).strip()
    stack = brief.get("stack") or []
    meta = []
    if owner:
        meta.append(f"For {owner}")
    if stack:
        meta.append("Stack: " + ", ".join(stack))
    if brief.get("window_hours"):
        meta.append(f"Window: last {brief['window_hours']}h")
    if meta:
        lines += ["*" + " · ".join(meta) + "*", ""]

    if brief.get("headline"):
        lines += [f"**{brief['headline'].strip()}**", ""]

    for section in brief.get("sections", []):
        stories = section.get("stories", [])
        if not stories:
            continue
        lines += [f"## {section['name']}", ""]
        for story in stories:
            lines.append(f"### {story['title'].strip()}")
            lines.append("")
            lines.append(story["summary"].strip())
            lines.append("")
            lines.append(f"**Why it matters.** {story['why_it_matters'].strip()}")
            lines.append("")

            continuity = continuity_line(story.get("continuity"))
            if continuity:
                lines += [f"*Follow-up: {continuity}*", ""]

            tags = story.get("stack_matches") or []
            if tags:
                lines += ["Touches: " + ", ".join(f"`{t}`" for t in tags), ""]

            published = format_date(story.get("published"))
            source_line = f"Source: [{story['source'].strip()}]({story['url'].strip()})"
            if published:
                source_line += f" · {published}"
            lines.append(source_line)

            for other in story.get("also_covered_by", []) or []:
                if isinstance(other, dict) and other.get("url"):
                    lines.append(f"Also covered by: [{other.get('source', 'link')}]({other['url']})")
            lines.append("")

    watchlist = brief.get("watchlist") or []
    if watchlist:
        lines += ["## Watchlist", ""]
        lines += [f"- {str(item).strip()}" for item in watchlist]
        lines.append("")

    if brief.get("notes"):
        lines += ["---", "", f"*{str(brief['notes']).strip()}*", ""]

    return "\n".join(lines).rstrip() + "\n"

# archive and history

def update_history(path: Path, brief: dict, date: str) -> int:
    try:
        history = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except (json.JSONDecodeError, OSError):
        history = {}
    history.setdefault("version", 1)
    stories = history.setdefault("stories", {})

    now = datetime.now(timezone.utc).isoformat()
    added = 0
    for _, story in iter_stories(brief):
        url = canonical_url(story.get("url", ""))
        key = story.get("id") or url
        if not key:
            continue
        record = stories.get(key)
        if record:
            record["last_seen"] = now
        else:
            stories[key] = {
                "title": story.get("title", ""),
                "url": url,
                "source": story.get("source", ""),
                "day": date,
                "first_seen": now,
                "last_seen": now,
            }
            added += 1

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(history, indent=2, ensure_ascii=False), encoding="utf-8")
    return added


def update_index(outdir: Path) -> None:
    briefs = sorted((p for p in outdir.glob("[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9].md")), reverse=True)
    lines = ["# Brief archive", ""]
    lines += [f"- [{p.stem}]({p.name})" for p in briefs]
    (outdir / "index.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

# main

def main() -> int:
    parser = argparse.ArgumentParser(description="Render, verify and archive the daily brief.")
    parser.add_argument("--in", dest="infile", type=Path, required=True, help="brief JSON written by the agent")
    parser.add_argument("--outdir", type=Path, default=default_outdir())
    parser.add_argument("--history", type=Path, help="history.json to update (default: <outdir>/history.json)")
    parser.add_argument("--verify-against", type=Path,
                        help="ranked.json from filter_news.py; every story URL must appear in it")
    parser.add_argument("--allow-unverified", action="store_true",
                        help="downgrade unknown-URL errors to warnings")
    parser.add_argument("--no-archive", action="store_true", help="print the brief without writing files")
    parser.add_argument("--quiet", action="store_true", help="do not echo the Markdown to stdout")
    args = parser.parse_args()

    if not args.infile.exists():
        print(f"brief not found: {args.infile}", file=sys.stderr)
        return 2
    try:
        brief = json.loads(args.infile.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"brief is not valid JSON: {exc}", file=sys.stderr)
        return 2

    allowed: set[str] | None = None
    if args.verify_against:
        if not args.verify_against.exists():
            print(
                f"cannot verify: {args.verify_against} does not exist. Run filter_news.py "
                "first, or drop --verify-against to render without checking the links.",
                file=sys.stderr,
            )
            return 2
        try:
            ranked = json.loads(args.verify_against.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            print(f"cannot verify: {args.verify_against} is unreadable: {exc}", file=sys.stderr)
            return 2
        allowed = set()
        for story in ranked.get("stories", []):
            allowed.add(story.get("canonical_url") or canonical_url(story.get("url", "")))
            for other in story.get("also_covered_by", []):
                allowed.add(canonical_url(other.get("url", "")))
        allowed.discard("")
        if not allowed:
            print(
                f"cannot verify: {args.verify_against} carries no story URLs, so every link "
                "in the brief would be rejected. Re-run the collect and rank steps.",
                file=sys.stderr,
            )
            return 2

    problems = validate(brief, allowed)
    unverified = [p for p in problems if "not among the collected candidates" in p]
    hard = [p for p in problems if p not in unverified]
    if args.allow_unverified:
        for warning in unverified:
            print(f"warning: {warning}", file=sys.stderr)
        unverified = []

    if hard or unverified:
        print("brief rejected:", file=sys.stderr)
        for problem in hard + unverified:
            print(f"  - {problem}", file=sys.stderr)
        return 1

    date = brief.get("date") or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    markdown = render(brief)

    if not args.quiet:
        print(markdown)

    if args.no_archive:
        return 0

    args.outdir.mkdir(parents=True, exist_ok=True)
    target = args.outdir / f"{date}.md"
    target.write_text(markdown, encoding="utf-8")
    added = update_history(args.history or (args.outdir / "history.json"), brief, date)
    update_index(args.outdir)

    story_count = sum(1 for _ in iter_stories(brief))
    print(f"saved {story_count} stories to {target} ({added} new in history)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())