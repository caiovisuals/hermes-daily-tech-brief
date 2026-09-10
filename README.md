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

## Installation

Install the Hermes agent first by following the official Hermes installation instructions.<br/>
Then install Hermes Tech Brief through the AI Worth Using Agent Index.<br/>
After installation, configure the agent according to your preferences.

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