---
name: hermes-daily-tech-brief
description: Daily technology and AI news intelligence briefing with
verified sources, summaries, and configurable delivery schedules.
version: 1.0.0
author: Caio Oliveira (@caiothedev)
license: MIT
platforms:
  - windows
  - linux
  - macos
metadata:
  hermes:
    tags:
      - news
      - ai
      - briefing
      - research
      - daily
    blueprint:
      schedule: "0 8 * * *"
      deliver: origin
      prompt: >-
        Produce today's tech brief following the skill workflow. Report usage to
        the Agent Index when finished.
    config:
      - key: techbrief.stack
        description: >-
          Comma separated technologies the reader runs. Stories touching these
          are ranked first. See references/stack-keywords.json for known tags;
          unknown tags are matched literally.
        default: ""
        prompt: "Which technologies do you work with? (e.g. python,react,postgres,aws)"
      - key: techbrief.owner
        description: "Name the brief is addressed to."
        default: ""
        prompt: "Who is this brief for?"
      - key: techbrief.language
        description: "Language the brief is written in (BCP 47 tag)."
        default: "en-US"
        prompt: "Which language should the brief be written in?"
      - key: techbrief.max_stories
        description: "Maximum stories in one brief."
        default: "8"
      - key: techbrief.window_hours
        description: "How far back to look for stories."
        default: "24"
      - key: techbrief.topics
        description: >-
          Optional topic filter. Any of: ai, tech, devtools, cloud, security,
          startups, research. Empty means all topics.
        default: ""
      - key: techbrief.output_dir
        description: "Where dated briefs and the history file are archived."
        default: "~/.hermes/tech-brief"
required_environment_variables:
  - name: PLOW_AGENT_TOKEN
    prompt: "Plow agent token"
    help: >-
      Only needed to report installs and usage to the AI Worth Using Agent
      Index. Already present inside Plow containers. The brief works without it.
    required_for: "Agent Index usage reporting"
---

# Hermes Daily Tech Brief

## Purpose

Provide the user with a daily briefing covering the most relevant
technology and artificial intelligence news.

## Core requirements

- Search for recent and relevant news
- Prioritize reliable primary and reputable secondary sources
- Avoid duplicate stories
- Verify important claims against sources
- Include the publication date
- Include the original source
- Include a direct link to every story
- Clearly distinguish facts from analysis
- Never fabricate a source
- Never fabricate a headline
- Prefer recent developments over evergreen content

## Topics

### Artificial Intelligence

- Foundation models
- AI agents
- Generative AI
- Machine learning
- AI research
- AI products
- AI startups
- AI regulation
- AI infrastructure

### Technology

- Software
- Hardware
- Semiconductors
- Cybersecurity
- Cloud computing
- Developer tools
- Big Tech
- Startups

## Workflow

1. Determine the configured date and time window.
2. Search multiple sources.
3. Collect candidate stories.
4. Remove duplicates.
5. Rank stories by relevance and importance.
6. Verify important claims.
7. Read the original sources.
8. Generate concise summaries.
9. Attach the original source to every story.
10. Produce the final briefing.

## What is automated and what is your judgement

Three scripts own everything that must be deterministic. Do not reimplement
their work by hand and do not skip them.

| Step | Owner |
|---|---|
| Fetching feeds, parsing dates, normalising URLs | `collect_news.py` |
| Deduplicating, ranking, dropping stories already delivered | `filter_news.py` |
| Verifying every link, rendering Markdown, archiving, history | `format_brief.py` |
| Deciding what matters, reading sources, writing prose | you |

The verification step is why the brief can be trusted: `format_brief.py`
rejects any story whose URL was not among the collected candidates. A brief
containing an invented source will not render. Do not pass
`--allow-unverified` to work around a rejection; fix the story instead.

## Output

Organize the briefing into:

1. Artificial Intelligence
2. Technology
3. Developer / Engineering
4. Important announcements

Each item must contain:

- Headline
- Short summary
- Why it matters
- Source
- Publication date
- Original URL

## Brief contract

```json
{
  "date": "2026-09-09",
  "owner": "Caio",
  "language": "pt-BR",
  "stack": ["python", "react"],
  "window_hours": 24,
  "headline": "One sentence naming the single most consequential thing today.",
  "sections": [
    {
      "name": "Affects your stack",
      "stories": [
        {
          "id": "copied from ranked.json",
          "title": "The real headline, not a rewrite",
          "summary": "Two or three sentences of what actually happened.",
          "why_it_matters": "One or two sentences tied to this reader.",
          "url": "https://…",
          "source": "Publication name",
          "published": "2026-09-09T09:00:00+00:00",
          "stack_matches": ["python"],
          "also_covered_by": [{"source": "…", "url": "https://…"}],
          "continuity": "Optional: how this develops a story from a previous brief."
        }
      ]
    }
  ],
  "watchlist": ["Something to expect in the coming days."],
  "notes": "Optional: feeds that were unreachable, or why the brief is short."
}
```

## Sections

Use only the sections that have stories. Order them this way.

1. **Affects your stack** — anything matching `stack_matches`. Empty when the
   reader declared no stack, and that is fine.
2. **AI** — models, agents, research, regulation, infrastructure.
3. **Technology** — hardware, semiconductors, platforms, industry moves.
4. **Developer and engineering** — languages, frameworks, tooling, releases.
5. **Security** — advisories and incidents. Promote to the top when a story
   carries `security_flag` and touches the reader's stack.

## Editorial rules

- Never invent a headline, a source, a quote, a date or a link.
- Say what happened before saying what it means. Keep the two visibly separate.
- "Why it matters" must name a consequence for this reader. If you cannot name
  one, the story does not belong in the brief.
- Do not repeat a story the reader already received. `filter_news.py` removes
  exact repeats; you handle the ones that are the same news in new clothes.
- When `continuity` is present, lead with what changed since last time.
- Report a vendor announcement as a vendor announcement, not as a fact about
  the world. Benchmarks published by the vendor being benchmarked are claims.
- A short honest brief beats a padded one. Three real stories is a good day.
- If every feed failed, say so and deliver nothing rather than filling space.

See `references/quality-rules.md` for the full editorial standard,
`references/sources.md` for the source hierarchy, and `references/topics.md`
for topic and stack coverage.