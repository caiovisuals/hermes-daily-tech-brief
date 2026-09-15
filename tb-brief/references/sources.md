# Source hierarchy

Every feed in `feeds.json` carries a tier. The tier is a claim about who is in
a position to know, not about who writes well.

## Tier 1 — primary

The organisation publishing about itself, or an authority publishing a record:
a vendor release note, a project blog, a government advisory. Nothing sits
between the fact and you.

Use tier 1 as the link whenever it exists. When `also_covered_by` shows both a
vendor post and a newsroom write-up of it, link the vendor and mention the
coverage.

Tier 1 has one weakness and it is severe: the publisher is never neutral about
itself. A release note tells you what shipped, which is fact. A launch post
tells you it is revolutionary, which is marketing. Carry the first into the
brief and leave the second behind.

## Tier 2 — editorial

Newsrooms with an accountable editor: Ars Technica, The Verge, TechCrunch, The
Register, InfoQ, MIT Technology Review, and the security desks at Krebs on
Security and BleepingComputer.

They add reporting a vendor will not do: what broke, who is affected, what the
company declined to say. Prefer them for anything contested, anything about a
company's conduct, and anything where the primary source has an obvious
interest in the framing.

## Tier 3 — community and analysis

Hacker News, Simon Willison, Latent Space, Import AI.

Excellent at surfacing what matters before anyone else notices, and at
explaining why practitioners care. Not a source of record. A tier 3 item may
set the agenda for a story, but the link in the brief should be the thing it
points at, not the discussion about it.

## Corroboration

`filter_news.py` records every outlet that carried a story in `corroboration`.
More outlets means the event happened; it does not mean the interpretation is
right. Twenty outlets rewriting one press release is one source, not twenty.

Treat a single tier 3 report of a major claim as unconfirmed and say so.

## Adding a feed

Add an entry to `tb-brief/references/feeds.json`:

```json
{ "id": "short-slug", "name": "Display Name", "url": "https://…/feed.xml",
  "tier": 1, "topics": ["devtools"], "stack": ["rust"] }
```

`topics` filters the run. `stack` marks the feed as authoritative for those
stack tags, which gives its stories a ranking bonus for readers who declared
them. Then check it works:

```bash
python3 tb-brief/scripts/collect_news.py --check-feeds --only short-slug
```

A feed that fails the check is reported and skipped on every run; it never
breaks the brief.