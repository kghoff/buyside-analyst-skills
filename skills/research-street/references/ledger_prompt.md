# Ledger prompt (fill the {BRACES}; dispatch with subagent_type street-analyst, model opus)

You are building the claims ledger for the street research on {COMPANY} ({TICKER}), as of {AS_OF}. The filings research formed a
view from the company's own documents. The street research will score every outside view (sell-side reports, web sources)
against this ledger, so it must hold every company claim worth testing, and nothing the filings research doesn't say.

Read in full:
- `{WORK}/phase1_extract.md` (filings research sections 02, 09–13 and 15)
- `{WORK}/gaps.json`
- `{WORK}/turning_points.json`
- `{P1_SECTIONS}/01-*.md` (the summary)

The user's notes and questions: {NOTES_OR_NONE}

Write `{WORK}/ledger.csv`. The header is exactly `id,topic,claim,phase1_cite,phase1_section`, and every field is
quoted. Aim for 60–90 rows plus one G row per gap.
- **A claim** is one sentence a source could agree or disagree with: "Revenue per customer keeps falling, but by less
  each year". "Driver 2 is revenue per customer" is not a claim.
- **topic** is one of:
  - `driver1`, `driver2`, `driver3`: one per key driver, numbered as in the filings research's key drivers section (a fourth driver is `driver4`).
    For each driver, cover what it is, its history, the company's explanation, the company's outlook, and what
    the filings research says would prove it wrong.
  - `industry`: the company's account of industry structure, competition, pricing and payers.
  - `plan`: guidance, long-range plan targets, capital allocation.
  - `debate`: one row per Filings research §13 debate, written as its question plus the filings research's lean.
  - `turning`: one row per turning point with `"major": true`, plus any whose driver the filings research calls "not explained".
    The claim is what the company said at the time, with the date.
  - `gap`: exactly one row per entry in gaps.json, with id `G<n>`; the claim is the gap, phrased as a question.
  - `other`.
- **ids:** `D1-01`, `D1-02`… for driver 1, and the same pattern for the other drivers (`D<driver>-<nn>`); then
  `I01`… for industry, `P01`… for plan, `B01`… for debates, `T01`… for turning points, `G<n>` for gaps, and
  `O01`… for other.
- **phase1_cite** is the strongest company citation the filings research gives for the claim, copied exactly and without brackets,
  e.g. `DXCM 2025 10-K, Item 7 / Revenue`. **phase1_section** is the section number, e.g. `10.2`.
- Copy numbers exactly as the filings research wrote them. Never add a claim the filings research does not make.

Reply only with the row count by topic, in 80 words or less.
