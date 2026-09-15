# HERMES DAILY TECH BRIEF

Your daily intelligence briefing for technology and AI.<br/>

Hermes Tech Brief is a Hermes agent that researches the latest technology and artificial intelligence news and delivers a concise, source-backed daily briefing at a schedule defined by the user.<br/>

Instead of manually checking dozens of websites every morning, Hermes researches the news for you, identifies the most relevant stories, summarizes what happened, explains why it matters, and provides the original sources.

## Features

- Daily technology and AI news briefings
- AI-focused news monitoring
- Technology and software development coverage
- Multi-source research
- Relevance-based story selection
- Duplicate story detection
- Concise summaries
- "Why it matters" context
- Original source for every story
- Configurable language
- Configurable daily schedule
- Source and information quality rules

## Build and run

The image is the `plow-hermes-agent` base with this repo's persona and three
skills copied over it. The base tag is pinned by digest in the `Dockerfile`;
see the comment there before bumping it.

```sh
# 1. A Plow credential, written beside compose.yml. Never committed --
#    .gitignore and .dockerignore both exclude it.
bin/plow-agents login && bin/plow-agents mint

# 2. Build and start.
docker compose up --build -d
```

The agent's home is a named volume that shadows the image, so an edit to
`runtime/SOUL.md` or to a skill is only picked up once it is gone:

```sh
docker compose down -v && docker compose up --build -d
```

First boot has no `config.json`, so `SOUL.md` routes the owner to `tb-setup`.
Run `tb-schedule` once after that to register the daily cron row -- a rebuild
does not replay it.

## Agent Index

The agent reports its token usage to the [AI Worth Using Agent
Index](https://aiworthusing.com/agent-index). Three things put it on the
leaderboard, and all three are required:

**1. MIT licensed.** See [LICENSE](LICENSE).

**2. Registered.** Once, from the host, with the metadata that becomes the
agent's public page:

```sh
curl -O https://raw.githubusercontent.com/plow-pbc/agent-index-client/main/standalone/agent_index_client.py
set -a; . ./plow-credentials; set +a
python3 agent_index_client.py --register \
  --agent hermes-daily-tech-brief \
  --name "Hermes Daily Tech Brief" \
  --blurb "A daily, source-backed briefing on the tech and AI news that touches your stack." \
  --repo https://github.com/caiovisuals/hermes-daily-tech-brief \
  --runtime hermes \
  --install-url https://github.com/caiovisuals/hermes-daily-tech-brief#install
```

Then open the agent's page on the Index and click **Verify my agent**. That
step is a human one and cannot be scripted.

The id registered here must be the `AGENT_ID` in `compose.yml`. Registering one
id and shipping another fails silently: the reporter runs happily every hour,
into a page nobody owns. `tests/test_agent_index_service.py` pins the two
together.

**3. Reporting.** Already in the image -- the `agent-index` s6 service
(`image/s6-overlay/`) runs the pinned client hourly. It registers itself on
first run if needed, and stands down rather than guessing when `AGENT_ID` is
unset. There is no switch: an owner who does not want their usage reported
builds an image without the service.

The client itself is fetched at build time from the commit `vendor/client.pin`
names and checked against the sha256 beside it, rather than tracked here --
`plow-pbc/agent-index-client` owns that file.

## Configuration

You can configure your briefing according to your needs.<br/>
Example:
```bash
language: en-US
owner: Caio Oliveira
```

## Development

This project is built as a Hermes skill/agent and is designed to work with Hermes' existing tools and capabilities rather than implementing a separate AI system.<br/>
The project may introduce custom scripts or integrations when deterministic processing or external services are required.

## Tests

No framework, so they run anywhere the skills run:

```sh
python3 tests/test_filtering.py          # deduplication and stack matching
python3 tests/test_schedule.py           # the cron spec's dangerous parts
python3 tests/test_agent_index_service.py # the reporter, run in a sandbox
```

`test_agent_index_service.py` starts the real `run` script against a fake
container environment and a stub client, because a test that greps for a string
passes on a service that would not boot.

## Hackathon

Built for the AI Worth Using × Plow Hermes Hackathon.<br/>
The project uses the required AI Worth Using client for usage reporting and integrates with an open-source Plow tool.

## License

MIT — see [LICENSE](LICENSE).