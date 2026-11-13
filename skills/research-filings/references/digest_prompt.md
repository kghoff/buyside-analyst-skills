# Digest prompt (fill the {BRACES}; dispatch with subagent_type filings-analyst, model sonnet)

You are condensing reader notes on {COMPANY} ({TICKER}), as of {AS_OF}, for the senior analyst and the report
writers, who can't read all ~40 reader notes. Your group: **{GROUP_TITLE}**.

Read every one of these notes files in full (each reader read one stretch of the company's documents):
{NOTES_LIST}

Write `{OUT}` (5,000–8,000 words) with these headings, in this order:
- `## Key findings`: the 15–20 most important points across the group, as a PM would rank them
- one `##` per framework Part 1 heading the notes cover (see `{SK}/references/framework.md`): merge what the
  readers found into one arc over time (how it started, what changed, when, and what the company said why)
- `## Timeline`: one merged table (date | event | source), sorted by date, duplicates removed
- `## Promises vs delivery`: merged and sorted by date
- `## Contradictions and changes`: where readers' sources disagree with each other, basis changes, restatements,
  wording that changed between documents
- `## Quotes`: the 12 best short quotes
- `## Screenshot ideas`: every slide or table idea the readers listed (file label, slide or page, why)
- `## Not found in these documents`: merged; drop an item if another reader in your group did find it

Rules:
- Keep every number and every citation exactly as the reader wrote it: `[<file label>, <locator>]`. Never add a
  fact, a number or a citation that isn't in the notes. Don't recompute anything; "(my arithmetic: …)" items stay
  marked as the reader's arithmetic.
- When you must shorten, cut repetition and connecting prose, never a number, a slide-level specific (targets, ramps, market-by-market figures, launch dates, new products) or a management explanation.
- When readers disagree, keep both with their citations.
- Square brackets are only for citations; use parentheses for anything else.
- Plain English; define acronyms on first use.
- Reply only with the output path and a summary of 120 words or less.
