# Output template

`format_brief.py` is the renderer and the source of truth for the layout. This
file records the shape it produces, so you can see the target before writing
`brief.json`. Do not assemble a brief by editing this file by hand.

```markdown
# Daily Tech Brief — YYYY-MM-DD

*For {owner} · Stack: {stack} · Window: last {N}h*

**{headline}**

## {section name}

### {story title}

{summary: two or three sentences of what happened}

**Why it matters.** {one or two sentences of consequence for this reader}

*Follow-up: {only when this develops an earlier story}*

Touches: `{stack tag}`, `{stack tag}`

Source: [{publication}]({url}) · {publication date}
Also covered by: [{publication}]({url})

## Watchlist

- {something to expect}

---

*{closing note: unreachable feeds, or why the brief is short}*
```

## Which parts appear

| Element | Appears when |
|---|---|
| The `For … Stack: …` line | `owner`, `stack` or `window_hours` is set |
| `**{headline}**` | `headline` is set |
| A section | it has at least one story |
| `*Follow-up: …*` | the story has `continuity` |
| `Touches: …` | the story has `stack_matches` |
| `· {date}` | the story has `published` |
| `Also covered by` | the story has `also_covered_by` |
| `## Watchlist` | `watchlist` is non-empty |
| The closing note | `notes` is set |

`title`, `summary`, `why_it_matters`, `url` and `source` are required on every
story. A brief missing any of them is rejected rather than rendered with a gap.

## Where it lands

- `/var/lib/hermes/tb/YYYY-MM-DD.md` — the brief
- `/var/lib/hermes/tb/index.md` — archive listing, newest first
- `/var/lib/hermes/tb/history.json` — delivered stories, so tomorrow's run
  skips them and can recognise follow-ups

See `examples/example-brief.md` for a rendered brief and
`examples/example-brief.json` for the input that produced it.