# Section writer prompt (filings-analyst, model opus)

Write sections {SECTION_NUMBERS} of the filings research report on {COMPANY} ({TICKER}), as of {AS_OF}.
Read: `{SK}/references/report_outline.md` (your sections and the writing rules), `{SK}/references/framework.md`
Part 2 (the lenses), `{WORK}/drivers.md` and `{WORK}/pm_review.md`, `{WORK}/drivers_math.md`, `{WORK}/coverage_key.md`,
`{WORK}/conflicts.md`, `{WORK}/guidance_track.csv`, the digests {NOTES_PATHS}, the figure list
`{WORK}/figures.md` (file, caption), and the user's notes and questions: {NOTES_OR_NONE}.
If you are writing section 01, first read every other file in `{PHASE}/sections/`.
Write each section to `{PHASE}/sections/` under the file name the outline's table gives it.
Use the figures that fit, as `<figure><img src="fig/<file>"><figcaption>caption</figcaption></figure>`.
Rules:
- **Length and focus:** stay within your sections' word targets in the outline; citations don't
  count. Write each fact only in its home section (the outline's topic table); elsewhere one sentence and "(see
  §N.N)". Open each section with its `> [!KEY]`; at most one `> [!MODEL]` and one `> [!WATCH]` per section. Cut
  any paragraph that doesn't help the user understand the industry, the company, or the key drivers and how to model
  them. A script flags paragraphs that repeat another section, and they come back to you.
- Each section file starts with `## NN Title` (two #), sub-sections `### N.N Title`; the contents page is built
  from them. Equations are plain text or bold text (`**Revenue per customer = revenue ÷ average customers**`), never
  LaTeX (`$$`, `\frac`): the PDF prints LaTeX as raw code.
- Every number is cited: documents as [<file label>, <locator>]; model numbers by the cell in the `source` column
  of `{WORK}/series.csv` (Grep the metric name), e.g. `[Model, MOD!H61]`, several cells in one bracket split by ';',
  e.g. `[Model, MOD!H61; Model, MOD!N61]`; the user's notes as [User's notes, <where>].
- `[Calc, drivers_math <section>]` is ONLY for numbers that appear in `{WORK}/drivers_math.md`. Do no arithmetic of
  your own. If you need a number that isn't there, list it in your reply (what it is and its inputs) and leave
  `(needs calc: <what>)` in the text; the main agent will add it.
- KPI tiles carry their citation inside the label: `<div class="l">FY2025 revenue [Model, MOD!BH61]</div>`.
- Keep citations inline in brackets with their full text; the PDF turns them into per-section footnotes and colours
  them by the first word (`Calc`, `Model`, `price.csv` = orange, everything else blue), so keep those prefixes exact.
- Numbers in tables get a source line under the table.
- Quotation marks only for wording copied exactly from a digest or note where the reader marked it as a quote. Never put a paraphrase or a reader's inference in quotation marks; numcheck checks every quote of 4+ words against its cited source.
- The user's model can hold rows they typed in from outside sources (e.g. "Number of ppl with diabetes (CDC)", "IDF").
  They are the user's own model inputs, not company documents: if you use one, label it "user's model input (outside
  source)", never treat it as company evidence, and list it in your reply.
- Contradictions between sources are explained, not resolved silently; no outside knowledge; if the documents
  don't answer something, say so and add it to the Gaps section's list in your reply.
Reply with the file paths, any gaps, any calcs needed and any outside-source model rows used, in 150 words or less.

The digests are long (8 files, ~125,000 words). Read each digest's `## Key findings` in full, then Grep the digests for your sections' topics and read only those parts. drivers.md is required reading in full.
