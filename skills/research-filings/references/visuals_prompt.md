# Visuals prompt (filings-analyst, model sonnet)

The report teaches through pictures as much as text. Choose its charts and slide screenshots for {COMPANY} ({TICKER}).
Read: `{WORK}/drivers.md`, `{WORK}/drivers_math.md`, `{WORK}/coverage_key.md`, the "Screenshot ideas" and "Timeline"
sections of {NOTES_PATHS}, the chart spec format in the docstring of `{SK}/scripts/charts.py`, and the metric names
in `{WORK}/series.csv` (first column). Use metric names exactly as written there, including the " | " separators
(e.g. `INCOME STATEMENT | Revenue`); a name that doesn't match exactly fails the chart.
1. Write `{WORK}/charts.json`: 15–20 chart specs covering each key driver, revenue anatomy (share of revenue and of
   growth), price vs volume, seasonality / 2-year stack, margins, the profit bridge (waterfall), FCF and conversion,
   guidance vs actual, the stock vs company events (kind `price`), and the forecast-structure diagram from
   drivers.md. Price-chart events come from the readers' Timeline tables, and only company events: earnings
   releases, guidance changes, launches, investor days. House rules: plain titles; never two near-identical metrics
   in one chart (e.g. GAAP and non-GAAP P/E); non-GAAP for valuation; simple over dense; every spec has a source.
   Waterfall values must come from `drivers_math.md`; do no arithmetic of your own.
   The user's model can hold rows they typed in from outside sources (e.g. "Number of ppl with diabetes (CDC)", "IDF").
   They are the user's own model inputs, not company documents: if a chart uses one, its title or source says "user's
   model input (outside source)", and you list it in your reply.
2. Look at the contact sheets in `{WORK}/slides/*/sheet-*.jpg` (6 slides each, labeled S1…). Write
   `{WORK}/slides.json`: 20–30 picks `{"file": <label>, "page": <n>, "out": "slide_<short>_s<n>.png", "crop": null,
   "caption": "<why it matters> [<label>, S<n>]"}`. `page` must exist in that PDF; `crop` is null or
   `[left, top, right, bottom]` as fractions 0–1. Prefer slides that show a driver, a disclosure the filings lack,
   or a change between investor days. Skip near-duplicates (the same slide in later decks).
Reply with both paths and a 100-word summary.
