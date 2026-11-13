# Checker prompt (fill the {BRACES}; dispatch with subagent_type street-analyst, model sonnet)

You are checking sections {SECTION_FILES} of the street research report on {COMPANY} ({TICKER}). The scripts flagged the
items in `{NUMCHECK_FILES}` and `{WORK}/repeat.md`.

Where to find each source:
- **sell-side:** `{SRC}/<md>`, the report's `md` path in `{WORK}/run.json` `sellside` (inside its tier folder,
  e.g. `Sellside Research/1 Broker Research/_md/<label>.md`)
- **web:** the text under `## <url>` in `{WORK}/research/*/excerpts.md`
- **The filings research:** `{P1_REPORT}`
- **company documents:** find the label in `{P1_WORK}/inventory.json`. Its `md` path is relative to `{SRC}`.

For each flagged item, in the section file itself:
- **Unconfirmed or weak number:** find it in the cited source, and for sell-side, confirm it is on the cited page. If the source says it differently, fix the number or
  the citation. If no source supports it, remove the claim or rewrite it without the number.
- **Uncited number:** add the right citation, or remove the number.
- **Bad citation:** fix it to an exact sell-side label, a URL with an excerpt, `Filings research, §x`, or a company label.
- **Quote not found:** replace it with the exact words, or paraphrase without quotation marks.
- **Dated after the as-of date:** remove it, or label it "(after the as-of date)" if it is essential.
- **Repeats the filings research:** cut it to one sentence plus "(see Filings research §x)".

Then read your sections once more for balance. Every key driver should show the bear case as well as the bull case,
or say plainly that none was found.

Never add a new claim. Reply only with a list of what you changed, and anything you couldn't resolve, in 150 words
or less.
