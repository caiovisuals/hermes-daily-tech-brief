# Topics and stack coverage

## Topics

A topic is a coarse filter over feeds, set by `topics` in `config.json`. Leave it
empty to search everything.

| Topic | Covers |
|---|---|
| `ai` | Foundation models, agents, generative AI, ML research, AI products, AI regulation, AI infrastructure |
| `tech` | Big Tech, consumer platforms, hardware, semiconductors, industry moves |
| `devtools` | Languages, runtimes, frameworks, databases, build and deploy tooling |
| `cloud` | AWS, Google Cloud, Azure, Cloudflare, Kubernetes, containers |
| `security` | Advisories, exploited vulnerabilities, breaches, supply chain |
| `startups` | Funding, launches, acquisitions, shutdowns |
| `research` | Papers and preprints |

## Stack tags

A stack tag is what makes the brief specific to one reader.
It is set by `stack` in `config.json`, and resolved through `references/stack-keywords.json` into the terms that signal a story touches it.

Declaring `python` matches headlines about CPython, PyPI, Django, FastAPI and
Pydantic, not only ones containing the word "python".

An unmapped tag still works. It is matched as a literal term on word
boundaries, so `elixir` finds Elixir stories without any mapping. Adding a
mapping makes it better, not possible.

### Groups currently mapped

**Languages and runtimes** — python, javascript, typescript, node, deno, bun,
go, rust, java, ruby, php, swift, csharp

**Frontend** — react, nextjs, vue, svelte

**Data** — postgres, mysql, sqlite, mongodb, redis, clickhouse, kafka

**Cloud and infrastructure** — aws, gcp, azure, cloudflare, vercel, kubernetes,
docker, terraform

**Development workflow** — github, gitlab, git, ci

**AI** — openai, anthropic, claude, gemini, llama, mistral, huggingface,
pytorch, langchain, llm, agents, rag

**Platforms** — nvidia, apple, linux, security

### Adding a mapping

Add to the `stack` object in `references/stack-keywords.json`:

```json
"elixir": ["elixir", "phoenix framework", "erlang", "beam vm", "hex.pm"]
```

Terms match case-insensitively. A term is anchored at whichever of its ends is
alphanumeric, so `react` does not fire on "reactor", while `go 1.`, `gpt-` and
`cve-` still match the version or identifier that follows them. A term ending
in a letter is a whole word and not a prefix: write `fine-tuning`, not
`fine-tun`.

Keep them specific: a term like `go` alone would match "going", which is why
the mapping uses `golang` and `go 1.` instead. Test a mapping before trusting
it:

```bash
python3 tests/test_filtering.py
```

## How ranking uses all of this

`filter_news.py` scores each deduplicated story:

- source tier, primary sources weighted highest
- one bonus per distinct stack tag matched in the headline or summary, capped
- a bonus when the feed itself is authoritative for a declared tag
- a bonus per additional outlet corroborating the story, capped
- a large bonus when a security story touches the declared stack
- recency, decaying over the window
- a bonus when the story follows up something already delivered

The score orders a shortlist. It does not pick the brief. That is the agent's
job, and a high score is only a reason to look closely.