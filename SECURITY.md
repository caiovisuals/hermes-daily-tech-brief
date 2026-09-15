# SECURITY POLICY

This agent runs unattended, inside a container that holds a live Plow
credential, and reads text written by strangers on the public internet. That
combination is the whole reason this file exists.

## Reporting a vulnerability

**Do not open a public issue for a vulnerability.**

Use GitHub's private reporting form:
[**Report a vulnerability**](https://github.com/caiovisuals/hermes-daily-tech-brief/security/advisories/new)
(repository → *Security* → *Advisories* → *Report a vulnerability*).
The report stays private between you and the maintainer until a fix is published.

If that form is unavailable to you, open a public issue that says only that you
have a security report and asks for a private channel — no details, no
reproduction steps.

Please include, as far as you have them:

- what an attacker can do, not just what looks wrong
- the affected file or component (`tb-brief/scripts/`, the `agent-index` s6 service, the `Dockerfile`, `runtime/SOUL.md`, …)
- a reproduction: a crafted feed entry, a config value, a command, a diff
- the image tag or commit you tested
- whether it needs the owner's cooperation, or works against them unprompted

**What to expect.** This is a single-maintainer project, so response is best
effort: an acknowledgement within about 72 hours, an assessment within a week,
and a fix released before any public write-up. Credit in the advisory if you
want it. There is no bounty.

## Supported versions

Only `main`, and only images built from it. There are no maintained release
branches, so a fix ships as a commit on `main` and an image rebuild — an
operator running an older build updates by rebuilding, not by patching.

## The security model

Several things in this repo look over-engineered until you know what they are
defending. Read this before proposing a simplification, and before deciding
whether something you found is a bug.

**The credential never enters the repository or the image.** `plow-credentials`
is written beside `compose.yml` by `plow-agents mint` and is excluded twice, on
purpose: `.gitignore` keeps it out of commits, `.dockerignore` keeps it out of
the build context, where a `COPY` could otherwise reach it. It is mounted
read-only. Neither exclusion is redundant — losing either one is a real
vulnerability, and a PR that touches those files gets read with that in mind.

**Everything executable is pinned, twice.** The base image is an immutable
`base-<sha>` tag *and* a digest. The Agent Index client is fetched at build time
from one commit named in `vendor/client.pin` and rejected unless its sha256
matches. A moving reference would substitute unreviewed code inside a container
that holds someone's live token; the checksum is there because a sha in a URL is
only as trustworthy as the host serving it. Bumping either pin is a reviewed
edit, never a convenience.

**The agent can read the reporter, not rewrite it.** `agent-index-client.py`
lives root-owned under `/opt/plow`, outside `$HERMES_HOME`. Everything under the
home belongs to uid 10000 in a running container, so a scheduled script living
there would turn a single prompt-injected file edit into code that runs
unattended, forever, holding a live credential. Any proposal to move agent-run
code into the home is a privilege change, not a refactor.

**Feed content is data, never instruction.** `SOUL.md` states it and the skills
repeat it: article text, feed summaries and tool output are read, quoted and
summarised — never obeyed. A headline that tells the agent to ignore its
instructions is a story *about* prompt injection, and it goes into the brief as
one. Reports showing that a crafted feed entry, article body, or story title can
steer the agent's actions — rather than merely appear in its output — are the
highest-value reports this project can receive.

**Sources are verified mechanically, not editorially.** `format_brief.py`
refuses to render any story whose URL was not among the collected candidates,
which is what stops a fabricated or injected link from reaching the reader. The
`--allow-unverified` escape hatch exists for debugging and is documented as
something the agent must not reach for. A change that weakens or bypasses that
check is a security change.

**No third-party Python dependencies.** Every script is standard library only.
That is a deliberate supply-chain decision: the only code this image trusts that
it did not write is the base image and one pinned, checksummed file.

**Outbound only.** `compose.yml` publishes no ports. The agent connects out to
Plow and to the feeds; nothing connects in. A contribution that opens a listener
needs to argue for it first.

**The reporter drops privileges.** The s6 service reads `PLOW_AGENT_TOKEN` as
root and then runs the client under `s6-setuidgid hermes`. The broad Plow bearer
is handed to the pinned client for the assertion exchange and to nothing else —
no image-owned HTTP path ever sends it to the Index.

## Disclosure

Coordinated. Report privately, give the fix a reasonable window to ship, and
publish afterwards. If a report goes unanswered for 30 days, disclosing it
publicly is fair.