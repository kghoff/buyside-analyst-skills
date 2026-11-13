# Visuals prompt (fill the {BRACES}; dispatch with subagent_type street-analyst, model sonnet)

Pick the figures for the street research report on {COMPANY} ({TICKER}). The reader learns visually: show outside views next to
the company's record, not decoration.

## Read
- `{WORK}/synthesis.md`, including its response to the PM review
- `{WORK}/turning_points.json`
- the contact sheets under `{WORK}/sheets/<label>/sheet-NN.jpg`: every sell-side page, tagged S1, S2…
- the "Exhibits worth showing" in `{WORK}/readers/*/notes.md`

## Write
1. **`{WORK}/charts.json`**: 1–2 price charts in the filings research's format:
   `{"id": "px_views", "kind": "price", "title": "...", "start": "YYYY-MM-DD", "source": "Closes: price.csv (the filings research). Views: as cited in section 06.", "events": [["YYYY-MM-DD", "<label, 40 characters or fewer>"]]}`
   Each event marks a turning point, labeled with the outside view held before it, e.g. "JPM: guide too high".
   Use only dates and views that are in the synthesis.
2. **`{WORK}/grabs.json`**: 4–10 sell-side exhibits that show a view differing from the company's (a model, a chart,
   a table):
   `[{"file": "<exact label>", "page": N, "out": "ss_<tag>.png", "crop": [l, t, r, b] or null, "caption": "<what it shows> [<exact label>, p<N>]"}]`
   Crop values are fractions of the page from 0 to 1. Crop to the exhibit, not the whole page.
3. **`{WORK}/figures.md`**: one line per figure, `fig/<file> | <caption with source>`. Include
   `fig/stance_heatmap.png` and `fig/gap_status.png`, which are drawn automatically.

Reply only with the number of figures, in 40 words or less.
