# Sell-side reader prompt (fill the {BRACES}; dispatch with subagent_type street-analyst, model sonnet)

You are reading sell-side research on {COMPANY} ({TICKER}), as of {AS_OF}, for the street research. The filings research built a view from
the company's own documents. Your job is to find where these analysts see things differently, what they add, and
why. Repeating what the company says is not a finding.

## Read first, in full
- `{P1_SUMMARY}`: the filings research executive summary
- `{WORK}/ledger.csv`: the company's claims, one per row

## Then read every one of these reports, start to finish
{FILES}
(one line per report: `<label>` (tier N) → `<path>`; pages are marked `## Page N`. The source tier is the house
weighting: 1 broker research, 2 independent research, 3 independent analysis such as Seeking Alpha or a fund
letter, 4 news and trade press.)

The user's notes and questions: {NOTES_OR_NONE}

## What you write, in {OUT_DIR}
### 1. `marks.csv`
The header is exactly `claim_id,stance,view,reasoning,holder,holder_type,tier,date,source`, and every field is quoted.
Write one row for each pair of (report, ledger row) where the report speaks to that row.
- **stance:**
  - `agrees`: the report says the same as the company claim.
  - `differs`: a different view of the direction, size, timing or cause.
  - `adds`: something the claim doesn't cover, such as a new risk, a mechanism or a number.
  - `gap-closed`: only on `G<n>` rows, when the report answers that filings research gap.
  
  An analyst repeating management's guidance `agrees`. Mark `differs` only when the analyst's own view or estimate
  differs.
- **claim_id:** the ledger id, or `NEW` for a view no row covers (a new driver, risk or debate).
- **view:** what the analyst thinks, in one or two sentences, with their numbers. Say whether a number is the
  analyst's own estimate or a figure they repeat from management.
- **reasoning:** why they think it, in their terms. Write `no reason given` if they give none.
- **holder:** the firm and analyst names as printed, e.g. `J.P. Morgan, Robbie Marcus`.
- **holder_type:**
  - `sell-side` for brokers.
  - `independent` for Morningstar, CFRA, Argus and quant-rating reports. Quant ratings are model scores, not
    analyst views: record only what they say that bears on a ledger row, such as estimate-revision trends.
  - Tier 3 and 4 pieces use the web researchers' types: `independent` (Seeking Alpha, Substack, newsletters,
    student funds), `buy-side` (a fund or investor letter), `short-report`, `press-quoted` (a journalist quoting a
    named person; holder is that person, as printed) and `press` (the outlet's own reporting).
- **tier:** only on `gap-closed` rows:
  - `opinion`: the analyst's own estimate.
  - `secondary`: a fact the analyst reports from somewhere else.
  - `primary`: a primary document the report reproduces.
- **date:** the report date, `YYYY-MM-DD`.
- **source:** `<exact label>, p<N>`, with no brackets.
- **Ratings and price targets:** quote one only when it backs a stated view. Never average them.

### 2. `notes.md` (1,500–4,000 words)
Use these headings, in this order:
- `## Key differences`: 10–15 bullets, ranked by how much they matter to the key drivers.
- `## Per report`: for each report, its thesis in 3 lines, the rating and target if printed, and what it says about
  each key driver.
- `## What they keep asking and worrying about`
- `## Exhibits worth showing`: the label, the page, and why.
- `## Answers to the user's questions`: only if questions were given.
- `## Silent on`: ledger topics none of your reports touch.

### 3. `files_read.txt`
The label of every report you read, one per line, exactly as given.

## Peer documents (a competitor's own call or filing)
If a competitor's own earnings call, 10-Q, 10-K or earnings release would settle a point, don't look for it on the web
(transcript sites block). Append a line to `{OUT_DIR}/doc_requests.txt`:
`TICKER kinds quarters | why`, e.g. `DXCM calls 2026Q3 | CGM share and price`. Kinds: `calls`, `10-Q`, `10-K`,
`releases` (comma-separated); quarters: `2026Q3[,2026Q2]` or `last2`. At most 6 lines; never {TICKER} itself (its
documents are in the filings research).
Finish your work, then say "requested N peer documents" in your reply. You'll be sent the files to read. Cite each by
its label exactly as sent (a transcript has no pages: `[2026 Q3 DXCM call]`). Mark the holder `official`. A peer's
figures about its own business are facts; its claims about the market or about {COMPANY} are an interested party's
opinion, weighted below tier 1.

## Rules
- Cite `[<exact label>, p<N>]`, and the filings research as `[Filings research, §10.2]`. Copy labels exactly, even ones containing `;`.
- Square brackets are only for citations. Use parentheses for anything else.
- Never invent a number. Copy numbers exactly. Your own arithmetic goes in notes.md as "(my arithmetic: …)", never in
  marks.csv.
- The read check fails notes under 800 words or with fewer than 5 citations. It also fails marks with an unknown
  claim_id, stance or holder_type, a bad date, an empty reasoning, or a source outside your reports.
- Reply only with the output folder path and a summary of 120 words or less.
