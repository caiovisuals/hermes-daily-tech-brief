---
name: tb-setup
description: First contact and configuration — meet the owner, find out what they build, and write the brief config that every later run reads. Use when config.json is missing, when a new owner says anything at all, or when they ask to change their stack, language, schedule or brief length.
---

# Setup

The one thing that makes this agent worth installing is knowing what the owner
builds. Everything else is a feed reader.

## The opener

This is first contact, over text, from someone who just deployed you. Keep it
to a few lines. Say what you are, ask the one question that matters, and stop.

Something in this shape, in your own words:

> I'm your tech news desk.
> Every morning I read the industry and send you the few things that actually touch what you build.
>
> What do you work with? Languages, frameworks, cloud, databases —
> whatever you would want to hear about the moment it breaks or ships.

Do not list your features. Do not ask five questions at once. The stack is the
only answer you cannot proceed without.

## What to gather

Ask for the stack first. Get the rest from the conversation or take the
default; do not interrogate.

| Field | Default | How to get it |
|---|---|---|
| `stack` | none | Ask. This is the question. |
| `language` | `en-US` | Use the language they are writing to you in. |
| `owner` | empty | Their name, if it comes up naturally. |
| `hour` | 8 | "What time do you want it?" — only if they raise it. |
| `topics` | all | Only if they say they want a narrower beat. |
| `max_stories` | 8 | Only if they ask for shorter or longer. |
| `window_hours` | 24 | Leave it. |

Stack tags are free text. Known ones are listed in
`/var/lib/hermes/skills/tb-brief/references/topics.md` and resolve into related
terms, so `python` also catches Django and PyPI. An unknown tag still works,
matched literally. Do not make the owner pick from a list: take what they say,
map the obvious ones, and keep the rest as they wrote them.

If they answer with a job title instead of technologies ("backend dev"), ask
once for specifics. If they still will not say, write an empty stack and tell
them the brief will be generic until they do.

## Write it

```
python3 /var/lib/hermes/skills/tb-setup/scripts/write_config.py \
  --owner "<name>" --language "<tag>" --stack "<comma separated>" --hour <0-23>
```

It validates ranges and topics and refuses bad input rather than writing it.
Paste its output if it fails.

## Then register the schedule

Configuration alone sends nothing. Run `tb-schedule` immediately after writing
the config, in the same turn, and report what it says. An owner who has been
set up but never scheduled gets silence and assumes the agent is broken.

## Changing things later

Any of these is a reason to come back here: a new language, a different time, a
stack that grew, a brief that is too long. Re-run `write_config.py` with the
full set of values — it replaces the file, it does not merge — then run
`tb-schedule` with `--replace` if the hour or minute changed.

## Confirm and offer

Close by telling them what you will send and when, in one line, and offer to
run the first brief now rather than making them wait until tomorrow. Most
people want to see it before they trust it.