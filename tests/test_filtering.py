#!/usr/bin/env python3
"""Regression tests for de-duplication and stack matching.

No test framework required, so it runs anywhere the skill runs:

    python3 tests/test_filtering.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tb-brief" / "scripts"))

from filter_news import (  # noqa: E402
    TITLE_SIMILARITY,
    build_term_index,
    cluster_items,
    match_stack,
    similar,
)

FAILURES: list[str] = []


def check(condition: bool, label: str) -> None:
    print(f"  {'PASS' if condition else 'FAIL'}  {label}")
    if not condition:
        FAILURES.append(label)


DEDUP_CASES = [
    # (title a, url a, title b, url b, should merge)
    ("OpenAI launches GPT-5.5 with a one million token context window",
     "https://techcrunch.com/2026/09/09/openai-launches-gpt-5-5-million-token-context/",
     "OpenAI Launches GPT-5.5, Adding a 1 Million Token Context Window",
     "https://www.theverge.com/2026/9/9/openai-gpt-5-5-million-token-context-window",
     True),
    ("Node.js 22.20.0 (LTS)", "https://nodejs.org/en/blog/release/v22.20.0",
     "Node.js 24.21.0 (LTS)", "https://nodejs.org/en/blog/release/v24.21.0",
     False),
    ("Rust 1.95 released", "https://blog.rust-lang.org/2026/09/01/Rust-1.95.0",
     "Announcing Rust 1.95.0", "https://www.infoq.com/news/2026/09/rust-1-95-released/",
     True),
    ("Critical CVE-2026-1234 in OpenSSL actively exploited",
     "https://krebsonsecurity.com/2026/09/openssl-cve-2026-1234",
     "OpenSSL flaw CVE-2026-1234 under active exploitation",
     "https://www.bleepingcomputer.com/news/security/openssl-flaw-exploited/",
     True),
    ("Anthropic ships Claude agent skills", "https://www.anthropic.com/news/agent-skills",
     "Docker announces hardened images", "https://www.docker.com/blog/hardened-images/",
     False),
    ("EU AI Act enforcement begins for general purpose models",
     "https://www.theregister.com/2026/09/09/eu_ai_act_gpai_enforcement/",
     "EU AI Act: enforcement phase starts for GPAI providers",
     "https://techcrunch.com/2026/09/09/eu-ai-act-gpai-enforcement-phase/",
     True),
    ("Kubernetes 1.36 released with in-place pod resize GA",
     "https://kubernetes.io/blog/2026/09/k8s-1-36",
     "Kubernetes 1.35 adds sidecar improvements",
     "https://kubernetes.io/blog/2026/05/k8s-1-35",
     False),
    ("Postgres 19 beta 1 is out", "https://www.postgresql.org/about/news/pg19b1",
     "MySQL 9.4 released", "https://dev.mysql.com/blog/mysql-9-4",
     False),
    ("CVE-2026-9999 patched in curl", "https://curl.se/docs/CVE-2026-9999.html",
     "CVE-2026-8888 patched in curl", "https://curl.se/docs/CVE-2026-8888.html",
     False),
    # Patch releases that differ only in the last digit are separate stories.
    ("Node.js 26.5.0 (Current)", "https://nodejs.org/en/blog/release/v26.5.0",
     "Node.js 26.5.1 (Current)", "https://nodejs.org/en/blog/release/v26.5.1",
     False),
    ("Node.js 26.0.0 (Current)", "https://nodejs.org/en/blog/release/v26.0.0",
     "Node.js 26.8.2 (Current)", "https://nodejs.org/en/blog/release/v26.8.2",
     False),
    # A headline that omits the patch number still names the same release.
    ("Go 1.27 is released", "https://go.dev/blog/go1.27",
     "Go 1.27.0 released with faster GC", "https://www.infoq.com/news/2026/09/go-1-27-released/",
     True),
]


def test_similarity() -> None:
    print("similarity thresholds")
    for title_a, url_a, title_b, url_b, should_merge in DEDUP_CASES:
        score = similar(title_a, title_b, url_a, url_b)
        merged = score >= TITLE_SIMILARITY
        check(merged == should_merge,
              f"{score:.3f} {'merge' if should_merge else 'separate':<8} {title_a[:52]}")


def test_clustering() -> None:
    print("\nclustering keeps the most authoritative source as primary")
    items = [
        {"id": "b", "title": "OpenAI ships GPT-5.5", "url": "https://techcrunch.com/openai-ships-gpt-5-5-model",
         "canonical_url": "https://techcrunch.com/openai-ships-gpt-5-5-model", "tier": 2,
         "source": "TechCrunch", "published": "2026-09-09T10:00:00+00:00", "summary": ""},
        {"id": "a", "title": "OpenAI Ships GPT-5.5", "url": "https://openai.com/index/openai-ships-gpt-5-5-model",
         "canonical_url": "https://openai.com/index/openai-ships-gpt-5-5-model", "tier": 1,
         "source": "OpenAI News", "published": "2026-09-09T09:00:00+00:00", "summary": ""},
        {"id": "c", "title": "Rust 1.95 released", "url": "https://blog.rust-lang.org/2026/09/01/Rust-1.95.0",
         "canonical_url": "https://blog.rust-lang.org/2026/09/01/Rust-1.95.0", "tier": 1,
         "source": "Rust Blog", "published": "2026-09-01T09:00:00+00:00", "summary": ""},
    ]
    clusters = cluster_items(items)
    check(len(clusters) == 2, f"three items collapse to two clusters (got {len(clusters)})")
    gpt = [c for c in clusters if "GPT" in c["primary"]["title"].upper()][0]
    check(gpt["primary"]["source"] == "OpenAI News",
          f"primary is the tier 1 source (got {gpt['primary']['source']})")
    check(len(gpt["members"]) == 2, "both outlets recorded as corroboration")


def test_stack_matching() -> None:
    print("\nstack matching")
    stack_map = {
        "python": ["python", "cpython", "django"],
        "aws": ["aws", "lambda", "s3"],
        "react": ["react", "jsx"],
    }
    index = build_term_index(stack_map, ["python", "aws", "react"])

    check(match_stack("Django 6.0 released with async ORM", index) == ["python"],
          "django headline matches python only")
    check(sorted(match_stack("AWS Lambda adds Python 3.14 runtime", index)) == ["aws", "python"],
          "headline spanning two tags matches both")
    check(match_stack("Reactor pattern explained", index) == [],
          "word boundary prevents 'reactor' matching 'react'")
    check(match_stack("Kubernetes 1.36 ships sidecar changes", index) == [],
          "unrelated headline matches nothing")

    literal = build_term_index(stack_map, ["elixir"])
    check(match_stack("Elixir 1.20 released", literal) == ["elixir"],
          "unmapped tag falls back to a literal term match")


def test_open_ended_terms_match_what_follows_them() -> None:
    """Half the shipped catalog is written to be followed by a version.

    `go 1.`, `git 2.`, `gpt-`, `cve-` all end where a number begins, and a
    blanket trailing `(?![a-z0-9])` forbade exactly the character that has to
    come next -- so none of them could ever match. A reader who declared `go`
    got nothing from "Go 1.25 is released". The same at the front: `.net`
    never matched "ASP.NET", because a letter precedes the dot.
    """
    print("\nterms that end where a version begins")
    stack_map = {
        "go": ["golang", "go 1.", "go module"],
        "openai": ["openai", "gpt-", "chatgpt"],
        "security": ["cve-", "vulnerability"],
        "csharp": ["c#", ".net", "dotnet"],
    }
    index = build_term_index(stack_map, ["go", "openai", "security", "csharp"])

    for headline, want in [
        ("Go 1.25 is released", ["go"]),
        ("OpenAI ships GPT-5.5 to the API", ["openai"]),
        ("CVE-2026-1234 is being actively exploited", ["security"]),
        ("ASP.NET Core 11 hits preview", ["csharp"]),
    ]:
        check(sorted(match_stack(headline, index)) == want,
              f"{headline!r} matches {want}")

    # The anchoring still has to hold where it was doing its job.
    for headline in ("Going to production with Postgres", "A gopher walks in",
                     "Algorithmic trading, explained"):
        check(match_stack(headline, index) == [],
              f"{headline!r} still matches nothing")


def test_the_shipped_keyword_catalog_is_matchable() -> None:
    """A term nothing can match is a mapping that silently does not exist.

    Catches the `fine-tun` / `es20` shape: written as a word prefix, which the
    matcher does not do, so the tag quietly lost that signal.
    """
    print("\nevery shipped term can match the text it is written for")
    catalog = json.loads(
        (ROOT / "tb-brief" / "references" / "stack-keywords.json").read_text(encoding="utf-8")
    )["stack"]
    unmatchable = [
        f"{tag}: {term!r}"
        for tag, terms in sorted(catalog.items())
        for term in terms
        # The term inside a sentence, which is how a headline carries it.
        if match_stack(f"today {term.strip()} landed", build_term_index({tag: [term]}, [tag]))
        != [tag]
    ]
    for entry in unmatchable:
        print(f"        {entry} cannot match its own text")
    check(not unmatchable,
          f"all {sum(len(t) for t in catalog.values())} mapped terms are matchable")


def main() -> int:
    test_similarity()
    test_clustering()
    test_stack_matching()
    test_open_ended_terms_match_what_follows_them()
    test_the_shipped_keyword_catalog_is_matchable()
    print()
    if FAILURES:
        print(f"{len(FAILURES)} failing check(s)")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())