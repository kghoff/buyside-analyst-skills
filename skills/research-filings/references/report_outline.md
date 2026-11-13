# Filings research report outline

File: `<YYYY-MM-DD> <TICKER> Filings Research Report`. Sections are written to `sections/NN-name.md` and joined.

## 00 Cover (main agent)
<div class="cover"><div class="band"><h1>{COMPANY} ({TICKER})</h1><div class="sub">Filings research: the
company's own record, as of {AS_OF}</div></div><div class="meta">Sources: {N} company documents (10-Ks, 10-Qs,
calls, press releases, decks, investor events, proxies). No sell-side research, investor letters or web sources were
used. Prepared {DATE}.</div></div>

## The shape of the report
About 20,000 words of reading text (citations, cover, summary and appendix not counted; repeat_check.py counts
17,000-23,000 as on target). The job is three things only: get the user up to speed on the industry, on the company, and
on the three key drivers and how to model them. A paragraph that serves none of them is cut, however true.

**Each fact has one home.** It is written in full in its home section only. Anywhere else it gets at most one
sentence and "(see §N.N)". repeat_check.py flags paragraphs that repeat another section.

| Topic | Home |
|---|---|
| Market, regulation, who pays, competitors, industry map | 02 |
| Eras and key decisions, products and launches, the business today (three lenses, five core drivers) | 02 |
| Revenue splits, seasonality, 2-year stack, price vs volume | 03 |
| Profit bridge, fixed vs variable costs, incremental margins, unit economics, sensitivity | 03 |
| FCF bridge and conversion, ROIC, capital deployment | 03 |
| Guidance vs actual, long-range plans, launch promises vs delivery, incentives, contradictions | 04 |
| Each key driver: mechanics, math, bull vs bear debate, what to watch; rejected drivers; PM challenges | 05 |
| Forecast build, the rows that matter, rows to add to the model | 06 |
| Yearly returns vs the market and eras, big moves, which driver moved the stock | 07 |
| Questions the documents can't answer | 08 |

**Signal over coverage.** Each section opens with `> [!KEY]` (its bottom line in 2-3 sentences), then the evidence.
Each section has at most one `> [!MODEL]` and one `> [!WATCH]`; the summary collects them. Prefer one table or chart
to three paragraphs. Each figure appears once, in its topic's home.

**The model gets the same material.** Sections 03, 04 and 07 are also written into the user's model (Filings Charts
and Idio Chart tabs) by step 8; keep their content complete here too (the user reads both).

| File | Section | Words |
|---|---|---|
| 01-summary.md | Summary (written last) | 1,200 |
| 02-industry-and-company.md | The industry and the company | 3,200 |
| 03-economics.md | Revenue, profit and cash | 4,000 |
| 04-management.md | Management credibility | 2,000 |
| 05-key-drivers.md | The key drivers | 4,500 |
| 06-forecast.md | Recommended forecast structure | 2,300 |
| 07-stock.md | The stock vs the drivers | 2,000 |
| 08-gaps.md | Gaps for the street research | 800 |
| 09-appendix.md | Appendix | not counted |

## 01 Summary (written last)
KPI tiles (4–8), each with its citation inside the label:
`<div class="kpis"><div class="kpi"><div class="v">$4.7B</div><div class="l">FY2025 revenue [Model, MOD!BH61]</div></div>…</div>`,
then <div class="drivers"> with the key drivers, one line each </div>, the forecast structure in two sentences, then
the 10 points a PM would care about (one or two lines each, each pointing to its section), then "What to watch":
the WATCH items from the sections, one line each.
## 02 The industry and the company
### How the market works (what it is, who pays, regulation, how it got here) · ### Competitors and the industry map
(winners vs losers, as the company describes them) · ### The company in eras (a table: era, years, key decisions and
management's stated reasons, what it did to the numbers; then short text) · ### Products (one table of generations
and launches) · ### The business today (three-lens scorecard, five core drivers, current vs future state). Say where the
company's documents run out.
## 03 Revenue, profit and cash
### Revenue anatomy (each disclosed split as % of revenue and % of growth, seasonality, 2-year stack) · ### Price vs
volume · ### Profit bridge · ### Fixed vs variable costs and incremental margins · ### Unit economics and sensitivity
(pull one driver) · ### Cash and capital (FCF bridge and conversion, ROIC from the model, capital deployment).
## 04 Management credibility
### Guidance vs actual (scorecard table: per year and metric, first guide, each revision, actual, beat / miss vs the
first midpoint; basis changes) · ### Long-range plans · ### Promises vs delivery (launches, operations) · ### What
management is paid to hit · ### Contradictions in the record (explained, not resolved).
## 05 The key drivers
One `### Driver N: <name>` per driver: what it is and why it moves value, the math (from drivers_math), the debate
(bull and bear, from the company's own disclosures), what to watch and how to model it. Then ### Considered and
rejected, ### The PM review's challenges and the answers.
## 06 Recommended forecast structure
The build is the key drivers, with every judgment input named as the user's assumption and its bounds; other builds are
cross-checks. A revenue growth-rate engine only when the drivers cannot be modelled, said plainly.
### The build (with the diagram) · ### The three checks · ### Cost lines and below the line · ### The rows that matter
(coverage matrix, rows that matter only) · ### Rows to add or change in the user's model.
## 07 The stock vs the drivers
### Yearly returns vs the market (table: year, company, SPY, difference; then the eras beside the years) · ### The big
moves around company events (table; first column `<label> (YYYY-MM-DD)`, a `**bold**` label for the biggest moves;
then one-day moves) · ### Big moves with no company event (bullets `- **<period>.** text`, dates as YYYY-MM-DD) ·
### Which driver moved the stock (table: period, driver, evidence) · takeaways. The street research parses these two formats.
## 08 Gaps for the street research
### A. Questions the company documents could not answer: numbered `N. **Title.** text`, grouped under `**<group>**`
lines (one group per driver, then other). ### B. Framework Part 4 methods relevant to this company. The street research
parses part A's format.
## 09 Appendix
Judgment calls, conflicts between sources, unconfirmed numbers. No data tables and no full coverage matrix (the
model and `_work/coverage.md` hold them).
## The user's questions (no section of their own)
Only if the user gave any: answer each in its home section in a `> [!Q]` callout with the question's number, and list them
in the summary.

## Writing rules (all sections)
- Plain English with academic rigor: explain each finance idea from first principles. Show equations.
- Define every acronym on first use.
- Callouts: `> [!KEY]` takeaway, `> [!MODEL]` modeling implication, `> [!WATCH]` watch item, `> [!Q]` answers
  one of the user's questions.
- Cite every number: [<file label>, <locator>] for documents; model numbers by cell from series.csv's `source`
  column, e.g. [Model, MOD!H61], several cells as [Model, MOD!H61; Model, MOD!N61]; [Calc, drivers_math <section>]
  ONLY for numbers in drivers_math. Writers do no arithmetic of their own.
- Square brackets are only for citations and callout tags; use parentheses for anything else.
- Write citations inline in brackets exactly as above, with the full text (never shortened). The PDF prints each
  bracket as a numbered footnote at the foot of the page, numbered per section, blue for company documents and
  orange for our own work; the colour comes from the first word, so keep the `Calc`, `Model` and `price.csv`
  prefixes exactly. `[unconfirmed]` prints as a yellow flag, not a footnote.
- Rows the user typed into their model from outside sources (e.g. CDC, IDF) are labeled "user's model input (outside
  source)" and are never company evidence.
- "Not in the company documents" is a finding; say it and add it to section 08.
- Contradictions between sources: explain both, don't pick silently.
