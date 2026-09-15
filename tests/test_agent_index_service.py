#!/usr/bin/env python3
"""Regression tests for the Agent Index usage reporter, as the image ships it.

There is no switch: the service is in the image or it is not, and that IS the
decision -- an owner who does not want their usage on the index builds without
it. So what is worth pinning is not whether it can be turned off, but what it
does on each of the three answers the client gives about this install.

These RUN the service script in a sandbox rather than grepping it. A test that
matches a string passes on a script that would not start, which is the one
thing worth knowing about a boot service.

No test framework required, so it runs anywhere the skill runs:

    python3 tests/test_agent_index_service.py
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SERVICE = ROOT / "image" / "s6-overlay" / "s6-rc.d" / "agent-index"

FAILURES: list[str] = []


def check(condition: bool, label: str) -> None:
    print(f"  {'PASS' if condition else 'FAIL'}  {label}")
    if not condition:
        FAILURES.append(label)


# A stand-in for the pinned client, answering the two things the run script asks
# of it: `status`, whose EXIT CODE is the whole answer, and everything else,
# which it records the argv of. What the script did is then a file, not a guess
# from the output of a program that is not there.
STUB_CLIENT = """
import sys

if sys.argv[1:2] == ["status"]:
    sys.exit({status})

with open({record!r}, "a") as record:
    record.write(" ".join(sys.argv[1:]) + "\\n")
"""


def run_service(tmp: Path, environment: dict[str, str], seconds: float = 2.0,
                status: int | None = None) -> str:
    """Start the real run script against a fake container environment.

    It is a supervised loop, so it never exits on its own: it is killed after a
    moment and judged on what it did. /command and /opt are not there, so the
    client invocation fails -- which is the point, it proves the script reached
    the invocation with the values it was given.

    Given `status` -- what the stub client's `status` command exits with -- the
    three absolute paths this image guarantees are pointed at the sandbox
    instead, so the script's OWN branching runs against a client that answers.
    That is the only way to see what it does on the second hour, which is where
    the registration gate is either right or minting a key an hour forever.
    """
    env_dir = tmp / "run" / "s6" / "container_environment"
    env_dir.mkdir(parents=True)
    for name, value in environment.items():
        (env_dir / name).write_text(value, encoding="utf-8")

    script = (SERVICE / "run").read_text(encoding="utf-8").replace(
        "/run/s6/container_environment", str(env_dir))
    if status is not None:
        home = tmp / "hermes"
        home.mkdir()
        client = tmp / "client.py"
        client.write_text(
            STUB_CLIENT.format(status=status, record=str(tmp / "invoked")),
            encoding="utf-8",
        )
        script = (script
                  .replace("/var/lib/hermes", str(home))
                  .replace("/command/s6-setuidgid hermes", "")
                  .replace("/opt/hermes/.venv/bin/python3", sys.executable)
                  .replace("/opt/plow/agent-index-client.py", str(client)))
    sandbox = tmp / "run.sh"
    sandbox.write_text(script, encoding="utf-8")
    sandbox.chmod(0o755)

    try:
        done = subprocess.run(["sh", str(sandbox)], capture_output=True, text=True,
                              timeout=seconds, env={"PATH": os.environ["PATH"]})
        return done.stdout + done.stderr
    except subprocess.TimeoutExpired as expired:
        out = (expired.stdout or b"") + (expired.stderr or b"")
        return out.decode() if isinstance(out, bytes) else str(out)


def invocations(tmp: Path) -> list[str]:
    """Every way the client was invoked in that run, in order."""
    record = tmp / "invoked"
    return record.read_text(encoding="utf-8").splitlines() if record.exists() else []


def test_no_agent_id_stands_down() -> None:
    print("\nwithout an AGENT_ID there is nothing to report for")
    with tempfile.TemporaryDirectory() as raw:
        said = run_service(Path(raw), {"PLOW_AGENT_TOKEN": "plow_atokenshapedthing"})
    check("standing down" in said, "it stands down rather than guessing a name")
    check("AGENT_ID" in said, "and it says which value is missing")


def test_an_id_and_a_credential_are_enough() -> None:
    """One run, two things worth knowing about it.

    It reaches the work -- as the agent, with the home this image uses -- and it
    does NOT stand down, which is the no-switch rule stated as behaviour: with a
    credential and an id and nothing else set, a switch would have stopped it
    here for want of a flag.
    """
    print("\ngiven an id and a credential it proceeds")
    with tempfile.TemporaryDirectory() as raw:
        said = run_service(Path(raw), {"PLOW_AGENT_TOKEN": "plow_atokenshapedthing",
                                       "AGENT_ID": "hermes-daily-tech-brief"})
    check("standing down" not in said, "it had everything it needed")
    # /command/s6-setuidgid does not exist out here, and that failure is the
    # evidence: it got as far as dropping privilege to do the work.
    check("s6-setuidgid" in said or "not found" in said,
          "it got as far as dropping privilege to do the work")


def test_registers_exactly_when_the_client_says_it_is_not_registered() -> None:
    """What the script DID with the client, read off the argv the stub recorded."""
    print("\nthe registration gate asks the client and believes the answer")
    cases = [
        # 0 -- registered, so the hour is a report and nothing else. This is the
        # row a path test gets wrong: the client only ever DELETES the path a
        # naive gate would check, so the gate reads true on every pass and every
        # tenant mints a fresh key on the hour.
        (0, [""], "already registered: it reports and does not re-register"),
        # 3 -- not registered, and a gate that never registers is a tenant with
        # no page: register once, then report with what that stored.
        (3, ["--register --agent hermes-daily-tech-brief", ""],
         "not registered: it registers once, then reports"),
    ]
    for status, expected, label in cases:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            run_service(tmp, {"PLOW_AGENT_TOKEN": "plow_atokenshapedthing",
                              "AGENT_ID": "hermes-daily-tech-brief"}, status=status)
            check(invocations(tmp) == expected, label)


def test_unreadable_state_touches_the_index_not_at_all() -> None:
    """2 is not 3. State the client could not READ is not state to register
    over: minting against a new install id strands every row the old one
    published. So the hour is skipped entirely -- no registration, no report.
    """
    print("\nstate the client cannot read is skipped, not registered over")
    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)
        said = run_service(tmp, {"PLOW_AGENT_TOKEN": "plow_atokenshapedthing",
                                 "AGENT_ID": "hermes-daily-tech-brief"}, status=2)
        check(invocations(tmp) == [], "it did not touch the Index on a state it cannot read")
    check("could not read this install's state" in said,
          "and it says so rather than failing quietly")


def test_the_service_is_wired_the_way_s6_starts_one() -> None:
    """A service s6 does not know about is a file nobody runs -- and this one
    cannot start before the boot that exports its credential.
    """
    print("\nthe service is wired the way s6 starts one")
    check((SERVICE / "type").read_text(encoding="utf-8").strip() == "longrun",
          "type is longrun")
    check((SERVICE / "dependencies.d" / "plow-init").exists(),
          "it depends on plow-init, which exports the credential it reads")
    check((ROOT / "image/s6-overlay/s6-rc.d/user/contents.d/agent-index").exists(),
          "it is listed in the user bundle, so s6 actually starts it")
    check(os.access(SERVICE / "run", os.X_OK), "the run script is executable")


def test_the_client_is_pinned_and_the_build_verifies_it() -> None:
    """A moving reference would substitute unreviewed code inside an agent that
    holds a live credential; a sha alone trusts whoever serves it. The build
    does the checking -- this asserts the build was told to.
    """
    print("\nthe client is pinned and the build checks what it fetched")
    pin = (ROOT / "vendor" / "client.pin").read_text(encoding="utf-8")
    check(bool(re.search(r"^sha=[0-9a-f]{40}$", pin, re.M)),
          "a full commit sha, never a branch")
    check(bool(re.search(r"^sha256=[0-9a-f]{64}$", pin, re.M)),
          "and the hash of the file that sha serves")
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    check("vendor/client.pin" in dockerfile and "sha256sum" in dockerfile,
          "the build reads the pin and verifies the download against it")
    check("COPY image/s6-overlay/" in dockerfile,
          "and the service tree is copied into the image")


def test_the_agent_id_reaches_the_container() -> None:
    """The reporter reads AGENT_ID out of the container environment, and nothing
    puts it there but the compose file. A registered id that is not set here is
    an agent that stands down every hour and never appears on the leaderboard.

    And the id shipped has to be the id claimed. Registering one and running
    another is silent: the service reports happily, into a page nobody owns.
    """
    print("\ncompose ships the id the README claims")
    compose = (ROOT / "compose.yml").read_text(encoding="utf-8")
    shipped = re.search(r"^\s*AGENT_ID:\s*(\S+)", compose, re.M)
    check(shipped is not None, "AGENT_ID is set, not left commented out")
    if shipped is None:
        return
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    claimed = re.search(r"--agent\s+(\S+)", readme)
    check(claimed is not None, "the README says which id to register")
    if claimed is not None:
        check(claimed.group(1) == shipped.group(1),
              f"the id registered ({claimed.group(1)}) is the id shipped "
              f"({shipped.group(1)})")


def main() -> int:
    test_no_agent_id_stands_down()
    test_an_id_and_a_credential_are_enough()
    test_registers_exactly_when_the_client_says_it_is_not_registered()
    test_unreadable_state_touches_the_index_not_at_all()
    test_the_service_is_wired_the_way_s6_starts_one()
    test_the_client_is_pinned_and_the_build_verifies_it()
    test_the_agent_id_reaches_the_container()
    print()
    if FAILURES:
        print(f"{len(FAILURES)} failing check(s)")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())