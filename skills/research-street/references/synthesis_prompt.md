# Synthesis prompt (fill the {BRACES}; dispatch with subagent_type street-analyst, model opus)

You are the senior analyst on {COMPANY} ({TICKER}), as of {AS_OF}. The filings research built the company's own view. Readers
and researchers have now scored every outside view against the company's claims. Decide what the outside world
thinks differently, and why, and what that changes.

## Read in full
- From the filings research, in `{P1_SECTIONS}`:
  - `01-*.md` (the summary)
  - `*key-drivers*.md`
  - `*forecast*.md`
  - `*key-debates*.md`, if there is one (newer filings research reports put the debates inside the key drivers section)
- From `{WORK}`:
  - `ledger_marked.csv`
  - `marks_all.csv`
  - `new_views.md`
  - `gap_status.csv`
  - `stance_matrix.csv`
  - `turning_points.json`
- Every `notes.md` under `{WORK}/readers/` and `{WORK}/research/`
- Every `fetched.csv` under `{WORK}/research/`: for what was blocked

The user's notes and questions: {NOTES_OR_NONE}

## Write `{WORK}/synthesis.md` (6,000–10,000 words)
Use these headings, in this order:
- `## Bottom line`: 5–8 bullets. Do outsiders agree on the drivers, the industry and the plan? What is the single
  biggest difference?
- `## Scorecard`: a table with columns Topic | Company view | Outside view: bull | Outside view: bear | Verdict | Key
  sources. One row per key driver and one per filings research debate. Verdict is one of agrees, differs, adds, no outside view.
- `## Where outsiders agree`: a table with columns Ledger id | Claim | Who agrees.

  In both tables, the Company view and Claim columns are the ledger id plus a paraphrase of 12 words or fewer
  (the filings research already has the full text).
- `## Drivers`: one `###` per driver. Cover:
  - who differs, what they think, and why
  - how strong the reasoning is: evidence-based, model-historicalsd, narrative, or no reason given
  - each view's source tier (see "Source tiers" below), and which tier carries the verdict
  - whether sell-side and buy-side split
  - drivers outsiders weight that the filings research didn't, and drivers they think matter less
- `## Industry direction`
- `## Growth plan`
- `## Turning points`: for each move, what outsiders said before it, what happened, and who was right. Then a
  credibility read: whose view has held up better, the company's or the Street's, and on what?
- `## Gaps`: for every gap, its status, the answer, the tier and the source. Give detail only for the gaps that matter
  to a driver.
- `## What changes in our view`:
  - each driver: confirmed, re-weighted or replaced, and why
  - changes to the forecast structure compared with Filings research §11
  - new watch items
  - handoff notes for /model-consensus: which estimates likely build in which views
- `## Still open`: each question, and who could answer it (expert call, channel check, or management).
- `## Thin coverage`: where search came back thin, kept separate from where nobody outside covers the topic. When
  blocked pages (fetched.csv `blocked`) cover a large share of the relevant results, say so and suggest the user drop
  those pieces into Sellside Research as PDFs.
- `## Answers to the user's questions`: only if questions were given. Numbered to match `questions.md`, each with
  citations.

## Rules
- Copy every citation exactly from the marks or notes. Never add a fact, a number or a citation.
- Weigh, don't count. One well-reasoned bear case outweighs five analysts repeating guidance.
- **Source tiers (house weighting).** Weight every outside view by its source tier, in the order of the
  Sellside Research folders: 1 broker research, then 2 independent research, then 3 independent analysis, then
  4 news and trade press. Sell-side reports carry their tier in `{WORK}/run.json`. Web sources take it from
  `holder_type`:
  - `sell-side`: tier 1. A broker view known only through a news piece keeps tier 1 but is marked second-hand.
  - `independent`: tier 2 for a rating shop (Morningstar, CFRA, Argus, Value Line), tier 3 for everything else
    (Seeking Alpha, Substack, newsletters, student funds).
  - `buy-side` and `short-report`: tier 3.
  - `press`, `press-quoted` and `anonymous`: tier 4.

  `official` sources (company, regulator, law text) are facts, not views, and sit outside the tiers. When views
  conflict, the higher tier carries the verdict. A lower tier overrides it only with evidence the higher tier lacks
  (a document or a reported figure); say so when that happens. Within a tier, weigh by reasoning as above. Put the
  tier next to each view, e.g. "BofA (tier 1)".
- Hindsight pieces never count as what people thought at the time.
- Undated sources rank below dated ones.
- Don't retell the filings research. Point to it as "(see Filings research §x)".
- Square brackets are only for citations.
- Reply only with the output path and a summary of 150 words or less.
