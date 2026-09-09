#!/usr/bin/env python3
"""Collect candidate stories from the curated feed catalog.

Standard library only, so the skill installs and runs with nothing but
python3. Every feed is fetched independently; a dead or malformed feed is
recorded and skipped, never fatal.

Usage:
    collect_news.py --hours 24 --out candidates.json
    collect_news.py --check-feeds
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

USER_AGENT = "hermes-daily-tech-brief/1.0 (+https://github.com/caiovisuals/hermes-daily-tech-brief)"
DEFAULT_TIMEOUT = 15
DEFAULT_WORKERS = 12
SUMMARY_CHARS = 600

# Tracking parameters that change per-visit and would defeat de-duplication.
TRACKING_PARAMS = re.compile(
    r"^(utm_[a-z_]+|ref|ref_src|source|fbclid|gclid|mc_cid|mc_eid|at_medium|at_campaign)$",
    re.IGNORECASE,
)

ATOM = "{http://www.w3.org/2005/Atom}"
DC = "{http://purl.org/dc/elements/1.1/}"
CONTENT = "{http://purl.org/rss/1.0/modules/content/}"

# helpers

def skill_root() -> Path:
    """The skill directory, whether running from the image or a reconciled home."""
    return Path(__file__).resolve().parent.parent


def load_catalog(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data["feeds"]


def canonical_url(url: str) -> str:
    """Strip tracking noise so the same story from two feeds collapses to one key."""
    url = (url or "").strip()
    if not url:
        return ""
    try:
        parts = urllib.parse.urlsplit(url)
    except ValueError:
        return url
    query = [
        (k, v)
        for k, v in urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
        if not TRACKING_PARAMS.match(k)
    ]
    netloc = parts.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    path = parts.path.rstrip("/") or "/"
    return urllib.parse.urlunsplit(
        (parts.scheme.lower() or "https", netloc, path, urllib.parse.urlencode(query), "")
    )


def story_id(url: str, title: str) -> str:
    key = canonical_url(url) or title.strip().lower()
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


def strip_html(raw: str) -> str:
    if not raw:
        return ""
    text = re.sub(r"(?is)<(script|style).*?</\1>", " ", raw)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = (
        text.replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
    )
    text = re.sub(r"&#(\d+);", lambda m: chr(int(m.group(1))), text)
    return re.sub(r"\s+", " ", text).strip()


def parse_date(raw: str | None) -> datetime | None:
    if not raw:
        return None
    raw = raw.strip()
    try:
        dt = parsedate_to_datetime(raw)
        if dt is not None:
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError, IndexError):
        pass
    candidate = raw.replace("Z", "+00:00")
    for attempt in (candidate, candidate[:19], candidate[:10]):
        try:
            dt = datetime.fromisoformat(attempt)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def fetch(url: str, timeout: int) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
            "Accept-Encoding": "gzip",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = response.read()
    if payload[:2] == b"\x1f\x8b":
        payload = gzip.decompress(payload)
    return payload

# feed parsing

def _text(node) -> str:
    if node is None:
        return ""
    return strip_html("".join(node.itertext()))


def _atom_link(entry) -> str:
    fallback = ""
    for link in entry.findall(f"{ATOM}link"):
        rel = link.get("rel", "alternate")
        href = link.get("href", "")
        if not href:
            continue
        if rel == "alternate":
            return href
        fallback = fallback or href
    return fallback


def parse_feed(payload: bytes) -> list[dict]:
    root = ET.fromstring(payload)
    entries: list[dict] = []

    # RSS 2.0 / RDF
    for item in root.iter():
        tag = item.tag.split("}")[-1]
        if tag != "item":
            continue
        title = _text(item.find("title"))
        link = _text(item.find("link")) or (item.find("link").get("href") if item.find("link") is not None else "")
        if not link:
            guid = item.find("guid")
            if guid is not None and (guid.get("isPermaLink") or "true") == "true":
                link = _text(guid)
        summary = _text(item.find("description")) or _text(item.find(f"{CONTENT}encoded"))
        published = _text(item.find("pubDate")) or _text(item.find(f"{DC}date"))
        if title or link:
            entries.append({"title": title, "url": link, "summary": summary, "published_raw": published})

    if entries:
        return entries

    # Atom
    for entry in root.iter(f"{ATOM}entry"):
        entries.append(
            {
                "title": _text(entry.find(f"{ATOM}title")),
                "url": _atom_link(entry),
                "summary": _text(entry.find(f"{ATOM}summary")) or _text(entry.find(f"{ATOM}content")),
                "published_raw": _text(entry.find(f"{ATOM}published")) or _text(entry.find(f"{ATOM}updated")),
            }
        )
    return entries


def collect_feed(feed: dict, timeout: int) -> dict:
    result = {"feed": feed["id"], "name": feed["name"], "url": feed["url"], "items": [], "error": None}
    try:
        payload = fetch(feed["url"], timeout)
        raw_entries = parse_feed(payload)
    except urllib.error.HTTPError as exc:
        result["error"] = f"HTTP {exc.code}"
        return result
    except urllib.error.URLError as exc:
        result["error"] = f"network: {exc.reason}"
        return result
    except ET.ParseError as exc:
        result["error"] = f"malformed XML: {exc}"
        return result
    except Exception as exc:  # a single bad feed must never take the run down
        result["error"] = f"{type(exc).__name__}: {exc}"
        return result

    for entry in raw_entries:
        title = entry["title"].strip()
        url = entry["url"].strip()
        if not title or not url:
            continue
        published = parse_date(entry["published_raw"])
        result["items"].append(
            {
                "id": story_id(url, title),
                "title": title,
                "url": url,
                "canonical_url": canonical_url(url),
                "summary": entry["summary"][:SUMMARY_CHARS],
                "published": published.astimezone(timezone.utc).isoformat() if published else None,
                "source": feed["name"],
                "source_id": feed["id"],
                "tier": feed["tier"],
                "topics": feed.get("topics", []),
                "feed_stack": feed.get("stack", []),
            }
        )
    return result

# main

def select_feeds(catalog: list[dict], args) -> list[dict]:
    feeds = catalog
    if args.only:
        wanted = {f.strip() for f in args.only.split(",") if f.strip()}
        feeds = [f for f in feeds if f["id"] in wanted]
    if args.exclude:
        skipped = {f.strip() for f in args.exclude.split(",") if f.strip()}
        feeds = [f for f in feeds if f["id"] not in skipped]
    if args.topics:
        wanted = {t.strip().lower() for t in args.topics.split(",") if t.strip()}
        feeds = [f for f in feeds if wanted & {t.lower() for t in f.get("topics", [])}]
    if args.max_tier:
        feeds = [f for f in feeds if f["tier"] <= args.max_tier]
    return feeds


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect candidate tech stories from RSS/Atom feeds.")
    parser.add_argument("--feeds", type=Path, default=skill_root() / "references" / "feeds.json")
    parser.add_argument("--hours", type=int, default=24, help="how far back a story may have been published")
    parser.add_argument("--out", type=Path, help="write JSON here instead of stdout")
    parser.add_argument("--only", help="comma separated feed ids to include")
    parser.add_argument("--exclude", help="comma separated feed ids to skip")
    parser.add_argument("--topics", help="comma separated topics: ai, tech, devtools, cloud, security, startups, research")
    parser.add_argument("--max-tier", type=int, choices=[1, 2, 3], help="1 primary only, 2 adds newsrooms, 3 adds community")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    parser.add_argument("--undated", action="store_true", help="keep items whose feed omits a publication date")
    parser.add_argument("--check-feeds", action="store_true", help="report reachability per feed and exit")
    args = parser.parse_args()

    if not args.feeds.exists():
        print(f"feed catalog not found: {args.feeds}", file=sys.stderr)
        return 2

    feeds = select_feeds(load_catalog(args.feeds), args)
    if not feeds:
        print("no feeds selected", file=sys.stderr)
        return 2

    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(collect_feed, feed, args.timeout): feed for feed in feeds}
        for future in as_completed(futures):
            results.append(future.result())

    if args.check_feeds:
        ok = [r for r in results if not r["error"]]
        bad = [r for r in results if r["error"]]
        for r in sorted(ok, key=lambda r: r["feed"]):
            print(f"  ok    {r['feed']:<14} {len(r['items']):>3} items  {r['url']}")
        for r in sorted(bad, key=lambda r: r["feed"]):
            print(f"  FAIL  {r['feed']:<14} {r['error']}  {r['url']}")
        print(f"\n{len(ok)} reachable, {len(bad)} failing, {len(feeds)} configured")
        return 0 if ok else 1

    cutoff = datetime.now(timezone.utc) - timedelta(hours=args.hours)
    items: list[dict] = []
    for result in results:
        for item in result["items"]:
            if item["published"] is None:
                if args.undated:
                    items.append(item)
                continue
            if datetime.fromisoformat(item["published"]) >= cutoff:
                items.append(item)

    items.sort(key=lambda i: (i["published"] or "", i["tier"]), reverse=True)

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "window_hours": args.hours,
        "feeds_configured": len(feeds),
        "feeds_ok": sorted(r["feed"] for r in results if not r["error"]),
        "feeds_failed": {r["feed"]: r["error"] for r in results if r["error"]},
        "item_count": len(items),
        "items": items,
    }

    text = json.dumps(payload, indent=2, ensure_ascii=False)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
        print(
            f"collected {len(items)} items from {len(payload['feeds_ok'])}/{len(feeds)} feeds "
            f"(last {args.hours}h) -> {args.out}"
        )
        if payload["feeds_failed"]:
            print("unreachable: " + ", ".join(payload["feeds_failed"]))
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())