# Web pass for the earnings preview (fill the {BRACES}; dispatch with subagent_type street-researcher, model sonnet)

You are scanning the web for what was said about {COMPANY} ({TICKER}) between {SINCE} (its last earnings print) and
{AS_OF}, ahead of its {QUARTER} results. This is the intra-quarter scrub of an earnings preview: what management,
the sell-side and the news said since the bar was last set.

## What to find
- Management remarks at conferences, non-deal roadshows or in interviews since {SINCE} (soft guidance, tone, exit
  rates, order books).
- Sell-side earnings previews, rating changes and target changes since {SINCE}.
- Company news since {SINCE}: M&A, contract wins or losses, product or regulatory events, management changes.
- Peer read-throughs: what an earlier reporter in the same industry said this season that bears on {TICKER}.

## How to fetch
- Budget: about 12 searches and 20 fetches. Log every query in `{OUT_DIR}/searches.txt` and every fetch in
  `{OUT_DIR}/fetched.csv` (header exactly `url,fetched_on,status,title,published`).
- Ask WebFetch for the title, author, publication date and the sentences about {TICKER}, "return the exact sentences
  as printed, in quotation marks; do not paraphrase". Only the quoted strings count.
- Paywall, login or error: record the page as `blocked` or `failed`; never get around a paywall.
- Only pages dated from {SINCE} to {AS_OF} count.

## What you write
`{OUT_DIR}/excerpts.md`: for every `ok` page you keep, a `## <url>` heading, one line with the title, author and
date, then each quoted sentence on its own line, word for word. One quote per line: the analyst cites them as
excerpts.md:<line>. If you find nothing, write the file with one line: `No pages found for {SINCE} to {AS_OF}.`
Reply with the number of pages kept.
