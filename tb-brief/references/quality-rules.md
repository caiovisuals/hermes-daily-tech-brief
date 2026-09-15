# Editorial standard

## The one rule

Never invent anything. Not a headline, not a source, not a date, not a quote,
not a link, not a version number.

This is enforced, not merely requested: `format_brief.py` compares every URL in
the brief against the collected candidates and refuses to render a brief with a
link it cannot account for. `--allow-unverified` exists for the case where a
reader adds a story by hand. It is not a way past a rejection.

## Facts and claims are different things

State what happened, then state what it means, and never blur them.

- A company announcing a product is a fact. The product being good is a claim.
- A benchmark published by the vendor being benchmarked is a claim. Attribute
  it: "OpenAI reports", not "GPT-5.5 achieves".
- A funding round reported by one outlet with no confirmation is unconfirmed.
  Say so in the summary rather than dropping the qualifier.
- An analyst estimate is an estimate. Name whose.

## Read the source

The feed summary is a lead. Open the page before writing about it. Headlines
are written to be clicked and regularly overstate what the article supports.

If a page is paywalled or unreachable, either drop the story or say plainly
that you could not read past the headline.

## Why it matters

The hardest line to write and the reason the brief exists.

- It must name a consequence: something the reader may need to do, decide,
  postpone, or watch.
- It must be specific to this reader. "Important for developers" is filler.
  "Your Django services on 4.2 lose security support in January" is a reason.
- If no honest consequence exists, cut the story. A brief is not an obligation
  to fill sections.

## Repetition

`filter_news.py` removes stories already delivered, by URL and by identity.
What it cannot catch is the same news in new clothes: a rewrite, a follow-up
framed as fresh, a roundup of things the reader already saw.

When a story genuinely develops, `continuity` will be set. Lead with what
changed. Do not re-summarise what the reader already read.

## Length and restraint

- Summary: two or three sentences. Enough to act on without opening the link.
- Why it matters: one or two sentences.
- Three real stories is a good day. Eight padded ones is a bad one.
- Cut the story you are unsure about. The reader's trust is worth more than
  coverage.

## Tone

Plain declarative sentences. No hype, no breathless framing, no "game changing". 
If something is genuinely a big deal, the facts carry it.

Write in the language set by `language` in `config.json`, including headings.
Keep product names, version numbers and technical terms in their original form.

## When things fail

- Some feeds unreachable: deliver the brief, note it at the end.
- Every feed unreachable: deliver nothing and say why. An empty brief is
  honest; a fabricated one is not.
- Nothing newsworthy in the window: say that. A quiet day is information.