#!/usr/bin/env python3
"""Regression tests for the cron spec's dangerous parts.

The invariant with teeth: never read "I could not tell what is registered" as
"nothing is". Getting that wrong duplicates the job and the owner gets two
briefs a day. These tests pin it.

    python3 tests/test_schedule.py
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tb-schedule" / "scripts"))
sys.path.insert(0, str(ROOT / "tb-setup" / "scripts"))

import register_crons  # noqa: E402
import write_config  # noqa: E402

FAILURES: list[str] = []


def check(condition: bool, label: str) -> None:
    print(f"  {'PASS' if condition else 'FAIL'}  {label}")
    if not condition:
        FAILURES.append(label)


def test_schedule_expression() -> None:
    print("cron expression from config")
    check(register_crons.schedule_from({"hour": 8, "minute": 0}) == "0 8 * * *",
          "08:00 becomes '0 8 * * *'")
    check(register_crons.schedule_from({"hour": 17, "minute": 30}) == "30 17 * * *",
          "17:30 becomes '30 17 * * *'")
    check(register_crons.schedule_from({}) == "0 8 * * *", "defaults to 08:00")
    for bad in ({"hour": 24}, {"hour": -1}, {"hour": "8"}, {"hour": 8, "minute": 60}):
        try:
            register_crons.schedule_from(bad)
            check(False, f"rejects {bad}")
        except SystemExit:
            check(True, f"rejects {bad}")


def test_registered_jobs() -> None:
    print("\nreading hermes's persisted schedule")
    with tempfile.TemporaryDirectory() as tmp:
        missing = Path(tmp) / "absent.json"
        check(register_crons.registered_jobs(str(missing)) == {},
              "a missing jobs.json is the one absence meaning 'nothing scheduled'")

        active = Path(tmp) / "active.json"
        active.write_text(json.dumps({"jobs": [
            {"name": "tb-daily-brief", "enabled": True, "paused_at": None},
            {"name": "other", "enabled": True, "paused_at": None},
        ]}), encoding="utf-8")
        jobs = register_crons.registered_jobs(str(active))
        check(jobs.get("tb-daily-brief") is True, "an enabled job reads as runnable")

        paused = Path(tmp) / "paused.json"
        paused.write_text(json.dumps({"jobs": [
            {"name": "tb-daily-brief", "enabled": True, "paused_at": "2026-09-09T00:00:00Z"},
        ]}), encoding="utf-8")
        check(register_crons.registered_jobs(str(paused))["tb-daily-brief"] is False,
              "a paused job is registered but not runnable")

        disabled = Path(tmp) / "disabled.json"
        disabled.write_text(json.dumps({"jobs": [
            {"name": "tb-daily-brief", "enabled": False, "paused_at": None},
        ]}), encoding="utf-8")
        check(register_crons.registered_jobs(str(disabled))["tb-daily-brief"] is False,
              "a disabled job is registered but not runnable")

        broken = Path(tmp) / "broken.json"
        broken.write_text("{not json", encoding="utf-8")
        try:
            register_crons.registered_jobs(str(broken))
            check(False, "an unreadable jobs.json must raise, never read as empty")
        except json.JSONDecodeError:
            check(True, "an unreadable jobs.json raises rather than reading as empty")

        unexpected = Path(tmp) / "unexpected.json"
        unexpected.write_text(json.dumps({"schedules": []}), encoding="utf-8")
        try:
            register_crons.registered_jobs(str(unexpected))
            check(False, "an unexpected shape must raise")
        except KeyError:
            check(True, "an unexpected shape raises rather than reading as empty")


def test_deliver_target() -> None:
    print("\ndelivery target")
    check(register_crons.deliver_target({"PLOW_HOME_CHANNEL": "cht_abc"}) == "cht_abc",
          "the home channel is used verbatim")
    for env in ({}, {"PLOW_HOME_CHANNEL": ""}, {"PLOW_HOME_CHANNEL": "   "}):
        try:
            register_crons.deliver_target(env)
            check(False, f"refuses {env!r}")
        except SystemExit:
            check(True, f"refuses a blank channel rather than delivering nowhere ({env!r})")


def test_config_validation() -> None:
    print("\nconfig validation")
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "config.json"
        argv_ok = ["--owner", "Caio", "--language", "pt-BR", "--stack", "python, React ,AWS",
                   "--hour", "7", "--out", str(out)]
        sys.argv = ["write_config.py", *argv_ok]
        check(write_config.main() == 0, "a valid config is accepted")
        written = json.loads(out.read_text(encoding="utf-8"))
        check(written["stack"] == ["python", "react", "aws"],
              "stack tags are trimmed and lowercased")
        check(written["hour"] == 7 and written["minute"] == 0, "hour and minute are stored")

        for bad, label in [
            (["--hour", "25"], "hour above 23"),
            (["--minute", "60"], "minute above 59"),
            (["--max-stories", "0"], "max-stories below 1"),
            (["--window-hours", "0"], "window below 1"),
            (["--topics", "ai,bogus"], "an unknown topic"),
        ]:
            sys.argv = ["write_config.py", *bad, "--out", str(Path(tmp) / "rejected.json")]
            check(write_config.main() == 2, f"rejects {label}")


def test_bare_path_invocations_are_executable() -> None:
    """A skill sheet that names a script without an interpreter needs that file
    to carry its own executable bit.

    The Dockerfile PRESERVES modes rather than granting them -- it normalises
    0644 and 0755 and adds neither -- so a script committed 0644 lands 0644 in
    the image and every bare-path invocation fails with Permission denied. The
    failure surfaces as a brief that never arrives, which reads like a quiet
    news day, so it is worth catching in the checkout.
    """
    print("\nevery bare-path invocation in a skill sheet is executable")
    invocation = re.compile(r"^\s*/var/lib/hermes/skills/(\S+\.py)", re.M)
    named: set[str] = set()
    for sheet in sorted(ROOT.glob("tb-*/SKILL.md")):
        named.update(invocation.findall(sheet.read_text(encoding="utf-8")))
    check(bool(named), "the sweep found invocations to check")
    for relative in sorted(named):
        source = ROOT / relative
        check(source.exists(), f"the sheet names a script that exists: {relative}")
        if source.exists():
            check(os.access(source, os.X_OK),
                  f"{relative} is executable, as its sheet invokes it")


def main() -> int:
    test_schedule_expression()
    test_registered_jobs()
    test_deliver_target()
    test_config_validation()
    test_bare_path_invocations_are_executable()
    print()
    if FAILURES:
        print(f"{len(FAILURES)} failing check(s)")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())