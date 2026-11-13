# Model handoff prompt (filings-analyst, model sonnet)

Write `{WORK}/model_handoff.json` for {COMPANY} ({TICKER}). A script (handoff.py) turns it into a "Filings Charts"
tab and additions to the Idio Chart and Px Events tabs in the user's model. The numbers come from the model itself;
your job is the words: takeaways, eras, annotations and the stock tables.

Read:
- the finished report sections `{PHASE}/sections/03-economics.md`, `04-management.md` and `07-stock.md`, and the eras
  table in `02-industry-and-company.md`
- `{WORK}/drivers_math.md` and `{WORK}/drivers_config.json`
- `{WORK}/handoff_context.json`: the user's notes already on the alpha chart (`user_alpha_notes`), the top-20 idio days
  (`top_days`) and the Px Events dates (`events`), each with any annotation already there (`already`)
- for the guidance metric names: Grep the readers' `{WORK}/readers/*/guidance.csv` files (column 2 is the metric)
- for actuals: the metric names in the first column of `{WORK}/model_series.csv`

The user's extra requests for the model, if any: {MODEL_REQUESTS}

Rules:
- Copy facts from the sections. Add nothing they don't say. Plain English, in the house voice (short, direct).
- No bracket citations (the model cells link to their sources). End each takeaway with "(Filings research §N.N)".
- Never repeat a note the user already wrote: skip any date whose `already` is filled, and any move their
  `user_alpha_notes` already label.

The JSON:
```json
{
 "ticker": "{TICKER}",
 "takeaways": {
  "fixed_variable": "2-4 sentences: which costs are variable, semi-fixed or fixed and what that does to margins",
  "profit_bridge": "2-4 sentences: what drove operating income in the recent years",
  "price_volume": "2-4 sentences (only if drivers_config.json has units)",
  "guidance_<key>": "2-3 sentences per guided metric below: the pattern (beat, cut, sandbag) and the exceptions"
 },
 "guidance": [
  {"key": "revenue", "title": "Revenue ($M)", "unit": "$M",
   "names": ["every spelling of this metric in the guidance.csv files, exactly, e.g. revenue ($M)", "Revenue ($B)"],
   "scale": {"Revenue ($B)": 1000}, "basis": ["reported"],
   "actual": {"metric": "INCOME STATEMENT | Revenue"}},
  {"key": "gm", "title": "Non-GAAP gross margin", "unit": "%", "names": ["gross margin (%)"], "basis": ["non-GAAP"],
   "actual": {"ratio": ["NON-GAAP METRICS | Non-GAAP Gross Profit", "INCOME STATEMENT | Revenue"]}}
 ],
 "company_blocks": [],
 "returns_years": [2015, 2026], "last_is_ytd": true,
 "eras": [{"from": 2015, "to": 2017, "name": "short name", "text": "1-2 sentences: what the business was doing and what the stock did"}],
 "idio_notes": [{"date": "YYYY-MM-DD", "text": "6 words or fewer", "side": "above"}],
 "top_day_notes": {"YYYY-MM-DD": "one line: why the stock moved that day"},
 "event_notes": {"YYYY-MM-DD": "one line: what happened / why"},
 "event_moves": [{"date": "YYYY-MM-DD", "what": "what the company said", "driver": "which driver (the filings research's judgment)"}],
 "no_event_moves": [{"from": "YYYY-MM-DD", "to": "YYYY-MM-DD", "what": "what the documents say, and don't"}],
 "driver_by_period": [{"period": "2018-2021", "driver": "Driver 1 (volume)", "evidence": "one or two sentences"}],
 "stock_takeaways": ["one line each, 3-6 of them"]
}
```
- `guidance`: only metrics the company guided in at least 3 years. `names` must match the guidance.csv metric
  strings exactly (case aside); list every spelling and give a `scale` for any in other units. Long-range targets,
  growth rates and "meet or exceed" lines are separate metrics: leave them out. For a % metric the actual is a
  fraction (a ratio of two model metrics, or a metric already in %/100 form).
- `company_blocks`: only for the user's extra requests. Each is
  `{"title", "takeaway", "years": [first, last], "rows": [{"label", "metric": "<model_series metric>", "fmt": "usd"|"pct"|"mny"}], "note": "...", "chart": {"title", "rows": [row indexes], "type": "line"|"bar", "fmt": "\"$\"#,##0", "right": [row indexes on a right axis], "right_fmt": "0%"}}`.
- `returns_years`: the first year with a full year of prices to the as-of year; `last_is_ytd` when the as-of year
  is not over.
- `eras`: cover every year in `returns_years`, in order, no overlaps, from section 02's eras and section 07.
- `idio_notes`: 6-10 moves section 07 explains (dated releases, guide cuts, launches, big no-event drawdowns) that
  the user's notes don't cover. `side` "below" for drops, "above" for rises.
- `top_day_notes` / `event_notes`: only dates from `handoff_context.json` that the sections explain.
- `event_moves` and the rest: the tables in section 07, rewritten as JSON. Add `"dxcm"`, `"spy"`, `"idio"`
  (fractions) only for an event with no exact date in `events` (e.g. a month-long move), copied from section 07.

Reply only with the file path and the count of each list, in 60 words or less.
