---
name: tb-schedule
description: The daily brief's cron row — registering it, checking it is really active, and changing the delivery time. Use after setup, after any rebuild of the agent's home, when the owner changes their brief time, or when they say the brief stopped arriving.
---

# Schedule

One row: the daily brief, at the owner's hour, delivered to their chat.

## Why this is a skill and not a note

`hermes cron` persists jobs to `/var/lib/hermes/cron/jobs.json`, and nothing
replays that file on a rebuild. A rebuilt agent comes up with no schedule and
no signal that anything is wrong — the brief simply stops arriving, which looks
exactly like a quiet news day. Keeping the row in a script means "set up my
brief" replays a reviewed spec instead of improvising a schedule from a
sentence.

## Registering

**This is a bring-up step.** Run it right after `tb-setup`, and again after any
rebuild of the home.

You are already inside the container, running as the gateway's own uid:

    /var/lib/hermes/skills/tb-schedule/scripts/register_crons.py

**Then paste its output verbatim and report its exit status. The run is not
done until you have.** The script signals every refusal it has through its
output and a non-zero exit, and a turn does not propagate an exit code. If you
summarise instead of pasting, "set up the schedule, though something was
already there" is a perfectly honest sentence describing a run that failed, and
the owner has no way to tell.

Run it from a turn, not from a bare `docker exec`. It needs
`PLOW_HOME_CHANNEL` from the gateway's environment to know which chat the brief
goes to, and it refuses to register a job that would deliver nowhere.

## What it refuses, and why

- **No `config.json`** — there is no hour to register. Run `tb-setup` first.
- **An hour outside 0-23** — a cron row that never fires.
- **A blank `PLOW_HOME_CHANNEL`** — the brief would be delivered nowhere and
  the cron would still report success.
- **The job already registered and active** — re-registering duplicates it and
  the owner gets two briefs a day. It reports and stops.
- **The job registered but PAUSED** — it will never fire, and registering a
  second copy is not the fix. Resume it, or re-create with `--replace`.
- **An unreadable `jobs.json`** — it raises rather than assuming nothing is
  scheduled, because assuming that duplicates every job.

Only a missing `jobs.json` means nothing is scheduled.

## Changing the time

Write the new hour with `tb-setup` first, then:

    /var/lib/hermes/skills/tb-schedule/scripts/register_crons.py --replace

This deletes the existing row before creating the new one. If the delete fails
it stops rather than leaving two rows behind.

## When the owner says the brief stopped

Check in this order.

1. Is the row there and active? Run the script; it reports rather than
   duplicating.
2. Was the home rebuilt recently? Then it is gone and this is the fix.
3. Is it paused? `hermes cron resume tb-daily-brief`.
4. Row is fine and active? Then the schedule is not the problem. The brief may
   have run and found nothing worth sending, which is a legitimate outcome, or
   the feeds failed. Run `tb-brief` by hand and read what it says.

The job fires in the container's timezone. There is no per-job zone, so the
hour in the config is that zone's hour.