#!/usr/bin/env python3
"""Regression tests for feed parsing — the step everything downstream trusts.

Collection is the only part of the pipeline that touches the open web, and it
is the one part with no way to tell a bad day from a bug: a feed shape it
cannot read produces zero items, which is indistinguishable from a quiet news
day. So the shapes real publishers ship are pinned here rather than discovered
on a morning the brief arrives empty.

Nothing here goes to the network. Feeds are fixtures.

No test framework required:

    python3 tests/test_collect.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tb-brief" / "scripts"))

import collect_news  # noqa: E402

FAILURES: list[str] = []


def check(condition: bool, label: str) -> None:
    print(f"  {'PASS' if condition else 'FAIL'}  {label}")
    if not condition:
        FAILURES.append(label)


RSS2 = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/">
  <channel>
    <item>
      <title>Rust 1.95 is released</title>
      <link>https://blog.rust-lang.org/2026/09/09/Rust-1.95.0/</link>
      <description>&lt;p&gt;The release stabilises async closures.&lt;/p&gt;</description>
      <pubDate>Tue, 09 Sep 2026 09:00:00 +0000</pubDate>
    </item>
  </channel>
</rss>"""

# RSS 1.0. Same element names, declared in the RSS 1.0 namespace instead of
# none, which is the whole difference and the whole bug.
RDF = b"""<?xml version="1.0" encoding="UTF-8"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns="http://purl.org/rss/1.0/"
         xmlns:dc="http://purl.org/dc/elements/1.1/">
  <item rdf:about="https://example.org/a">
    <title>An RDF feed still carries stories</title>
    <link>https://example.org/a</link>
    <description>Body text.</description>
    <dc:date>2026-09-09T09:00:00Z</dc:date>
  </item>
</rdf:RDF>"""

ATOM = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>Go 1.25 is released</title>
    <link rel="self" href="https://go.dev/feed.atom"/>
    <link rel="alternate" href="https://go.dev/blog/go1.25"/>
    <summary>What is new in this release.</summary>
    <updated>2026-09-09T09:00:00Z</updated>
  </entry>
</feed>"""

GUID_ONLY = b"""<rss version="2.0"><channel><item>
  <title>Some feeds put the permalink in guid</title>
  <guid isPermaLink="true">https://example.org/g</guid>
</item></channel></rss>"""


def test_the_three_feed_shapes_publishers_actually_ship() -> None:
    print("\nRSS 2.0, RSS 1.0 and Atom all yield linked items")
    rss = collect_news.parse_feed(RSS2)
    check(len(rss) == 1 and rss[0]["url"].endswith("Rust-1.95.0/"), "RSS 2.0 item and link")
    check(rss[0]["summary"] == "The release stabilises async closures.",
          "the description is unwrapped from its HTML")

    # An item with no URL is dropped as unusable further down, so an RDF feed
    # read without namespaces contributed nothing at all, silently.
    rdf = collect_news.parse_feed(RDF)
    check(len(rdf) == 1 and rdf[0]["url"] == "https://example.org/a",
          "RSS 1.0 (RDF) items carry their link, not an empty string")
    check(rdf[0]["published_raw"] == "2026-09-09T09:00:00Z", "and their dc:date")

    atom = collect_news.parse_feed(ATOM)
    check(len(atom) == 1 and atom[0]["url"] == "https://go.dev/blog/go1.25",
          "Atom prefers rel=alternate over rel=self")

    guid = collect_news.parse_feed(GUID_ONLY)
    check(len(guid) == 1 and guid[0]["url"] == "https://example.org/g",
          "a permalink guid stands in for a missing link")


def test_entities_are_decoded_not_printed() -> None:
    """Newsrooms publish curly quotes and dashes as named entities.

    A six-entry replacement table left every one of them in the headline as
    raw source, so the brief read `AI&rsquo;s &ldquo;big&rdquo; leap`.
    """
    print("\nHTML entities reach the brief as characters")
    got = collect_news.strip_html(
        "AI&rsquo;s &ldquo;big&rdquo; leap &hellip; R&amp;D &mdash; caf&#xe9; &#8212; &#39;26"
    )
    want = "AI’s “big” leap … R&D — café — '26"
    check(got == want, f"named, numeric and hex entities all decode (got {got!r})")
    check("&" not in got.replace("R&D", ""), "no entity survives as source")
    check(collect_news.strip_html("<p>a<script>var x=1;</script>b</p>") == "a b",
          "script bodies are dropped, not read as text")


def test_dates_and_urls() -> None:
    print("\ndates parse and URLs canonicalise")
    check(collect_news.parse_date("Tue, 09 Sep 2026 09:00:00 +0000") is not None, "RFC 822")
    check(collect_news.parse_date("2026-09-09T09:00:00Z") is not None, "ISO 8601 with Z")
    check(collect_news.parse_date("2026-09-09") is not None, "a bare date")
    check(collect_news.parse_date("not a date") is None, "and nonsense is None, not a guess")
    naive = collect_news.parse_date("2026-09-09T09:00:00")
    check(naive is not None and naive.tzinfo is not None,
          "a naive timestamp is read as UTC, so the window comparison works")

    check(collect_news.canonical_url("https://WWW.Example.com/a/?utm_source=rss&id=1")
          == "https://example.com/a?id=1",
          "tracking parameters go, real ones stay")


def test_the_shipped_catalog_is_well_formed() -> None:
    """Ranking trusts `tier` and personalisation trusts `stack`. A typo in
    either is a feed that quietly scores wrong for every reader."""
    print("\nthe shipped feed catalog holds its own shape")
    catalog = json.loads(
        (ROOT / "tb-brief" / "references" / "feeds.json").read_text(encoding="utf-8")
    )["feeds"]
    valid_topics = {"ai", "tech", "devtools", "cloud", "security", "startups", "research"}

    ids = [feed["id"] for feed in catalog]
    check(len(ids) == len(set(ids)), "feed ids are unique")
    check(all(set(feed) >= {"id", "name", "url", "tier", "topics"} for feed in catalog),
          "every feed carries id, name, url, tier and topics")
    check(all(feed["tier"] in (1, 2, 3) for feed in catalog), "every tier is 1, 2 or 3")
    check(all(feed["url"].startswith(("http://", "https://")) for feed in catalog),
          "every url is http(s)")
    unknown = sorted({t for feed in catalog for t in feed["topics"]} - valid_topics)
    check(not unknown, f"topics come from the documented set (stray: {unknown})")


def main() -> int:
    test_the_three_feed_shapes_publishers_actually_ship()
    test_entities_are_decoded_not_printed()
    test_dates_and_urls()
    test_the_shipped_catalog_is_well_formed()
    print()
    if FAILURES:
        print(f"{len(FAILURES)} failing check(s)")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())