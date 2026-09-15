#!/usr/bin/env python3
"""Deduplicate, score and rank the candidates produced by collect_news.py.

Three jobs, all deterministic so the agent never has to guess:

  1. Collapse the same story reported by several feeds into one cluster.
  2. Drop anything already delivered on a previous day, and flag stories that
     are a genuine follow-up to one the reader already saw.
  3. Rank what survives against the reader's declared stack, so a release note
     for something they actually run outranks generic industry noise.

Standard library only.

Usage:
    filter_news.py --in candidates.json --stack "python,react,aws" \
        --history ~/.hermes/tech-brief/history.json --top 20 --out ranked.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from pathlib import Path

TIER_WEIGHT = {1: 3.0, 2: 2.0, 3: 1.5}
STACK_HIT_POINTS = 4.0
STACK_HIT_CAP = 12.0
FEED_STACK_POINTS = 2.5
CLUSTER_POINTS = 1.5
CLUSTER_CAP = 4.5
SECURITY_STACK_BONUS = 5.0
TITLE_SIMILARITY = 0.72
CONTINUITY_SIMILARITY = 0.50
DEFAULT_HISTORY_DAYS = 14

SECURITY_MARKERS = re.compile(
    r"\b(cve-\d{4}-\d+|zero[- ]day|actively exploited|critical vulnerability|"
    r"remote code execution|rce|supply chain attack|data breach|ransomware)\b",
    re.IGNORECASE,
)
VERSION_RE = re.compile(r"\b\d+(?:\.\d+)+\b")
CVE_RE = re.compile(r"\bcve-\d{4}-\d{4,}\b", re.IGNORECASE)
SLUG_NOISE = {"blog", "news", "posts", "post", "article", "index", "html", "amp",
              "release", "releases", "story", "www", "com", "org", "feed"}
STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "for", "in", "on", "with", "is",
    "are", "as", "at", "by", "from", "its", "it", "new", "now", "this", "that",
    "how", "why", "what", "you", "your", "we", "our", "be", "has", "have",
}

# text helpers

def normalize_title(title: str) -> str:
    text = re.sub(r"[^\w\s]", " ", title.lower())
    return re.sub(r"\s+", " ", text).strip()


def title_tokens(title: str) -> set[str]:
    return {
        t
        for t in normalize_title(title).split()
        if t not in STOPWORDS and (len(t) > 2 or t.isdigit())
    }


def _version_tuples(text: str) -> set[tuple[int, ...]]:
    out = set()
    for raw in VERSION_RE.findall(text):
        try:
            out.add(tuple(int(p) for p in raw.split(".")))
        except ValueError:
            continue
    return out


def _versions_conflict(a: str, b: str) -> bool:
    """True when both titles name a version and no pair of them can be the same release.

    Agreement is prefix-based and never normalises trailing zeros: "Rust 1.95"
    and "Rust 1.95.0" are the same release because one simply omits the patch
    number, while "Node.js 26.5.0" and "Node.js 26.5.1" are two different patch
    releases and must stay apart.
    """
    va, vb = _version_tuples(a), _version_tuples(b)
    if not va or not vb:
        return False
    for x in va:
        for y in vb:
            if x[: len(y)] == y or y[: len(x)] == x:
                return False
    return True


def slug_tokens(url: str) -> set[str]:
    """Article slugs survive rewording across outlets, so they are a strong duplicate signal."""
    if not url:
        return set()
    try:
        path = urllib.parse.urlsplit(url).path.lower()
    except ValueError:
        return set()
    parts = re.split(r"[^a-z0-9]+", path)
    return {
        p for p in parts
        if p and p not in STOPWORDS and p not in SLUG_NOISE and len(p) > 2 and not p.isdigit()
    }


def similar(a: str, b: str, url_a: str = "", url_b: str = "") -> float:
    """Blend token overlap, sequence ratio and URL slug overlap.

    Any one of them alone misfires: headlines get reworded per outlet, slugs
    are missing on some feeds, and sequence ratio rewards shared boilerplate.
    """
    # A shared CVE identifier means the same vulnerability, whatever the wording.
    cve_a, cve_b = set(m.lower() for m in CVE_RE.findall(a)), set(m.lower() for m in CVE_RE.findall(b))
    if cve_a and cve_b:
        return 1.0 if cve_a & cve_b else 0.0

    # Release announcements differ only by version number, and after stopword
    # removal almost nothing else is left. Treat a version conflict as decisive
    # so "Node.js 22.20.0" never absorbs "Node.js 24.21.0".
    if _versions_conflict(a, b):
        return 0.0
    versions_agree = bool(_version_tuples(a)) and bool(_version_tuples(b))

    ta, tb = title_tokens(a), title_tokens(b)
    if not ta or not tb:
        return 0.0
    jaccard = len(ta & tb) / len(ta | tb)
    ratio = SequenceMatcher(None, normalize_title(a), normalize_title(b)).ratio()
    score = max(jaccard, (jaccard + ratio) / 2)

    sa, sb = slug_tokens(url_a), slug_tokens(url_b)
    if len(sa) >= 3 and len(sb) >= 3:
        score = max(score, len(sa & sb) / len(sa | sb))

    # Both headlines name the same release. That agreement survived the
    # conflict check above, so it is real evidence, not shared boilerplate.
    if versions_agree:
        score += 0.25
    return min(score, 1.0)


def build_term_index(stack_map: dict, tags: list[str]) -> dict[str, list[str]]:
    """Resolve each declared stack tag to the terms that signal it."""
    index: dict[str, list[str]] = {}
    for tag in tags:
        key = tag.strip().lower()
        if not key:
            continue
        index[key] = stack_map.get(key) or [key]
    return index


def term_pattern(term: str) -> str:
    """A term, anchored so it does not fire inside a longer word.

    The guard belongs on the alphanumeric ENDS of the term only. Half the
    catalog is deliberately open-ended -- `go 1.`, `git 2.`, `gpt-`, `cve-`
    are written to be followed by a version or an identifier -- and a blanket
    trailing `(?![a-z0-9])` made every one of them unmatchable: the character
    that has to follow them is exactly the one it forbids. "Go 1.25 is
    released" matched nothing for a reader who declared `go`, and
    "CVE-2026-1234 exploited in the wild" matched nothing for `security`.

    The same applies at the front: `.net` never matched "ASP.NET", because the
    character before the dot is a letter.
    """
    term = term.lower().strip()
    pattern = re.escape(term)
    if term[:1].isalnum():
        pattern = r"(?<![a-z0-9])" + pattern
    if term[-1:].isalnum():
        pattern = pattern + r"(?![a-z0-9])"
    return pattern


def match_stack(text: str, term_index: dict[str, list[str]]) -> list[str]:
    lowered = text.lower()
    hits = []
    for tag, terms in term_index.items():
        for term in terms:
            if term.strip() and re.search(term_pattern(term), lowered):
                hits.append(tag)
                break
    return hits

# history

def load_history(path: Path | None) -> dict:
    if not path or not path.exists():
        return {"version": 1, "stories": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"version": 1, "stories": {}}
    data.setdefault("stories", {})
    return data


def recent_history(history: dict, days: int) -> list[dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    out = []
    for story_id, record in history.get("stories", {}).items():
        seen = record.get("last_seen") or record.get("first_seen")
        try:
            if seen and datetime.fromisoformat(seen) < cutoff:
                continue
        except ValueError:
            pass
        out.append({"id": story_id, **record})
    return out

# clustering

def cluster_items(items: list[dict]) -> list[dict]:
    """Group duplicate coverage. The most authoritative source becomes primary."""
    clusters: list[dict] = []
    for item in items:
        placed = False
        for cluster in clusters:
            head = cluster["primary"]
            if item["canonical_url"] and item["canonical_url"] == head["canonical_url"]:
                placed = True
            elif similar(item["title"], head["title"],
                         item["canonical_url"], head["canonical_url"]) >= TITLE_SIMILARITY:
                placed = True
            if placed:
                cluster["members"].append(item)
                if (item["tier"], item.get("published") or "") < (head["tier"], head.get("published") or ""):
                    cluster["primary"] = item
                break
        if not placed:
            clusters.append({"primary": item, "members": [item]})
    return clusters


def find_continuity(title: str, url: str, prior: list[dict]) -> dict | None:
    best, best_score = None, 0.0
    for record in prior:
        score = similar(title, record.get("title", ""), url, record.get("url", ""))
        if score > best_score:
            best, best_score = record, score
    if best and CONTINUITY_SIMILARITY <= best_score < TITLE_SIMILARITY:
        return {"previous_title": best.get("title"), "previous_url": best.get("url"),
                "previous_day": best.get("day"), "similarity": round(best_score, 3)}
    return None

# scoring

def score_cluster(cluster: dict, term_index: dict[str, list[str]], now: datetime) -> dict:
    primary = cluster["primary"]
    sources = {m["source"] for m in cluster["members"]}
    haystack = f"{primary['title']} {primary.get('summary', '')}"

    stack_hits = match_stack(haystack, term_index)
    feed_hits = sorted(set(primary.get("feed_stack", [])) & set(term_index))

    score = TIER_WEIGHT.get(primary["tier"], 1.0)
    score += min(len(stack_hits) * STACK_HIT_POINTS, STACK_HIT_CAP)
    if feed_hits:
        score += FEED_STACK_POINTS
    score += min((len(sources) - 1) * CLUSTER_POINTS, CLUSTER_CAP)

    is_security = bool(SECURITY_MARKERS.search(haystack))
    if is_security and (stack_hits or feed_hits):
        score += SECURITY_STACK_BONUS

    if primary.get("published"):
        try:
            age_hours = (now - datetime.fromisoformat(primary["published"])).total_seconds() / 3600
            score += max(0.0, 3.0 - (age_hours / 12))
        except ValueError:
            pass

    return {
        "id": primary["id"],
        "title": primary["title"],
        "url": primary["url"],
        "canonical_url": primary["canonical_url"],
        "summary": primary.get("summary", ""),
        "published": primary.get("published"),
        "source": primary["source"],
        "tier": primary["tier"],
        "topics": primary.get("topics", []),
        "score": round(score, 2),
        "stack_matches": sorted(set(stack_hits) | set(feed_hits)),
        "security_flag": is_security,
        "corroboration": sorted(sources),
        "also_covered_by": [
            {"source": m["source"], "url": m["url"]}
            for m in cluster["members"]
            if m["id"] != primary["id"]
        ][:5],
    }

# main

def main() -> int:
    parser = argparse.ArgumentParser(description="Deduplicate and rank collected stories.")
    parser.add_argument("--in", dest="infile", type=Path, required=True)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--stack", default="", help="comma separated stack tags the reader cares about")
    parser.add_argument("--stack-map", type=Path,
                        default=Path(__file__).resolve().parent.parent / "references" / "stack-keywords.json")
    parser.add_argument("--history", type=Path, help="history.json written by format_brief.py")
    parser.add_argument("--history-days", type=int, default=DEFAULT_HISTORY_DAYS)
    parser.add_argument("--top", type=int, default=20, help="how many ranked clusters to hand the agent")
    parser.add_argument("--min-score", type=float, default=0.0)
    parser.add_argument("--keep-seen", action="store_true", help="do not drop stories already delivered")
    args = parser.parse_args()

    if not args.infile.exists():
        print(f"input not found: {args.infile}", file=sys.stderr)
        return 2

    payload = json.loads(args.infile.read_text(encoding="utf-8"))
    items = payload.get("items", [])

    stack_map = {}
    if args.stack_map.exists():
        stack_map = json.loads(args.stack_map.read_text(encoding="utf-8")).get("stack", {})
    tags = [t for t in (args.stack or "").split(",") if t.strip()]
    term_index = build_term_index(stack_map, tags)

    history = load_history(args.history)
    prior = recent_history(history, args.history_days)
    seen_ids = {r["id"] for r in prior}
    seen_urls = {r.get("url") for r in prior if r.get("url")}

    fresh, dropped = [], 0
    for item in items:
        if not args.keep_seen and (item["id"] in seen_ids or item["canonical_url"] in seen_urls):
            dropped += 1
            continue
        fresh.append(item)

    now = datetime.now(timezone.utc)
    scored = [score_cluster(c, term_index, now) for c in cluster_items(fresh)]

    for entry in scored:
        continuity = find_continuity(entry["title"], entry["canonical_url"], prior)
        if continuity:
            entry["continuity"] = continuity
            entry["score"] = round(entry["score"] + 2.0, 2)

    scored = [s for s in scored if s["score"] >= args.min_score]
    scored.sort(key=lambda s: (s["score"], s.get("published") or ""), reverse=True)
    selected = scored[: args.top]

    result = {
        "generated_at": now.isoformat(),
        "window_hours": payload.get("window_hours"),
        "stack": tags,
        "unknown_stack_tags": [t.strip().lower() for t in tags if t.strip().lower() not in stack_map],
        "input_items": len(items),
        "already_delivered": dropped,
        "clusters_found": len(scored),
        "returned": len(selected),
        "feeds_failed": payload.get("feeds_failed", {}),
        "stories": selected,
    }

    text = json.dumps(result, indent=2, ensure_ascii=False)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
        print(
            f"ranked {len(selected)} stories from {len(items)} items "
            f"({dropped} already delivered, {len(scored)} unique) -> {args.out}"
        )
        if result["unknown_stack_tags"]:
            print("stack tags with no keyword mapping (matched literally): "
                  + ", ".join(result["unknown_stack_tags"]))
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())