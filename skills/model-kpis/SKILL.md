---
name: model-kpis
description: Add the user's NON-GAAP METRICS and KEY OPERATING METRICS sections to a company model (TICKER_model.xlsx). It finds every GAAP to non-GAAP reconciliation in the /collect-documents folder (releases, decks, event slides) and backfills them as GAAP line, adjustments, non-GAAP total, with a source note on every cell and a check against each reported total. It also scans the filings, decks, calls and events for every company-specific metric a buy-side modeler tracks (RPO, ARPU, subscribers, organic growth, backlog, same-store sales...) and backfills those too, each number checked against the line it came from. Then it adds the user's margin / growth rows. Use when the user runs /model-kpis TICKER or asks for non-GAAP, adjusted or KPI history in a model.
---

# /model-kpis

Step 4 of the user's chain: `/collect-documents` → `/model-historicals` → `/model-ratios` → **`/model-kpis`**. It can also run
before /model-ratios. It adds two sections to the MOD tab, placed as in the house layout (2026-11-06):

1. **NON-GAAP METRICS**, between the income statement and BALANCE SHEET: each reconciliation the company
   publishes, written as GAAP line (link) → grouped adjustments → non-GAAP total, plus non-GAAP EPS, then the user's
   M / G analysis rows.
2. **KEY OPERATING METRICS**, at the top, just above INCOME STATEMENT (the user's ALT DATA area): every
   company-specific metric the company reports consistently and the model doesn't already have, then analysis rows
   where they make sense. Models built before 2026-11-06 have the INCOME STATEMENT title on the period-header row.
   There it goes before BALANCE SHEET instead, and the build log says so.

The scripts do the mechanical work and the checking. Your job is the judgment, and **telling the user about every call**.
Write plain English. `reference/dxcm_example/` holds the DXCM plans to copy from.

```bash
SK="<this skill's base directory>/scripts"      # the base directory is shown when the skill loads
SKILLS="<this skill's base directory>/.."
```
Skills and agents are named here without a prefix. Installed as a plugin, Claude Code lists them as
`buyside:<name>` (e.g. skill `buyside:model-historicals`, agent `buyside:filings-analyst`): use the name as listed.


**Saving the model (house default).** The scripts edit with openpyxl but never save with it (openpyxl deletes the user's text boxes, shapes and pictures: 129 of them in the DXCM model). Every save goes through `scripts/safe_save.py`: it replays the logged row moves on the user's raw file, writes only the changed cells, styles and notes, and refuses to write unless the result equals openpyxl's, tab by tab. Never call `wb.save` on the user's model; a new row move must go through the logged insert / delete / remap functions.

**MOD fill convention (house default).** Ordinary rows: quarter cells plain, fiscal-year cells grey; section title rows (text in column A) carry their section colour across every quarter and year; spacer columns and year columns with no quarters (2050E) untouched. `scripts/modfill.py` enforces it: the build runs `fix` after every save and the check fails on any break (`python3 scripts/modfill.py check MODEL`). Never hand-colour MOD cells; if you add or rewrite MOD rows outside the scripts, run `python3 scripts/modfill.py fix MODEL MODEL` and then `check` before saying done.

## Step 1: Locate and back up

1. Run `python3 "$SKILLS/model-ratios/scripts/locate_model.py" --ticker <T>`.
   - `"status": "build"`: run the `/model-historicals` skill for the ticker (Skill tool, skill `model-historicals`, args `<T>`),
     follow it fully, then locate again.
   - Set `M=<model>`, `SRC=<src>` and `W=<model_dir>/_model_work/nongaap` (`mkdir -p "$W"`). If `src` is null, stop and
     tell the user to run `/collect-documents <T>` first.
2. If `~$<model file name>` exists next to the model, the file is open in Excel. Ask the user to close it, and stop.
3. If MOD already has a NON-GAAP METRICS or KEY OPERATING METRICS section, **stop and ask the user** whether to rebuild
   it. Rebuild only with their yes: add `--replace` to the build commands.
4. Copy the model to `B="$W/before.xlsx"`. Every check compares against it. Delete it once Step 4 passes: The user
   doesn't keep old model versions.

## Step 2: Non-GAAP reconciliations

1. **Extract:** `python3 "$SK/ng_extract.py" --src "$SRC" --model "$M" --work "$W"`. Read `$W/inventory.md` in full:
   - every adjustment line, by metric, with its periods
   - **"Different totals for the same period":** a restatement or a definition change
   - **"GAAP starting value differs from the model":** restated comparatives (e.g. a new accounting standard).
     Those columns are skipped automatically, along with the shares, add-backs and EPS in the same columns.
   - **"Restatement bridges":** tables walking old figures to restated ones. They aren't used as data, but they
     tell you what was restated and why. Say so in the report.

   If the company publishes no reconciliations, skip to Step 3 with a plan of `{"metrics": [], "eps": null}`.
2. **Plan:** write `$W/plan.json`, starting from `reference/dxcm_example/plan.json`.
   - **`metrics`:** each reconciliation the company publishes consistently (gross profit, operating income,
     adjusted EBITDA, net income are typical).
   - **Rows (the user: keep column B changes few, group simply):**
     - Give an adjustment its own row only if it behaves differently in a forecast: amortization of intangibles
       (predictable, from the 10-K schedule), SBC if excluded, material litigation or restructuring,
       equity-investment gains, tax adjustments.
     - Everything rare (COVID costs, debt extinguishment, one-off fees, FX) goes in a last-listed
       **"(+/-) Other Items"** row, using a negative-lookahead `match`. Each cell's note names its components.
   - **Link rows:** D&A, SBC and taxes link to the model's own rows (`"role": "link"`). Where the release figure
     differs, the builder types the release value and logs it.
   - **`prefer_restated`:** metric-years where a later release restated the **definition** while GAAP was unchanged
     (inventory.md shows different totals). Then every quarter of that year uses one definition and the quarters
     sum to the year.
   - **`exclude`:** any other period whose figure is on a basis the model doesn't use (rarely needed now).
   - **`share_splits`:** the split factors the model uses (`=94.1*4`).
   - **`analysis`:** `M` on each profit total, `G` on non-GAAP EPS. Add `M` with `"cost": true` on an adjustment
     only if it's recurring and worth tracking as % of sales.
   - **`notes`:** every judgment call, in plain English.
3. **Build:** `python3 "$SK/ng_build.py" --model "$M" --work "$W" --plan "$W/plan.json" --out "$M"`, then
   `python3 "$SK/analysis_rows.py" --model "$M" --out "$M" --plan "$W/plan.json"`.
   - Quarters are typed from each period's own release, Q4 included.
   - FY = SUM(Q1:Q4) when all four quarters exist, otherwise the twelve-month column is typed, with a note.
   - Every number gets a note (source file, page, md line, components, the reported total next to each derived
     total), and every row label lists the reconciliation lines grouped into it.
   - Colours: reported numbers blue, links green, formulas black.
   - Row inserts keep every formula in the workbook pointing at the same cells, including /model-ratios's rows and
     sections in MOD and any links from other tabs.

## Step 3: Company-specific KPIs

The user wants **any and all** company-specific metrics a buy-side modeler tracks. Most are non-GAAP in nature: RPO,
ARR, net retention, ARPU, subscribers, users, installed base, procedure volumes, organic / constant-currency growth,
backlog, book-to-bill, same-store sales, traffic, ticket, units, ASP, store counts, GMV, take rate, RevPAR, ASMs,
NIM, AUM, combined ratio, production, FFO... They also include revenue splits by product, geography or channel that
the company reports outside its income statement. Every metric found and reported consistently gets a row.

1. **Leads:** `python3 "$SK/kpi_scan.py" --src "$SRC" --model "$M" --work "$W"` writes `$W/kpi_leads.md`:
   - what's already in the model
   - a reading list
   - where the company defines its own metrics
   - recurring table rows that aren't model rows
   - cross-industry keyword hits

   These are leads, not answers.
2. **Discovery:** dispatch ONE `general-purpose` agent with the prompt below.
3. **Snippets:** `python3 "$SK/kpi_snippets.py" --src "$SRC" --work "$W" --plan "$W/kpi_plan.json"`. It writes
   `$W/snippets/<key>.md`: every matching line, grouped by document period, table rows with their header row.
   If a metric gets 0 lines, fix its `patterns` and rerun.
4. **Read the values:** dispatch `general-purpose` agents with `model: sonnet`, up to 4 metrics each and at most 5
   at a time, using the reader prompt below. Each writes `$W/values/<key>.json`.
5. **Check:** `python3 "$SK/kpi_check.py" --src "$SRC" --work "$W" --plan "$W/kpi_plan.json" --model "$M"`. Read
   `$W/kpi_check.md`:
   - **Rejected values** (number not on the cited line, wrong scale, a document reporting a later period): send
     them back to a reader once, with the reasons. Whatever is still rejected stays out; list it in the report.
   - **Conflicts:** the period's own document wins (as originally reported), unless the metric has
     `"prefer_restated": true` (every year) or a list of fiscal years such as `[2017]`. Use the year list when a
     later document redefined the metric and restated that year, so all of the year's quarters follow one
     definition. The built check below catches a year that mixes definitions, because its quarters won't add up to
     the reported full year. Send the reader back for the restated figures, set `prefer_restated` for that year,
     and say so.
   - **Sign from wording** (e.g. "declined 3%" → -3%): look at each one.
6. **Build:** `python3 "$SK/kpi_build.py" --model "$M" --work "$W" --plan "$W/kpi_plan.json" --out "$M"`.
   - If `kpi_plan.json` has an `analysis` list, run
     `python3 "$SK/analysis_rows.py" --model "$M" --out "$M" --plan "$W/kpi_plan.json"`.
   - Then `python3 "$SK/kpi_check.py" --src "$SRC" --work "$W" --plan "$W/kpi_plan.json" --model "$M" --built`.
     It must report 0 model problems.

### Discovery agent prompt

> You are a buy-side analyst finding every company-specific metric worth modeling for {COMPANY} ({TICKER}).
> The source documents are Markdown files under `{SRC}`. The leads are in `{W}/kpi_leads.md`. Read the leads, then
> read the documents yourself:
> - the newest 10-K's business section and MD&A, especially any "key metrics" section
> - the newest 4 earnings decks and press releases
> - the newest 4 call transcripts (prepared remarks, and analyst questions on metrics)
> - the newest investor-event slides
> - skim older releases and decks to see how long each metric has been reported, and whether its name or
>   definition changed
>
> Look for operating and business metrics: volumes, users, customers, subscribers, retention, pricing / ASP /
> ARPU, backlog / RPO / bookings, utilization, store or unit counts, same-store or organic growth,
> constant-currency growth, revenue by product, geography or channel when reported outside the income statement,
> industry-specific metrics, and any non-GAAP measure that isn't a GAAP-to-non-GAAP reconciliation (free cash flow
> as the company defines it, a non-GAAP tax rate, adjusted gross margin by segment). Section 0 of the leads lists
> what the model already has; don't repeat those. GAAP-to-non-GAAP reconciliations (adjusted EBITDA, non-GAAP net
> income...) are handled elsewhere; skip them.
>
> Write `{W}/kpi_plan.json`:
> ```json
> {"metrics": [{"key": "organic_growth", "label": "Organic Revenue Growth", "units": "%", "kind": "rate",
>    "definition": "the company's own definition, quoted or closely paraphrased, with the file it came from",
>    "why": "why a modeler tracks it, one sentence", "patterns": ["organic (revenue )?growth", "organically"],
>    "doc_types": ["release", "deck", "call"], "group": "Growth"}],
>  "not_tracked": [{"name": "...", "why": "mentioned once / guidance only / stopped in 2019 / ..."}],
>  "analysis": [{"row": "U.S. Revenue", "section": "KEY OPERATING METRICS", "macro": "G"}],
>  "notes": ["every judgment call, plain English"]}
> ```
> - `key`: short snake_case. `label`: the column-B label (short, the user's style).
> - `units`: one of `%`, `$ M`, `$` (per-unit amounts like ARPU), `M` (millions of a count), `#` (a count), `x`.
> - `kind`: `flow` (adds up over a year: revenue splits, units sold, procedures), `stock` (a level at a date:
>   users, backlog, RPO, store count), or `rate` (a % or ratio: growth, margin, retention).
> - `patterns`: Python regexes (case-insensitive) that find the metric's lines. Include the company's wordings,
>   and old names if it was renamed.
> - `doc_types`: from `release`, `deck`, `call`, `event`, `10-Q`, `10-K`, `recast`. Omit it to search everything.
> - `group`: rows with the same group sit together.
> - `analysis`: `G` (growth rows) on flows and stocks where growth matters. Not on rates.
> - Rows are for metrics reported in **4 or more periods**. Anything thinner, guidance-only or discontinued goes in
>   `not_tracked` with the reason.
> - If the company reports segments, list segment-level metrics only as the company reports them; don't invent
>   splits. If segments were redefined during the period, say so in `notes`.
> - Never write numbers in this file. Finish with a short list of the metrics and why each matters.

### Reader agent prompt

> Fill in the history of these metrics for {COMPANY} ({TICKER}): {KEYS WITH LABEL, UNITS, KIND, DEFINITION}.
> Evidence is in `{W}/snippets/<key>.md`: lines from every document, grouped by the document's period, each with
> its file (relative to `{SRC}`) and line number. Table rows come with their table's header row. Open the file
> itself whenever you need more context, such as which column is which period, or the units in a table title.
>
> For each metric write `{W}/values/<key>.json`, a list with one object per period you can source:
> `{"period": "Q3 25", "value": 0.123, "raw": "12.3%", "scale": 0.01, "file": "Press Releases/_md/<name>.md",
> "line": 23, "note": "worldwide; prior-year column of the Q3 26 release"}`
> - **period:** `Qn yy` for a quarter, `FY yy` for a full year or year-end, in the company's fiscal calendar (the
>   same labels as the file names).
> - **raw:** the number exactly as printed on that line. **scale:** what turns it into `value` in the metric's
>   units: `%` units are fractions (12.3% → 0.123, scale 0.01); "$1.2 billion" with units `$ M` → 1200,
>   scale 1000.
> - **line:** the exact line number where `raw` is printed. A code check rejects anything not printed on that
>   line.
> - Only printed numbers. Never calculate one: no differences, no sums, no growth rates from two figures, no
>   reading values off a chart.
> - Prefer the period's own document. Where an earlier period only appears as a later document's prior-year
>   column, use it and say so in `note`. If two documents give different figures for one period, list both; the
>   check picks one and reports the conflict.
> - A decline written in words ("declined 3%") is a negative value; say so in `note`.
> - For `stock` metrics, FY is the year-end figure. For `flow` metrics, add FY only where the company prints a
>   full-year figure.
> - If the definition changed (e.g. a new user count methodology), note it on the first period of the new basis.
> - Skip periods you can't source. Never guess. Finish with: periods filled per metric, and anything odd.

## Step 4: Verify

`python3 "$SK/ng_verify.py" --model "$M" --work "$W" --plan "$W/plan.json" --before "$B"`

It must show:
- 0 failed tie-outs (non-GAAP totals and EPS against what was reported)
- 0 formula errors
- 0 colour exceptions
- 0 missing notes
- 0 cells changed outside the two sections
- 0 other tabs changed (every link from another tab still points at the same line and value)

If anything fails, fix the plan or the values and rebuild from `$B` with `--replace`. Never hand-edit numbers to
pass. /model-ratios's rows moved with the inserts, so it doesn't need a rerun. A rerun needs `--replace` and is
safe.

## Step 5: Report

Write `$W/NONGAAP_JUDGMENT_CALLS.md` (working files stay in `_model_work`) from:
- `plan.json` notes
- `$W/build_log.json`
- `kpi_plan.json` notes and `not_tracked`
- `$W/kpi_build_log.json`
- `$W/kpi_check.md`
- the inventory's restatement sections

The final message gives:
- **What was built:** each non-GAAP metric and each KPI, with its period range.
- **The verify and kpi_check results.**
- **Every judgment call in plain English, with sizes:** definition changes and which version was used, years
  typed from twelve-month columns, grouping choices, split adjustments, links replaced by typed values, KPI
  conflicts and which figure won, rejected values.
- **Metrics found but not tracked**, and why.
- **Gaps:** periods the company didn't report. Gaps are normal: "if the company stopped reporting reconciliations
  in prior years, that's fine".
- A reminder to open the file in Excel, where the formulas calculate.

## Judgment policy (the user's rule)

- **Business segment changes:** stop and ask before building segment-level rows.
- **Everything else:** make the call and **say what you did**. A call the user disagrees with is fine; one they never
  hears about is not.
- **Source priority:**
  - **Markdown over PDF.** Use a PDF only if it has no Markdown twin; `sources.json` lists those.
  - **The earnings release is the primary source.** Decks round numbers and drop lines that are zero that
    quarter, so they only fill gaps.

## Reference

- `NOTES.md`: the DXCM findings that will recur at other companies, how the two claude.ai drafts were merged, and
  known limitations.
- `reference/dxcm_example/`: DXCM's `plan.json` and `kpi_plan.json`, and the expected verify results.
