# Contributing

Thanks for looking. This is a small, opinionated repository: a persona, three
skills, an image that carries them, and tests for the parts that must not be
left to judgement. Most of it is prose the agent reads, which means a change to
a Markdown sheet is a change to behaviour and gets reviewed like code.

## What lives where

| Path | What it is |
|---|---|
| `runtime/SOUL.md` | The persona. Replaces the base image's own. Voice, scope, and the non-negotiable rules. |
| `SKILL.md` | The agent manifest: metadata, and where configuration and the schedule actually live. Behaviour is in the sheets below. |
| `tb-brief/` | The daily brief: the sheet, `references/` (feeds, sources, topics, quality rules), and the three scripts. |
| `tb-setup/` | First-run conversation; writes `config.json`. |
| `tb-schedule/` | Registers the daily cron row. Bring-up step, run once after setup. |
| `image/s6-overlay/` | The hourly Agent Index reporter service. |
| `vendor/client.pin` | The commit and sha256 of the Agent Index client, fetched at build. |
| `templates/`, `examples/` | The brief's shape, and a rendered example of it. |
| `tests/` | Plain `python3` scripts, no framework. |

Three scripts own everything deterministic — collection, ranking,
verification — and the agent owns judgement. That split is the design. If you
find yourself moving editorial decisions into Python or verification into a
prompt, stop and open an issue first.

## Getting set up

You need `python3` for the tests and `docker` + `docker compose` to run the
agent. The scripts are **standard library only** and there is nothing to
install.

```sh
# A Plow credential, written beside compose.yml. Never committed.
bin/plow-agents login && bin/plow-agents mint

docker compose up --build -d
```

The agent's home is a named volume that shadows the image, so an edit to
`SOUL.md` or to a skill is only picked up once the volume is gone:

```sh
docker compose down -v && docker compose up --build -d
```

That is the loop for anything the agent reads. For the Python scripts you do not
need the container at all — they run against local files:

```sh
python3 tb-brief/scripts/collect_news.py --hours 24 --out /tmp/candidates.json
python3 tb-brief/scripts/collect_news.py --check-feeds
```

## Tests

No framework, so they run anywhere the skills run. Run all of them before
opening a pull request — CI runs exactly this loop:

```sh
for suite in tests/test_*.py; do python3 "$suite"; done
```

| Suite | What it pins |
|---|---|
| `test_collect.py` | Feed parsing, for every shape publishers ship, and the catalog's own schema |
| `test_filtering.py` | Deduplication and stack matching |
| `test_render.py` | The no-fabrication guarantee, and the archive path |
| `test_schedule.py` | The cron spec's dangerous parts |
| `test_agent_index_service.py` | The reporter, in a sandbox |

Write new tests in the same style: plain `python3`, a `check(condition, label)`
helper, a non-zero exit on failure, and no dependencies. Follow the existing
bias toward testing behaviour over text — `test_agent_index_service.py` boots
the real `run` script against a fake container environment and a stub client,
because a test that greps for a string passes on a service that would not boot.

Changes that need a test: anything in deduplication or ranking, anything in the
cron spec, anything in the reporter's exit-code handling, and any bug you fix in
a script.

## The most common contributions

**Adding a feed** — edit `tb-brief/references/feeds.json`. Every entry needs:

```json
{ "id": "rust", "name": "Rust Blog", "url": "https://blog.rust-lang.org/feed.xml",
  "tier": 1, "topics": ["devtools"], "stack": ["rust"] }
```

- `id` unique and lowercase; `name` as the publication calls itself.
- `tier`: **1** primary source (a vendor, project or authority publishing about
  itself), **2** reputable editorial newsroom, **3** community aggregator or
  opinion. Ranking trusts this field, so do not inflate it.
- `topics` from: `ai`, `tech`, `devtools`, `cloud`, `security`, `startups`,
  `research`.
- `stack` lists the tags the feed is authoritative for — empty is fine for a
  general newsroom.

Then prove it parses: `python3 tb-brief/scripts/collect_news.py --check-feeds`,
and say in the PR that you ran it. Prefer a publisher's own feed over an
aggregator's copy of it, and prefer full-text feeds over headline-only ones.

**Adding stack keywords** — `tb-brief/references/stack-keywords.json` maps a
stack tag the reader declares to the terms that signal a story touches it
(`kubernetes` → `k8s`, `kubectl`, `helm`, `eks`, …). Matching is
case-insensitive against the headline and summary, and an unknown tag falls
back to matching itself literally — so a tag is only worth adding when its
real-world vocabulary is wider than its name. Keep terms specific: a term that
shows up in unrelated stories pulls noise to the top of the brief.

A term is anchored at whichever of its ends is alphanumeric, so `react` does
not fire on "reactor" — but a term written to be followed by something, like
`go 1.`, `gpt-` or `cve-`, matches the version or identifier that comes next.
A term ending in a letter is a whole word, not a prefix: `fine-tun` matches
nothing, `fine-tuning` matches. `test_filtering.py` checks that every shipped
term can match its own text, so a mapping that silently does nothing fails
there rather than in a brief.

**Editorial rules** — `tb-brief/references/quality-rules.md` and the rules
sections of `SOUL.md` and `SKILL.md`. These change what the agent writes. Say in
the PR what a brief would have looked like before and after.

## Pull requests

1. Branch off `main`, one topic per branch.
2. Run the test suites, plus `--check-feeds` if you touched feeds.
3. Write a commit message that says why, in the imperative: `rank security
   advisories above stack matches`, not `update filter`.
4. In the PR body: what changed, what you ran, and — for behaviour changes —
   what the brief looks like before and after. A rendered snippet beats a
   description.
5. Expect review comments on prose as well as code. The sheets *are* the
   program.

Bug reports and feature ideas are welcome as issues. For anything that reshapes
the workflow, open the issue before the PR.

**Security bugs do not go in issues or pull requests.** See
[SECURITY.md](SECURITY.md) for the private channel.

## License

MIT. By contributing, you agree your contributions are licensed under it — see
[LICENSE](LICENSE).