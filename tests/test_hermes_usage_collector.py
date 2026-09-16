#!/usr/bin/env python3
"""Regression tests for the Hermes usage collector in agent_index_client.py.

The number this collector produces is published on a public leaderboard, and
the two ways it can be wrong are not symmetrical. Reporting too little makes a
busy agent look idle -- the failure this suite exists for, because it is silent:
a store nobody found and a store with nothing in it both totalled zero and said
nothing about which had happened. Reporting too much republishes history that
was already correct.

So what is pinned here is the accounting, not the plumbing: what a first run
does, what the second run does with it, and every way a store can be absent,
empty, unreadable or somewhere other than the one path the collector used to
look at.

Every store is a fixture built in a temp directory. Nothing reads a real Hermes
install, nothing goes to the network, and nothing here needs a credential.

No test framework required, so it runs anywhere the skill runs:

    python3 tests/test_hermes_usage_collector.py
"""

from __future__ import annotations

import contextlib
import datetime
import io
import json
import os
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import agent_index_client as client  # noqa: E402

FAILURES: list[str] = []

TODAY = datetime.date.today().isoformat()
ZERO = {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0}


def check(condition: bool, label: str) -> None:
    print(f"  {'PASS' if condition else 'FAIL'}  {label}")
    if not condition:
        FAILURES.append(label)


def restore(saved: dict) -> None:
    """Put environment variables back, where absent means absent."""
    for name, value in saved.items():
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value


@contextlib.contextmanager
def env(**overrides):
    """Environment variables set for the body and restored afterwards; a value
    of None removes the variable for the duration."""
    saved = {k: os.environ.get(k) for k in overrides}
    for name, value in overrides.items():
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value
    try:
        yield
    finally:
        restore(saved)


@contextlib.contextmanager
def on_path(directory: str):
    """`directory` prepended to PATH for the body."""
    with env(PATH=os.pathsep.join([directory, os.environ.get("PATH", "")])):
        yield

# The columns are Hermes' own: session_model_usage carries the per-model, per-
# task attribution rows, and the collector reads model plus the four disjoint
# counters. `keyed` adds the rest of the row's primary key, which older stores
# predate -- both shapes have to work, so both are buildable here.

KEYED_COLUMNS = ("session_id TEXT, model TEXT, billing_provider TEXT,"
                 " billing_base_url TEXT, billing_mode TEXT, task TEXT,")
PLAIN_COLUMNS = "session_id TEXT, model TEXT,"


def make_store(dirpath: str, rows=(), keyed: bool = False, name: str = "state.db") -> str:
    path = os.path.join(dirpath, name)
    conn = sqlite3.connect(path)
    conn.execute(
        f"CREATE TABLE {client.USAGE_TABLE} "
        f"({KEYED_COLUMNS if keyed else PLAIN_COLUMNS}"
        " input_tokens INT, output_tokens INT, cache_read_tokens INT,"
        " cache_write_tokens INT, first_seen REAL, last_seen REAL)")
    for row in rows:
        conn.execute(f"INSERT INTO {client.USAGE_TABLE} "
                     f"VALUES ({','.join('?' * len(row))})", row)
    conn.commit()
    conn.close()
    return path


def bump(db: str, session: str, **counters) -> None:
    """Advance a session's cumulative counters, the way Hermes does."""
    sets = ", ".join(f"{col} = ?" for col in counters)
    conn = sqlite3.connect(db)
    conn.execute(f"UPDATE {client.USAGE_TABLE} SET {sets} WHERE session_id = ?",
                 (*counters.values(), session))
    conn.commit()
    conn.close()


def collect(home: str, state_path: str, days: int = 28) -> dict:
    """from_hermes with its own ledger, and without its chatter on stdout."""
    with contextlib.redirect_stdout(io.StringIO()):
        return client.from_hermes(days, home=home, state_path=state_path)


@contextlib.contextmanager
def sandbox():
    """A Hermes home and a ledger beside it, both thrown away afterwards."""
    with tempfile.TemporaryDirectory() as home:
        yield home, os.path.join(home, "ledger.json")


@contextlib.contextmanager
def no_failures():
    """Run with a clean FAILURES list and hand back what was appended.

    The collector records read failures in a module global. Tests that provoke
    one have to see it, and must not leave it behind for the next test.
    """
    was, client.FAILURES = client.FAILURES, []
    try:
        yield client.FAILURES
    finally:
        client.FAILURES = was


# 1. no usage storage at all

def test_a_home_with_no_store_is_a_failure_when_it_was_configured() -> None:
    with sandbox() as (home, ledger), no_failures() as failures:
        missing = os.path.join(home, "not-here")
        got = collect(missing, ledger)
    check(got == {}, "a home with no store collects nothing")
    check(len(failures) == 1 and f"no {client.USAGE_TABLE} store" in failures[0],
          "a configured home with no store is recorded as a FAILED read")
    check(missing in failures[0],
          "and the failure names the home that was actually searched")


def test_a_database_without_the_usage_table_is_not_a_store() -> None:
    with sandbox() as (home, ledger), no_failures() as failures:
        sqlite3.connect(os.path.join(home, "state.db")).close()
        got = collect(home, ledger)
    check(got == {}, "a state.db with no usage table collects nothing")
    check(bool(failures), "and is a read failure, not a quiet zero")
    check(not os.path.exists(ledger), "and no ledger is written beside it")


def test_a_table_missing_the_token_columns_is_not_a_store() -> None:
    with sandbox() as (home, _ledger):
        db = os.path.join(home, "state.db")
        conn = sqlite3.connect(db)
        conn.execute(f"CREATE TABLE {client.USAGE_TABLE} (session_id TEXT, model TEXT)")
        conn.commit()
        conn.close()
        check(not client._has_usage_table(db),
              "a usage table without the token columns is not one we can diff")


# 2. an empty store

def test_an_empty_store_reports_nothing_and_never_fails() -> None:
    with sandbox() as (home, ledger), no_failures() as failures:
        make_store(home)
        got = collect(home, ledger)
    check(got == {}, "an empty store reports nothing")
    check(not failures, "an empty store is quiet, not a failure")


def test_an_empty_store_says_so_rather_than_saying_nothing() -> None:
    """The silence this whole change exists to end.

    A store nobody found and a store with nothing in it both printed nothing
    and totalled zero, so a run could not tell the two apart -- which is
    exactly the state an install lands in when HERMES_HOME points somewhere
    unexpected.
    """
    with sandbox() as (home, ledger):
        make_store(home)
        collect(home, ledger)                       # the first run baselines
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            client.from_hermes(28, home=home, state_path=ledger)
    check("holds no usage rows yet" in out.getvalue(),
          "an empty store names itself rather than reporting a silent zero")


# 3 & 4. baseline, then deltas

def test_the_first_run_baselines_and_the_second_reports_the_delta() -> None:
    with sandbox() as (home, ledger):
        now = time.time()
        db = make_store(home, rows=[
            # Spans days, so its lifetime cannot be attributed to one of them.
            ("s1", "gpt-5.5", 1000, 2000, 30, 40, now - 40 * 86400, now - 3600),
        ])
        first = collect(home, ledger)
        check(first == {}, "the first run records a baseline and reports nothing")
        check(os.path.exists(ledger), "and writes the ledger it baselined into")

        unchanged = collect(home, ledger)
        check(unchanged == {}, "an unchanged store must not republish the lifetime total")

        bump(db, "s1", input_tokens=1050, output_tokens=2004,
             cache_read_tokens=35, cache_write_tokens=40)
        got = collect(home, ledger)
    check(got == {TODAY: {"gpt-5.5": {"input": 50, "output": 4,
                                      "cache_read": 5, "cache_write": 0}}},
          "the next run reports the delta, not the lifetime")


def test_a_same_day_session_is_backfilled_onto_the_day_it_ran() -> None:
    with sandbox() as (home, ledger):
        ran = datetime.date.today() - datetime.timedelta(days=3)
        # Midday, so an hour either side cannot cross midnight and flake.
        noon = datetime.datetime.combine(ran, datetime.time(12, 0)).timestamp()
        make_store(home, rows=[
            ("done", "gpt-5.5", 7, 3, 0, 0, noon, noon + 3600),
            ("spanning", "gpt-5.5", 500, 0, 0, 0, noon - 9 * 86400, noon),
        ])
        got = collect(home, ledger)
    check(list(got) == [ran.isoformat()],
          "a finished same-day session belongs to the day it ran")
    check(got[ran.isoformat()]["gpt-5.5"] == {"input": 7, "output": 3,
                                              "cache_read": 0, "cache_write": 0},
          "and a session spanning days is baselined rather than invented onto one")


def test_a_brand_new_agents_first_turn_is_reported() -> None:
    """An empty snapshot means "looked, found nothing", not "never looked".

    Conflating the two ate a new agent's first session permanently: the empty
    snapshot read as un-baselined, so the run that finally found a row
    re-baselined instead of reporting it.
    """
    with sandbox() as (home, ledger):
        db = make_store(home)
        check(collect(home, ledger) == {}, "an empty store reports nothing")
        conn = sqlite3.connect(db)
        conn.execute(f"INSERT INTO {client.USAGE_TABLE} VALUES (?,?,?,?,?,?,?,?)",
                     ("first", "gpt-5.5", 100, 20, 0, 0, time.time(), time.time()))
        conn.commit()
        conn.close()
        got = collect(home, ledger)
    check(got == {TODAY: {"gpt-5.5": {"input": 100, "output": 20,
                                      "cache_read": 0, "cache_write": 0}}},
          "a new agent's FIRST turn is reported, not swallowed by the baseline")


# 5, 6 & 7. several models, several days, no double counting

def test_several_models_are_kept_apart() -> None:
    with sandbox() as (home, ledger):
        now = time.time()
        db = make_store(home, keyed=True, rows=[
            ("s1", "gpt-5.5", "", "", "", "", 10, 0, 0, 0, now - 5 * 86400, now),
            ("s1", "claude-opus-5", "", "", "", "", 20, 0, 0, 0, now - 5 * 86400, now),
        ])
        collect(home, ledger)
        conn = sqlite3.connect(db)
        conn.execute(f"UPDATE {client.USAGE_TABLE} SET input_tokens = 15"
                     " WHERE model = 'gpt-5.5'")
        conn.execute(f"UPDATE {client.USAGE_TABLE} SET output_tokens = 7"
                     " WHERE model = 'claude-opus-5'")
        conn.commit()
        conn.close()
        got = collect(home, ledger)
    check(sorted(got[TODAY]) == ["claude-opus-5", "gpt-5.5"],
          "each model gets its own row")
    check(got[TODAY]["gpt-5.5"] == {**ZERO, "input": 5}
          and got[TODAY]["claude-opus-5"] == {**ZERO, "output": 7},
          "and its own counters, not the other one's")


def test_several_days_accumulate_without_replacing_each_other() -> None:
    """The ledger is what makes multi-day reporting correct.

    The server upserts a (day, model) row with DO UPDATE SET = excluded, so a
    run that sent only its newest delta would clobber the earlier delta from
    the same day. The day's RUNNING TOTAL is what goes out.
    """
    with sandbox() as (home, ledger):
        earlier = (datetime.date.today() - datetime.timedelta(days=2)).isoformat()
        now = time.time()
        db = make_store(home, rows=[("s1", "gpt-5.5", 0, 0, 0, 0,
                                     now - 5 * 86400, now)])
        collect(home, ledger)
        # A day already in the ledger, as a run two days ago would have left it.
        state = json.load(open(ledger))
        state["daily"][earlier] = {"gpt-5.5": {**ZERO, "input": 11}}
        client._save_state(ledger, state)

        bump(db, "s1", input_tokens=4)
        first = collect(home, ledger)
        check(sorted(first) == [earlier, TODAY], "an earlier day stays in the window")
        check(first[earlier]["gpt-5.5"]["input"] == 11, "with the total it already had")

        bump(db, "s1", input_tokens=9)
        second = collect(home, ledger)
    check(second[TODAY]["gpt-5.5"]["input"] == 9,
          "a second run the same day sends the day's running total, not the last delta")
    check(second[earlier]["gpt-5.5"]["input"] == 11,
          "and does not disturb a day it did not touch")


def test_an_unchanged_store_never_reports_the_same_tokens_twice() -> None:
    with sandbox() as (home, ledger):
        now = time.time()
        db = make_store(home, rows=[("s1", "gpt-5.5", 0, 0, 0, 0,
                                     now - 5 * 86400, now)])
        collect(home, ledger)
        bump(db, "s1", input_tokens=100)
        once = collect(home, ledger)
        twice = collect(home, ledger)
        thrice = collect(home, ledger)
    check(once[TODAY]["gpt-5.5"]["input"] == 100, "the delta is reported once")
    check(twice == once and thrice == once,
          "and re-running adds nothing: the day's total stays where it was")


def test_a_counter_going_backwards_credits_nothing() -> None:
    with sandbox() as (home, ledger):
        now = time.time()
        db = make_store(home, rows=[("s1", "gpt-5.5", 500, 0, 0, 0,
                                     now - 5 * 86400, now)])
        collect(home, ledger)
        bump(db, "s1", input_tokens=600)
        collect(home, ledger)
        bump(db, "s1", input_tokens=1)          # session reset or replaced
        got = collect(home, ledger)
    check(got[TODAY]["gpt-5.5"]["input"] == 100,
          "a reset session credits nothing, never a negative that unpicks a correct day")


# 8. a corrupt ledger

def test_a_corrupt_ledger_rebaselines_rather_than_replaying_history() -> None:
    with sandbox() as (home, ledger), no_failures() as failures:
        now = time.time()
        db = make_store(home, rows=[("s1", "gpt-5.5", 900, 0, 0, 0,
                                     now - 40 * 86400, now)])
        collect(home, ledger)
        with open(ledger, "w") as f:
            f.write("{not json")
        lost = collect(home, ledger)
        check(lost == {}, "a lost ledger reports nothing rather than replaying a lifetime")
        check(not failures, "a lost ledger costs one run, it does not fail the report")
        bump(db, "s1", input_tokens=901)
        got = collect(home, ledger)
    check(got[TODAY]["gpt-5.5"]["input"] == 1,
          "and the run after it reports the delta, not the lifetime")


def test_a_corrupt_store_is_a_failure_and_not_a_zero() -> None:
    with sandbox() as (home, ledger), no_failures() as failures:
        db = os.path.join(home, "state.db")
        with open(db, "wb") as f:
            f.write(b"SQLite format 3\x00this is not a database at all")
        got = collect(home, ledger)
    check(got == {}, "a corrupt store collects nothing")
    check(bool(failures), "and is recorded as a FAILED read, which stops the report")


# 9. path handling, Windows included

def test_the_windows_platform_default_is_localappdata() -> None:
    """Hermes resolves its home as HERMES_HOME, else %LOCALAPPDATA%/hermes on
    Windows and ~/.hermes elsewhere. Trying ~/.hermes on Windows looks in a
    directory Hermes never writes a store into."""
    local = os.path.join("C:", os.sep, "Users", "x", "AppData", "Local")
    keep = {k: os.environ.get(k) for k in ("HERMES_HOME", "LOCALAPPDATA")}
    os.environ.pop("HERMES_HOME", None)
    os.environ["LOCALAPPDATA"] = local
    # os.name is what the collector branches on, and this suite has to pin the
    # Windows answer while running on whatever the CI box is.
    was, os.name = os.name, "nt"
    try:
        homes = client.hermes_homes()
    finally:
        os.name = was
        restore(keep)
    check(homes[0] == os.path.join(local, "hermes"),
          "on Windows the first home tried is %LOCALAPPDATA%/hermes")
    check(any(h.endswith(".hermes-life") for h in homes),
          "and the Plow layout stays in the list as a fallback")


def test_hermes_home_wins_over_every_default() -> None:
    told = os.path.join("somewhere", "else")
    with env(HERMES_HOME=told):
        check(client.hermes_homes() == [told],
              "HERMES_HOME is the only home tried when it is set")
        check(client.hermes_homes(home="explicit") == ["explicit"],
              "and an explicit home wins over even that")


def test_a_path_the_uri_parser_would_mangle_still_opens() -> None:
    """'?' and '#' belong to the URI parser, so a store under a directory
    holding either used to open a different file, or none at all."""
    with tempfile.TemporaryDirectory() as tmp:
        awkward = os.path.join(tmp, "a dir #1 ? here")
        os.makedirs(awkward)
        db = make_store(awkward, rows=[("s", "m", 1, 1, 0, 0, 0, 0)])
        check(client._has_usage_table(db),
              "a store under a path with URI punctuation in it is still readable")


def test_the_store_is_found_one_directory_down() -> None:
    """Discovery by SCHEMA, not by a guessed filename: an install that keeps
    the store in a subdirectory of its home is still measured."""
    with sandbox() as (home, ledger):
        nested = os.path.join(home, "runtime")
        os.makedirs(nested)
        os.makedirs(os.path.join(home, "logs"))     # a sibling with nothing in it
        db = make_store(nested, rows=[("s", "gpt-5.5", 5, 0, 0, 0, 0, 0)])
        check(client.find_store([home]) == db, "a nested store is found")
        collect(home, ledger)
        bump(db, "s", input_tokens=25)
        got = collect(home, ledger)
    check(got[TODAY]["gpt-5.5"]["input"] == 20, "and reported from")


def test_the_live_store_wins_over_a_copy_of_it() -> None:
    with sandbox() as (home, _ledger):
        live = make_store(home, rows=[("s", "gpt-5.5", 9, 0, 0, 0, 0, 0)])
        backups = os.path.join(home, "backups")
        os.makedirs(backups)
        make_store(backups, rows=[("s", "gpt-5.5", 1, 0, 0, 0, 0, 0)])
        check(client.find_store([home]) == live,
              "the store in the home itself is preferred over a copy beneath it")


# 10, 11 & 12. agentsview stays optional

def test_agentsview_missing_is_not_a_failure() -> None:
    with tempfile.TemporaryDirectory() as empty, no_failures() as failures:
        with env(PATH=empty), contextlib.redirect_stdout(io.StringIO()) as out:
            got = client.from_agentsview(28)
    check(got == {}, "an absent agentsview collects nothing")
    check(not failures, "and is skipped, not failed")
    check("not installed" in out.getvalue(), "and says so")


def test_agentsview_is_read_when_it_is_there() -> None:
    rows = [{"date": "2026-09-01",
             "modelBreakdowns": [{"modelName": "gpt-5.5", "inputTokens": 3,
                                  "outputTokens": 4, "cacheReadTokens": 1,
                                  "cacheCreationTokens": 2}]}]
    with fake_agentsview(json.dumps(rows)) as path, no_failures() as failures:
        with on_path(path), contextlib.redirect_stdout(io.StringIO()):
            got = client.from_agentsview(28)
    check(got == {"2026-09-01": {"gpt-5.5": {"input": 3, "output": 4,
                                             "cache_read": 1, "cache_write": 2}}},
          "an installed agentsview is read into the same shape as the Hermes store")
    check(not failures, "and a good read is not a failure")


def test_a_broken_agentsview_does_not_stop_the_hermes_collector() -> None:
    with fake_agentsview("not json at all") as path, no_failures() as failures:
        with on_path(path), contextlib.redirect_stdout(io.StringIO()):
            broken = client.from_agentsview(28)
        # The Hermes collector runs AFTER that failure, with it still on the
        # list: a broken agentsview must not stop it from measuring.
        with sandbox() as (home, ledger):
            now = time.time()
            db = make_store(home, rows=[("s", "gpt-5.5", 1, 0, 0, 0,
                                         now - 5 * 86400, now)])
            collect(home, ledger)
            bump(db, "s", input_tokens=61)
            hermes = collect(home, ledger)
        check(broken == {}, "a broken agentsview yields nothing")
        check(any("agentsview" in f for f in failures),
              "and is recorded as a FAILED read, which stops the report")
    check(hermes[TODAY]["gpt-5.5"]["input"] == 60,
          "while the Hermes collector still measures independently of it")


@contextlib.contextmanager
def fake_agentsview(stdout_text: str):
    """A stand-in agentsview on PATH, in the form the platform can launch."""
    with tempfile.TemporaryDirectory() as tmp:
        if os.name == "nt":
            exe = os.path.join(tmp, "agentsview.cmd")
            with open(exe, "w", encoding="utf-8") as f:
                f.write("@echo off\r\necho " + stdout_text + "\r\n")
        else:
            exe = os.path.join(tmp, "agentsview")
            with open(exe, "w", encoding="utf-8") as f:
                f.write("#!/bin/sh\ncat <<'OUT'\n" + stdout_text + "\nOUT\n")
            os.chmod(exe, 0o755)
        yield tmp


# 13. optional variables are optional

def test_the_collector_runs_with_no_optional_variables_set() -> None:
    absent = dict.fromkeys(("HERMES_HOME", "AGENTSVIEW_CONFIG", "LOCALAPPDATA",
                            *client.AGENTSVIEW_SOURCE_DIRS))
    with env(**absent), sandbox() as (home, ledger), no_failures() as failures:
        now = time.time()
        db = make_store(home, rows=[("s", "gpt-5.5", 1, 0, 0, 0, now - 5 * 86400, now)])
        collect(home, ledger)
        bump(db, "s", input_tokens=8)
        got = collect(home, ledger)
        homes = client.hermes_homes()
        child = client._child_env()
    check(got[TODAY]["gpt-5.5"]["input"] == 7,
          "an explicit home needs no environment variable at all")
    check(not failures, "and nothing about a missing optional variable is a failure")
    check(bool(homes), "the default home list is never empty")
    check(child.get("PATH"), "and the child environment always carries a PATH")


def test_the_child_path_default_is_the_platforms_own() -> None:
    with env(PATH=None):
        check(client._child_env()["PATH"] == os.defpath,
              "with no PATH inherited, the child gets os.defpath, not a Unix literal")


# 14. nothing secret leaves the machine

SECRETS = {
    "PLOW_AGENT_TOKEN": "plow-secret-value-must-not-appear",
    "AGENT_INDEX_KEY": "aik_" + "s" * 43,
    "AWS_SECRET_ACCESS_KEY": "aws-secret-must-not-appear",
    "GITHUB_TOKEN": "ghp_must_not_appear",
}


def test_no_credential_reaches_a_child_process() -> None:
    with env(**SECRETS):
        child = client._child_env()
    leaked = sorted(k for k in SECRETS if k in child)
    check(not leaked, f"no credential is handed to agentsview (leaked: {leaked})")
    check(not any(v in child.values() for v in SECRETS.values()),
          "and none of their values arrives under another name")


def test_the_payload_carries_counters_and_nothing_else() -> None:
    """What merge() produces IS the request body. Whatever is not in this
    shape cannot reach the Index."""
    with sandbox() as (home, ledger):
        now = time.time()
        db = make_store(home, keyed=True, rows=[
            # Every free-text column carries something that must never be sent.
            ("session-private-id", "gpt-5.5", "provider-secret", "https://internal.example",
             "mode-secret", "a private task title", 1, 0, 0, 0, now - 5 * 86400, now),
        ])
        collect(home, ledger)
        bump(db, "session-private-id", input_tokens=13)
        payload = {"days": client.merge(collect(home, ledger))}

    body = json.dumps(payload)
    for private in ("session-private-id", "provider-secret", "internal.example",
                    "mode-secret", "a private task title", home):
        check(private not in body, f"the payload does not carry {private!r}")
    day = payload["days"][0]
    check(sorted(day) == ["date", "models"], "a day carries a date and its models, nothing else")
    check(sorted(day["models"][0]) == ["cache_read", "cache_write", "input", "model", "output"],
          "and a model row carries its name and the four counters, nothing else")


def test_a_failure_message_never_carries_the_stored_key() -> None:
    with sandbox() as (home, ledger), no_failures() as failures:
        key = "aik_" + "s" * 43
        client.save_private(os.path.join(home, ".agent-index.json"),
                            json.dumps({"install_id": "install-test", "key": key}))
        sqlite3.connect(os.path.join(home, "state.db")).close()     # no usage table
        collect(home, ledger)
    check(bool(failures), "the unreadable store is reported")
    check(not any(key in f for f in failures),
          "and the report does not carry the key that happens to live beside it")


def main() -> int:
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            print(f"{name}:")
            fn()
    print()
    if FAILURES:
        print(f"FAILED ({len(FAILURES)}):")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("all Hermes usage collector checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())