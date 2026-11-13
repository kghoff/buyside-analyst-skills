# Street research report outline (target 15,000–25,000 words, appendix excluded)

Street research reports only where outside views differ from the filings research, add to it, or close its gaps. Anything the filings research
already says is referenced as "(see Filings research §x)", never retold.

| File | Section | Words | Writer group |
|---|---|---|---|
| 00-cover.md | Cover (main agent, template below) | – | main |
| 01-executive-summary.md | Executive summary: bottom line + scorecard | 1,500 | last |
| 02-where-outsiders-agree.md | Where outsiders agree (one table + 1–2 paragraphs) | 800 | A |
| 03-drivers-from-outside.md | The key drivers, seen from outside (one ### per driver; drivers outsiders weight that the filings research didn't) | 5,000 | A |
| 04-industry-direction.md | Industry direction: competition, pricing, payers, new entrants | 2,500 | A |
| 05-growth-plan.md | The growth plan: do outsiders believe the LRP and guidance; which parts they discount | 2,500 | B |
| 06-turning-points.md | Turning points: was the Street right before? + credibility read | 3,000 | B |
| 07-gaps-closed.md | Gaps closed: status table for every filings research gap + detail for the ones that matter | 3,000 | B |
| 08-what-changes.md | What changes in our view: drivers, forecast structure, watch items, /model-consensus handoff | 2,500 | C |
| 09-still-open.md | Still open, next steps: expert calls, channel checks, management questions; thin coverage, and blocked pages the user could drop in as PDFs | 1,000 | C |
| 10-appendix.md | Appendix (script: appendix.py) | – | script |

## Section 01 scorecard (required table)
| Topic | Company view (the filings research) | Outside view: bull | Outside view: bear | Verdict | Key sources |
Rows: each key driver, then each filings research debate. Verdict: agrees / differs / adds / no outside view.
Company view: the ledger id plus a paraphrase of 12 words or fewer (the filings research already has the full text). The same goes
for the Claim column of section 02's agreement table.

## Section 07 status table (required)
| # | Gap (Filings research §15) | Status | Answer | Tier | Source |
Status: closed with a fact / estimate only / still open. Every filings research gap appears.

## Citations
Write citations inline in brackets exactly as the writer prompt gives them, with the full text (never shortened). The
PDF prints each bracket as a numbered footnote at the foot of the page, numbered per section: purple for outside views
(sell-side reports, investor letters, web pages), blue for company documents and the filings research report, orange for our
own work. The colour comes from the first source, so keep the labels, URLs and the `Calc`, `Model` and `price.csv`
prefixes exactly. `[unconfirmed]` prints as a yellow flag, not a footnote. Square brackets are for citations only:
never put a page title or any other text in brackets.

## Callouts (as the filings research; render.py styles them)
`> [!KEY]` key takeaway · `> [!MODEL]` modeling implication · `> [!WATCH]` watch item · `> [!Q]` the user's question

## Cover template (00-cover.md, one line)
<div class="cover"><div class="band"><h1>{COMPANY} ({TICKER})</h1><div class="sub">Street research: outside views against the company's own record, as of {AS_OF}</div></div><div class="meta">Sources: {N_SELLSIDE} sell-side reports and {N_WEB} web pages, scored against {N_LEDGER} company claims from the filings research report ({P1_DATE}). Only differences, additions and closed gaps are reported. Prepared {DATE}.</div></div>
