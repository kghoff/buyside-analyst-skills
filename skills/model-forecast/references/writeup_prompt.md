# Forecast write-up for {TICKER} ({COMPANY})

The forecast is built into the user's model. The user opens MOD, sees many new rows and needs to know why each is there. Write
them a guide to the forecast: what each section does, how its rows work together, where the key numbers come from,
and which assumptions carry the result. The user is the portfolio manager, so write plain
English, with concrete numbers and MOD row numbers, and no jargon about the scripts or the plan file. You write ONE
file, `{MODEL_WORK}/forecast_writeup.md`. You do not edit the plan or the model. No shell, no web.

## Read
- `{MODEL_WORK}/forecast_plan.json`: every row, its method, its typed values and its `source` text (your reasoning
  is there; if you wrote this plan, also use what you remember)
- `{MODEL_WORK}/rowmap_after.md`: the final MOD layout. Cite rows by these numbers, never by the plan's
  pre-build numbers.
- `{MODEL_WORK}/forecast_headlines.md`, `{MODEL_WORK}/coverage.json`, `{MODEL_WORK}/check_report.json`
- The user's notes: {USER_NOTES_OR_NONE}
- The filings research key drivers and forecast structure (`{P1_SECTIONS}/*key-drivers*.md`, `{P1_SECTIONS}/*forecast*.md`), and
  the street research's what-changes section if given: {P2_SECTIONS_OR_NONE}. Use them only to say where a choice came from.

## Write (2,500-4,500 words: the intuition and the row names take room; cut repetition, not them; Markdown, `##` for sections, `###` for sub-sections; the PDF builds its contents page from them)
Start with `# {TICKER} forecast: how it is built` and one line with today's date.

1. `## The forecast in one page`: how the model flows, in 5-8 short lines from the key drivers to revenue to margins
   to cash to the share count to EPS, with the MOD rows where each step happens. Then the headline numbers (revenue,
   margins, EPS, FCF in the first and last forecast years) and where they sit against guidance.
2. One `##` per MOD section the forecast added or fills, in the order they appear in MOD (the revenue build, each
   driver section, then the statements). For each one:
   - **The intuition first:** in two to four plain sentences, the business logic before any math: what real-world
     thing this block models and why it moves the numbers (e.g. "longer-wearing sensors mean fewer sensors shipped
     per customer, so cost per customer falls even if each sensor costs the same"). A reader who skips the rest of
     the section should still understand why the block exists.
   - **How it works:** walk the block group by group, in the order the rows sit in MOD: which rows are inputs (blue),
     which are formulas, and what each formula means in words, not just which rows it multiplies ("Average customers
     (row 136) x Revenue per average customer (row 137) = Revenue (row 131): more customers or more revenue from each
     one both lift revenue").
   - **Key numbers and why:** each typed input that matters: its first- and last-year value, where it came from
     (filings research section, filing, guidance, the user's note) and why that value and not another.
   - **Judgment calls:** what is an estimate rather than a reported fact, and what would change your mind.
   Treat the statements and their analysis blocks briefly, as `###` sub-sections under ONE `## The statements and
   analysis (all formulas)` (every `##` starts a new PDF page): say only which driver rows feed them and anything
   unusual.
3. `## Key assumptions`: one table of the 8-15 assumptions that move value most: assumption, MOD row, first-year
   and last-year value, source, and how firm it is (reported / guided / estimated / judgment).
4. `## What the checks prove`: in a few lines: revenue traces to the drivers, the balance sheet balances, cash ties,
   guidance hit or deliberately missed (and why), and any research recommendation left out on purpose
   (`coverage.json` items marked explained).
5. `## Where the model could be simpler`: The user finds some sections too detailed. List the rows or blocks that could
   be merged or removed without losing a key driver or a filings research recommendation, what each currently adds, and what
   would be lost. Recommend only; change nothing.

Rules: every time you cite a row, give its name AND its number, the name exactly as column B shows it in
`rowmap_after.md` ("Share of cost of sales that scales with sensor count (row 143)"), never a bare "row 143"; a range
names its group ("the Ireland start-up drag rows (164-167)"). Every number you quote must be in the plan, the headlines or the model's row map; don't invent figures. Say
"estimate" or "judgment" where it is one. No company-specific facts that the files don't contain.

## Reply
Reply with the path and the three assumptions you think the user should look at first, one line each.
