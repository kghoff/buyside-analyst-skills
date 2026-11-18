# short-analyst assignment

You are given: W (work folder), W/context.md and W/context.json, W/rowmap.md, and the research root R
(`<research_dir>/<TICKER>/`). Read references/short_brief.md first.

## Read, in this order (Markdown before PDF)
1. context.md: code's ticks and the numbers behind them, the links, the short data, the stale-price check.
2. The filings research report and the street research report under R (newest of each).
3. The latest 10-Q and 10-K, and the last two earnings call transcripts under R.
Note the line numbers of everything you will cite.

## Decide
- Every one of the 17 scorecard rows (ids in short_brief.md, section 2). Every reason is at least 8 words.
  Computed rows: keep code's tick unless the documents show code is misreading the number (e.g. growth capex for a
  new plant); an override needs >= 12 words saying why. Code's ticks are judged at your inputs (a hurdle you change
  can flip the IRR-wedge row). Judgment rows: a yes needs a file.md:line anchor and the quote it rests on (or a
  Sheet!$A$1 anchor with the anchor_value the cell shows); no / unknown need only a reason.
- Smoke: read for auditor, CFO / CAO changes and changing metric disclosures. Each flag: anchor + quote. Say what
  you read in smoke_checked (>= 8 words).
- Short type and alpha bucket (or "none"): exactly as listed in short_brief.md, section 4; reason >= 8 words.
- Catalyst: is there one within the next two prints (soon: true / false)? Text, anchor (line, or "judgment").
  soon = true needs a file.md:line anchor and the quote that dates the event; "judgment" only for false.
- Inputs: reward_eps, reward_pe (the reward case: where EPS and the multiple land if the thesis is right),
  dream_eps, dream_pe (what a semi-rational bull believes), takeout_premium (what a buyer would pay over today; anchor
  to a deal premium in the documents when there is one). The seven house inputs keep anchor "house" and the house
  value (short_brief.md, section 11) unless a reason of >= 12 words says why not. Cell anchors: Sheet!$A$1 with
  anchor_value as the cell shows it; line anchors: file.md:N relative to R with anchor_value the number printed
  there (35% -> 0.35). Anchor "judgment" needs a reason of >= 12 words.
- Takeout candidate (true / false) and why.
- Verdict: one of Alpha short / Filler short / Watchlist / No short. The rule (short_brief.md, section 11) decides;
  a different call needs >= 12 words. "why": one line, <= 40 words.

## Write
W/short_plan.json in exactly this shape (an example is in the skill's tests/fixtures/plan_example.json):
{"ticks": {"<row id>": {"tick": "yes|no|unknown", "reason": "...", "anchor": "...", "quote": "..."}},
 "inputs": {"<key>": {"value": 0.0, "anchor": "...", "anchor_value": 0.0, "reason": "..."}},
 "type": {"value": "...", "reason": "..."}, "bucket": {"value": "...", "reason": "..."},
 "catalyst": {"soon": false, "text": "...", "anchor": "...", "quote": "...", "reason": "..."},
 "takeout_prone": {"value": false, "reason": "..."},
 "smoke": [{"flag": "...", "anchor": "file.md:N", "quote": "..."}], "smoke_checked": "...",
 "verdict": {"value": "...", "reason": "..."}, "why": "..."}
Then reply exactly: PLAN WRITTEN. If you are sent problems, fix only those and reply PLAN WRITTEN again.
