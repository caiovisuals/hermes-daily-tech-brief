#!/usr/bin/env python3
"""Write this owner's brief configuration, validated, atomically.

The agent gathers the answers in conversation and calls this. Validation lives
here rather than in the sheet because a prompt cannot enforce a range: an hour
of 25 or a window of -3 would be written happily and then fail at 08:00 in a
cron run nobody is watching.

Usage:
    write_config.py --owner "Caio" --language pt-BR \
        --stack "python,react,aws" --hour 8
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

VALID_TOPICS = {"ai", "tech", "devtools", "cloud", "security", "startups", "research"}


def config_path() -> Path:
    home = os.environ.get("HERMES_HOME", "/var/lib/hermes")
    return Path(home) / "tb" / "config.json"


def split_list(raw: str) -> list[str]:
    return [item.strip().lower() for item in (raw or "").split(",") if item.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description="Write the tech brief configuration.")
    parser.add_argument("--owner", default="", help="name the brief is addressed to")
    parser.add_argument("--language", default="en-US", help="BCP 47 tag, e.g. pt-BR")
    parser.add_argument("--stack", default="", help="comma separated technologies the owner runs")
    parser.add_argument("--topics", default="", help=f"optional filter, any of: {', '.join(sorted(VALID_TOPICS))}")
    parser.add_argument("--hour", type=int, default=8, help="local hour the brief is sent, 0-23")
    parser.add_argument("--minute", type=int, default=0, help="minute past the hour, 0-59")
    parser.add_argument("--max-stories", type=int, default=8)
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    problems = []
    if not 0 <= args.hour <= 23:
        problems.append(f"--hour must be 0-23, got {args.hour}")
    if not 0 <= args.minute <= 59:
        problems.append(f"--minute must be 0-59, got {args.minute}")
    if not 1 <= args.max_stories <= 20:
        problems.append(f"--max-stories must be 1-20, got {args.max_stories}")
    if not 1 <= args.window_hours <= 168:
        problems.append(f"--window-hours must be 1-168, got {args.window_hours}")

    topics = split_list(args.topics)
    unknown = [t for t in topics if t not in VALID_TOPICS]
    if unknown:
        problems.append(
            f"unknown topic(s): {', '.join(unknown)}. Valid: {', '.join(sorted(VALID_TOPICS))}"
        )

    if problems:
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 2

    stack = split_list(args.stack)
    config = {
        "version": 1,
        "owner": args.owner.strip(),
        "language": args.language.strip() or "en-US",
        "stack": stack,
        "topics": topics,
        "max_stories": args.max_stories,
        "window_hours": args.window_hours,
        "hour": args.hour,
        "minute": args.minute,
    }

    target = args.out or config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    # Atomic: a cron run reading a half-written config at 08:00 is a failure
    # nobody sees until the brief does not arrive.
    handle, tmp = tempfile.mkstemp(dir=str(target.parent), prefix=".config-", suffix=".json")
    with os.fdopen(handle, "w", encoding="utf-8") as stream:
        json.dump(config, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
    os.replace(tmp, target)

    print(f"wrote {target}")
    print(json.dumps(config, indent=2, ensure_ascii=False))
    if not stack:
        print(
            "\nNo stack declared. The brief will still run, but it will be a generic "
            "feed rather than one ranked for this owner.",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())