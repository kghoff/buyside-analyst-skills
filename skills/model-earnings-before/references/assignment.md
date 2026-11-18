# earnings-analyst assignment

You are given: W (work folder), W/context.md and W/context.json, W/rowmap.md, the research root R
(`<research_dir>/<TICKER>/`) and the web excerpts folder X (`R/Earnings Previews/_web/<quarter>/`). Read
references/earnings_brief.md first.

## Read, in this order (Markdown before PDF)
1. context.md: the quarter, the report date (and whether it is estimated), the model checks, base rates, the
   links, code's answers (set-up row value_perf, blow-up flags), the warnings and the documents since the last print.
2. Every document listed under "Documents since the last print" (paths relative to R): the print's release and
   call first, then conferences, filings, broker previews and news.
3. X/excerpts.md (the web pass; quotes, one per line) if it exists.
4. The newest filings research report and street research report under R.
Note the line numbers of everything you will cite.

## Decide
- setup: every row id in the brief (section 4) except value_perf, which code answers (give it only to override:
  a reason of >= 12 words). side is long, short, neutral or unknown; every reason is >= 8 words; a long or short
  side needs an anchor: file.md:line relative to R with the quote it rests on, or Sheet!$A$1 with the anchor_value
  the cell shows.
- risks: profit_stability, liquidity, valuation_skew, rating_change, revision: a whole-number score 1-5 and a
  reason of >= 8 words each.
- key_metric: value, reason (>= 8 words), anchor and quote.
- inputs: up_eps, up_pe, down_eps, down_pe, p_beat. Cell anchors Sheet!$A$1 with anchor_value as the cell shows it;
  line anchors file.md:N with anchor_value the number printed there (35% -> 0.35); "judgment" needs a reason of
  >= 12 words. p_beat is a probability (0-1) and usually a judgment. The upside price (up_pe x up_eps) must be above
  today's price and the downside price below it.
- call: quarter (beat / in line / miss), guide (raise / hold / cut / initiate / none given), expected_move, reason.
- whisper: text (your estimate of the buy-side bar, labeled as yours) and reason.
- stance: add / hold / trim / hedge as the rule says (brief section 10), with a reason.
- net, points (last_quarter, since_last_print, checkpoint) and judgment_calls (brief section 13).
  since_last_print may be empty only when context.md lists no documents and X has no excerpts.

## Write
W/earnings_plan.json in exactly this shape (an example is in the skill's tests/fixtures/plan_example.json):
{"quarter": "<the quarter in context.md>", "net": "...",
 "key_metric": {"value": "...", "anchor": "file.md:N", "quote": "...", "reason": "..."},
 "setup": {"<row id>": {"side": "long|short|neutral|unknown", "anchor": "...", "quote": "...", "reason": "..."}},
 "risks": {"<risk id>": {"score": 1, "reason": "..."}},
 "inputs": {"<key>": {"value": 0.0, "anchor": "...", "anchor_value": 0.0, "reason": "..."}},
 "call": {"quarter": "...", "guide": "...", "expected_move": 0.0, "reason": "..."},
 "whisper": {"text": "...", "reason": "..."}, "stance": {"value": "...", "reason": "..."},
 "points": {"last_quarter": [{"text": "...", "anchor": "file.md:N", "quote": "..."}], "since_last_print": [],
            "checkpoint": []},
 "judgment_calls": ["..."]}
Then reply exactly: PLAN WRITTEN. If you are sent problems, fix only those and reply PLAN WRITTEN again.
