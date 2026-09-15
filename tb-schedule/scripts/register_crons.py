#!/usr/bin/env python3
"""Register the daily brief cron, idempotently, from this owner's config.

Why this exists. 
`hermes cron` persists jobs to /var/lib/hermes/cron/jobs.json, and nothing replays that file on a rebuild.
A rebuilt agent therefore comes up with no schedule and no signal:
the brief simply stops arriving, which looks exactly like a quiet news day.
Keeping the row here means "set up my brief" replays a reviewed spec rather than improvising a schedule from a sentence.

The invariant with teeth, carried from the reference agent: never read "I could
not tell what is registered" as "nothing is". That re-registers the job and
duplicates it, and the owner gets two briefs a day with no way to tell which is which.
Only a missing jobs.json means nothing is scheduled; every other failure stops the run.

Runs INSIDE the container, where the hermes binary and that file live.

Usage:
    register_crons.py            # register or report
    register_crons.py --replace  # delete the existing row first, for a time change
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import subprocess
import sys

HERMES = "/opt/hermes/bin/hermes"
JOBS_FILE = "/var/lib/hermes/cron/jobs.json"
JOB_NAME = "tb-daily-brief"

PROMPT = (
    "Produce today's tech brief. Follow the tb-brief skill sheet exactly: collect, "
    "rank, read the sources, write brief.json, render it with format_brief.py, and "
    "make your final response the rendered brief itself so it reaches the owner."
)


def config_path() -> pathlib.Path:
    home = os.environ.get("HERMES_HOME", "/var/lib/hermes")
    return pathlib.Path(home) / "tb" / "config.json"


def load_config(path: pathlib.Path) -> dict:
    if not path.exists():
        raise SystemExit(
            f"{path} does not exist, so there is no schedule to register. "
            "Run tb-setup first."
        )
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{path} is not valid JSON: {exc}") from exc


def schedule_from(config: dict) -> str:
    """A bare cron expression. `hermes cron create` takes no per-job timezone:
    jobs fire in the container's zone, so the hour written here is that zone's."""
    hour = config.get("hour", 8)
    minute = config.get("minute", 0)
    if not (isinstance(hour, int) and 0 <= hour <= 23):
        raise SystemExit(f"config hour must be an integer 0-23, got {hour!r}")
    if not (isinstance(minute, int) and 0 <= minute <= 59):
        raise SystemExit(f"config minute must be an integer 0-59, got {minute!r}")
    return f"{minute} {hour} * * *"


def registered_jobs(jobs_path: str = JOBS_FILE) -> dict[str, bool]:
    """What is already scheduled, read from hermes's own persisted state.

    Reads the file `hermes cron` writes rather than parsing `hermes cron list`:
    that listing is a human rendering nothing pins, and matching on its text
    needs a new guard every time it is wrong. Here a name is a field.

    Returns {name: is_runnable}. A paused job is registered but will never fire,
    and the caller has to tell those apart: re-registering it duplicates it,
    skipping it silently leaves a brief that never arrives.

    Catches only FileNotFoundError. Every other failure raises, which is the
    invariant above.
    """
    try:
        jobs = json.loads(pathlib.Path(jobs_path).read_text(encoding="utf-8"))["jobs"]
    except FileNotFoundError:
        return {}
    return {job["name"]: bool(job["enabled"]) and not job.get("paused_at") for job in jobs}


def deliver_target(env: dict) -> str:
    """The owner's home chat, published into the container environment by first
    boot. Refused when blank: a --deliver with an empty target silently sends
    the brief nowhere, and the cron still reports success."""
    channel = (env.get("PLOW_HOME_CHANNEL") or "").strip()
    if not channel:
        raise SystemExit(
            "PLOW_HOME_CHANNEL is empty in this environment, so the brief would be "
            "delivered nowhere. Run this from a turn, which inherits the gateway's "
            "environment; a bare `docker exec` carries none of those values."
        )
    return channel


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--replace", action="store_true",
                        help="delete the existing row first, for a schedule change")
    parser.add_argument("--jobs-file", default=JOBS_FILE)
    args = parser.parse_args(argv)

    if not os.path.exists(HERMES):
        raise SystemExit(f"{HERMES} not found -- run this inside the agent container")

    env = os.environ
    config = load_config(config_path())
    schedule = schedule_from(config)
    target = deliver_target(env)

    registered = registered_jobs(args.jobs_file)

    if JOB_NAME in registered and not args.replace:
        if registered[JOB_NAME]:
            print(f"{JOB_NAME} is already registered and active ({schedule}).")
            print("Nothing to do. Use --replace to change the time.")
            return 0
        print(
            f"{JOB_NAME} is registered but PAUSED, so the brief will never fire.\n"
            "Resume it with `hermes cron resume tb-daily-brief`, or re-create it "
            "with --replace. Not registering a second copy.",
            file=sys.stderr,
        )
        return 1

    if JOB_NAME in registered and args.replace:
        removed = subprocess.run(
            [HERMES, "cron", "delete", JOB_NAME], capture_output=True, text=True
        )
        if removed.returncode != 0:
            print(removed.stdout + removed.stderr, file=sys.stderr)
            print(f"could not delete the existing {JOB_NAME}; not creating a second copy.",
                  file=sys.stderr)
            return 1
        print(f"removed the previous {JOB_NAME}")

    created = subprocess.run(
        [HERMES, "cron", "create", schedule, PROMPT,
         "--name", JOB_NAME, "--skill", "tb-brief", "--deliver", target],
        capture_output=True, text=True,
    )
    print((created.stdout + created.stderr).strip())
    if created.returncode != 0:
        print(f"cron create failed for {JOB_NAME}", file=sys.stderr)
        return 1

    # Confirm against hermes's own state rather than trusting the exit code.
    after = registered_jobs(args.jobs_file)
    if not after.get(JOB_NAME):
        print(
            f"{JOB_NAME} is not active in {args.jobs_file} after create. "
            "The brief will not fire; do not report this as set up.",
            file=sys.stderr,
        )
        return 1

    print(f"{JOB_NAME} registered and active: {schedule} (container timezone), "
          f"delivering to {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())