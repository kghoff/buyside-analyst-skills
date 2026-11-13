# Reader prompt (fill the {BRACES}; dispatch with subagent_type filings-analyst, model sonnet)

You are reading part of the company record for {COMPANY} ({TICKER}), as of {AS_OF}. This is the filings research:
company documents only. Your slice: **{SLICE_TITLE}**.

## Read every one of these files, start to finish
{FILES}
(one line per file: `<label>` → `<absolute path to read>`. A PDF path means there is no markdown copy; read the PDF.)

The markdown files are filtered copies. A line `*[N paragraphs unchanged since <earlier filing>]*` stands for text
you don't need to read again; another reader covered it. `*[changed since <filing>]*` marks a paragraph that was
reworded: `~~[- old words -]~~` were removed and `**[+ new words +]**` were added. Changes like these (a new risk, a
revised policy, new wording on guidance) are often the most important thing in a filing. Tables are always complete.

## What to look for
Read `{SK}/references/framework.md` Part 1 (and "The goal") before you start. Hunt for every item there.
The user's notes and questions: {NOTES_OR_NONE}

## What you write, in {OUT_DIR}
1. `notes.md`, 4,000–7,000 words, with these headings in this order:
   - `## Key findings` (10–15 bullets a PM would care about)
   - one `##` per framework Part 1 heading that your files speak to (findings, with numbers)
   - `## Timeline` (table: date | event | source)
   - `## Promises vs delivery` (what management said it would do, and what later happened, both cited)
   - `## Quotes` (up to 15 short quotes, each cited)
   - `## Screenshot ideas` (deck / event slides worth showing: file label, slide number, why)
   - `## Answers to the user's questions` (only if questions were given; number them to match)
   - `## Not found in these documents` (checklist items and questions your files are silent on)
2. `data.csv`, header exactly `metric,period,value,unit,source`. Only numbers NOT already in the user's model
   (see `{MODEL_ROWS}`): segment, geographic, channel or product revenue, units, users, installed base, prices,
   capacity, headcount, TAM figures the company states. `period` must be `Q3 2024`, `H1 2024`, `FY2024` or
   `2024-09-30`. `value` is a plain number (no $, %, commas): write percentages as 12.5 with unit `%`, money in
   the unit the document uses (`$M`). `source` is `<file label>, <locator>`; several sources go the same way as
   in citations (`label A, Item 7; label B, S12`). Quote the whole field. **Only numbers the document states,
   exactly as stated.** Never derive, infer or compute a value for data.csv (no backing out dollars from growth
   rates, no FX amounts from reported vs organic). If you work something out in notes.md, write "(my arithmetic:
   …)" with the inputs, and keep it out of data.csv. If a line you need is hidden behind an "unchanged since"
   marker, say so in "Not found in these documents"; don't guess its content.
3. `guidance.csv`, header exactly `fiscal_year,metric,basis,kind,date,low,high,actual,source`. One row for every
   guide and every revision you find (date = the document's date), and one row when the actual is reported
   (low/high empty, actual filled). `kind` = `hard` (press release / 8-K) or `soft` (call, deck, event). `basis` =
   `reported`, `organic`, `constant currency`, `non-GAAP`... A change of basis is a new basis value; never mix them.
   Same rule as data.csv: `low`, `high` and `actual` are only numbers a document states. Leave `actual` empty if
   no document in your slice states it; the merge step fills actuals from the model.
4. `files_read.txt`, the label of every file you read, one per line, exactly as given above.

## Rules
- Cite every fact `[<exact file label>, <locator>]`: locator = section / Item / slide `S41` / page / speaker.
  Several sources: `[label A, Item 7; label B, S12]`. Only cite files in your slice.
- Square brackets are only for citations. Use parentheses for anything else, e.g. "(in $M, unaudited)". Never
  write shorthand in brackets ("[same sources]", "[ibid]", "[each filing]"): repeat the full citation every time.
- Inside a locator, don't put a ';' followed by another comma: write `Item 7 / Note 3`, not `Item 7; Note 3, p. 4`.
- `notes.md` must have at least 1,000 words and 10 citations or the read check fails it. That is the floor; the
  target is 4,000–7,000 words.
- Investor days, long-range plans and strategy decks are the densest documents: capture every target, bridge, ramp, market-by-market figure, coverage or launch calendar and new product on every slide, each with its slide number.
- Never invent a number. If the documents don't say, say "not in the company documents"; that is a finding.
- Plain English; define acronyms on first use.
- Reply only with the output folder path and a summary of 150 words or less.
