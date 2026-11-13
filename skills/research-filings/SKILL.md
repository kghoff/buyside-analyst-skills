---
name: research-filings
description: Fundamental research on one company from ONLY what the company itself released (10-Ks, 10-Qs, earnings calls, press releases / 8-Ks, decks, investor events, segment recasts, proxies) in the /collect-documents folder - no sell-side, no investor letters, no web. Every document is read (repeat text filtered), the key drivers (usually 3) are found with code-backed driver math and a PM-style challenge, and a forecasting structure is recommended from the disclosures that exist. Delivers a cited, illustrated PDF report (about 20k words, 8 sections) and writes the charts the user keeps using into their model (a Filings Charts tab: fixed vs variable costs, profit bridge, price vs volume, guidance vs actual; plus annotations, yearly returns vs the market with eras, and the stock tables on the Idio Chart tab). Run after /collect-documents, /model-historicals, /model-ratios, /model-kpis and /model-price-history. Use when the user runs /research-filings TICKER or asks for filings research.
---

# /research-filings

```bash
SK="<this skill's base directory>/scripts"      # the base directory is shown when the skill loads
SKILLS="<this skill's base directory>/.."
```
Skills and agents are named here without a prefix. Installed as a plugin, Claude Code lists them as
`buyside:<name>` (e.g. skill `buyside:model-historicals`, agent `buyside:filings-analyst`): use the name as listed.

`R="$SKILLS/research-filings"` (scripts in `$R/scripts`, prompts in `$R/references`). Agents:
`subagent_type: filings-analyst` (no web, no shell). The agent ships in the repo's `agents/` folder.

Setup: the PDF is printed by WeasyPrint (`pip install weasyprint`; on a Mac also `brew install pango`), plus poppler
(`pdftotext`, `pdftoppm`, `pdfinfo`) for the checks and previews. render.py finds Homebrew's pango by itself.

The scripts do everything code can answer; the agents do the judgment. Everything you tell the user is
plain English.

**Hard rules.**
- Company documents only. Never read `Sellside Research/` or `Investor Letters/`, and never search the web. That
  includes you, the main agent.
- The model is read-only until step 8, which adds to it on a verified copy and never changes the user's own cells or
  shapes.
- You never read raw sources. You read reader summaries and the scripts' output.
- Never say "done" with a check open.

Create a task list with these steps.


**MOD fill convention (house default).** Ordinary rows: quarter cells plain, fiscal-year cells grey; section title rows (text in column A) carry their section colour across every quarter and year; spacer columns and year columns with no quarters (2050E) untouched. `scripts/modfill.py` enforces it: the build runs `fix` after every save and the check fails on any break (`python3 scripts/modfill.py check MODEL`). Never hand-colour MOD cells; if you add or rewrite MOD rows outside the scripts, run `python3 scripts/modfill.py fix MODEL MODEL` and then `check` before saying done.

## Prompt fills (used in every dispatch)
- `{COMPANY}`, `{TICKER}`, `{AS_OF}`: the company name, ticker and confirmed as-of date
- `{SK}`: `$R` (the skill folder, not the scripts folder)
- `{WORK}`: `$W`; `{PHASE}`: `$P`
- `{NOTES_OR_NONE}`: the paths of `$W/user_notes.md` and `$W/questions.md` that exist, or `none`
- `{MODEL_REQUESTS}`: anything the user asked to have put in the model (charts, KPI rows), or `none`
- `{NOTES_PATHS}`: every `$W/digests/<group>.md` (step 2b), one per line; the full reader notes stay in
  `$W/readers/*/notes.md` for anyone who needs more detail

## 0. Preflight
`python3 $R/scripts/preflight.py --ticker <T> [--src DIR] [--model PATH] [--price PATH]`. On `stop`, tell the user each
`missing[].fix` in plain English and stop. Otherwise keep `src`, `model`, `price.kind`, `price.path` and `out` from
its JSON: `SRC=<src>`, `MODEL=<model>`, `P=<out>`, `W=<out>/_work`.

If the model has no "Idio Chart" tab, run /model-price-history for the ticker first: step 8
annotates that tab. It pauses once for the user to download the price files.

Then ask the user ONE AskUserQuestion with two questions:
- confirm the as-of date (`as_of`)
- "Any notes or questions for this company?" (a file path or typed questions, or none)

If the notes are a handwritten PDF:
1. Render each page in two halves:
   `python3 $R/scripts/slides.py grab <pdf> <page> "$W/notes/p<page>a.png" --dpi 200 --crop 0,0,1,0.5`, and the same
   with `--crop 0,0.5,1,1` to `p<page>b.png`.
2. Transcribe it yourself into `$W/user_notes.md`. Mark uncertain words `[?]` and show the user the list.

Save numbered questions to `$W/questions.md`.

## 1. Inventory, filter, slices, model
```bash
python3 $R/scripts/inventory.py --src "$SRC"
python3 $R/scripts/filter.py --src "$SRC"
python3 $R/scripts/slices.py --src "$SRC"
python3 $R/scripts/modeldata.py --model "$MODEL" --work "$W" --ticker <T> --price-kind <price.kind> --price "<price.path>"
```
Read `$W/inventory.md`. Tell the user about everything under "Not read" (files on disk the filings research can't use) and under
"Registered but not saved (gaps in the company record)" (documents /collect-documents knew about but couldn't save).

## 2. Readers
1. `python3 $R/scripts/readcheck.py --src "$SRC" status`. Before dispatching, tell the user how many slices are to read
   and the estimated time. Keep 6 readers running, starting a new one as each finishes: about (todo slices / 6) ×
   7 minutes (DXCM: 175 documents, 41 slices, about 2 hours including fixes).
2. For each `todo` slice, dispatch one reader (model sonnet, prompt `$R/references/reader_prompt.md`), in parallel,
   **at most 6 at a time**. Fills, from the slice's entry in `$W/slices.json`:
   - `{SLICE_TITLE}`: its `title`
   - `{FILES}`: one line per file, `<label> → <SRC>/<read>`
   - `{OUT_DIR}`: `$W/readers/<id>`
   - `{MODEL_ROWS}`: `$W/model_rows.md`
3. After each reader returns, run `python3 $R/scripts/readcheck.py --src "$SRC" check <id>`. On problems, send the
   problems back to the same agent (SendMessage) or re-dispatch with them listed.
4. Keep dispatching until `status` shows no `todo`. **Don't continue until every slice passes.**

To keep dispatches short, write each slice's filled-in prompt to `$W/readers/<id>/assignment.md` and dispatch with
"Read `<that path>` and follow it exactly." Readers take 4–9 minutes each; the common check failure is a
non-citation in square brackets, which the reader fixes in a minute when sent the problem.

## 2b. Digests
About 40 reader notes are far too much for one agent to read (DXCM: ~370,000 words). Group the slices by document
type, about 6 slices or 60,000 words per group (e.g. 10-Ks early / late, 10-Qs early / late, calls, releases,
decks + events, proxies). For each group, write `$W/digests/<group>.assignment.md` from
`$R/references/digest_prompt.md` (`{GROUP_TITLE}`, `{NOTES_LIST}` = that group's notes paths, `{OUT}` =
`$W/digests/<group>.md`) and dispatch one digest agent (sonnet), at most 6 at a time. Every later agent reads the
digests, not the reader notes.

## 3. Merge and driver math
1. `python3 $R/scripts/merge_data.py --src "$SRC"` (writes series.csv, conflicts.md, coverage.md,
   guidance_track.csv).
2. `python3 $R/scripts/drivers.py --src "$SRC" suggest` (lists candidate metric names).
3. Write `$W/drivers_config.json`. Every metric name exactly as `suggest` printed it:
   ```json
   {"revenue": "<metric>", "cogs": "<metric>", "opex": ["<metric>", "..."], "operating_income": "<metric>",
    "first_year": 2015, "last_year": 2025, "tax_rate": 0.21,
    "splits": {"<split name, e.g. Geography>": ["<metric>", "..."]},
    "units": [{"name": "<e.g. Revenue per user>", "revenue": "<metric>", "units": "<metric>"}],
    "net_income": "<metric>", "da": "<metric>", "sbc": "<metric>", "wc": "<metric>", "cfo": "<metric>",
    "capex": "<metric>"}
   ```
   Choose:
   - the revenue, cost of revenue, opex and operating-income rows; `last_year` = the last full fiscal year
   - `tax_rate` (the model's last full-year effective rate)
   - every revenue split the coverage matrix shows the company disclosing
   - unit metrics, if any
   - the six cash-flow rows (net income, D&A, SBC, working capital change, CFO, capex); the FCF bridge needs all six
4. `python3 $R/scripts/drivers.py --src "$SRC" run`. If it names a metric not in series.csv, fix the config. If the
   anatomy shows a split differing from revenue by more than 1%, fix the config (wrong rows) or say why in the
   judgment calls.

## 4. Drivers, PM review, answer
1. Dispatch the driver analyst (opus, `$R/references/driver_prompt.md`).
2. Dispatch a separate PM reviewer (opus, `$R/references/pm_review_prompt.md`).
3. Send `pm_review.md` back to the driver analyst (SendMessage, or re-dispatch with both files). It answers each
   challenge in a `## Response to the PM review` section and revises the drivers if the challenge wins. Disagreement
   that's left stays in the file.
4. If an agent lists numbers it needed but drivers_math lacks, add them: add the rows to `drivers_config.json` and
   rerun `drivers.py run` when the math covers it; otherwise write it into the text yourself as an explicit
   equation with its cited inputs. Replace each `(needs calc: ...)` placeholder.

## 5. Visuals
1. `python3 $R/scripts/slides.py sheets --src "$SRC"`.
2. Dispatch the visuals agent (sonnet, `$R/references/visuals_prompt.md`).
3. `python3 $R/scripts/charts.py --src "$SRC"` and `python3 $R/scripts/slides.py grabs --src "$SRC"`. On chart
   failures, fix the spec (the metric names come from series.csv's first column, exactly) and rerun. On a grab
   failure (page or crop out of range), fix that pick in `slides.json` and rerun.
4. Write `$W/figures.md`: one line per figure, `fig/<file> | <caption with source>`.

## 6. Write
1. Write `$P/sections/00-cover.md` from the outline (`$R/references/report_outline.md`); `{N}` = the number of
   documents in `$W/inventory.json`, `{DATE}` = today.
2. Dispatch 4 writers (opus, `$R/references/writer_prompt.md`) in parallel, with `{SECTION_NUMBERS}` = 02, 03–04,
   05–06 and 07–09.
3. Then dispatch 1 writer for section 01, the summary; it reads all the other sections first.
4. Handle the writers' "calcs needed" lists as in step 4.4, and collect their gaps and outside-source model rows.

## 7. Check
0. `python3 $R/scripts/repeat_check.py --src "$SRC"`. If paragraphs are flagged or the word count is outside
   17,000–23,000, send `$W/repeat.md` to the writers of those sections (each keeps the fact in its home section
   and cuts or cross-references the rest). Rerun until it's clean.
1. `python3 $R/scripts/numcheck.py --src "$SRC" --report "$P/sections"` for the totals, then once per section file (`--report <file>`), copying each `numcheck.md` to `$W/numcheck/<section>.md`, so checkers can split the work.
2. If anything is unconfirmed, weak, uncited, a bad citation or a bad quote, dispatch checkers: one per group of about 4 sections (about 6 in parallel), each told its section files and their `$W/numcheck/` lists, to check every weak number in sections 01, 05 and 06 and the 15 most important elsewhere. Each checker is (sonnet,
   `$R/references/checker_prompt.md`) with `{SOURCE_PATHS_NOTE}` = "find the file's `md` path by its label in
   `$W/inventory.json`; the path is relative to `<SRC>`; never use the filtered copy in `_work/filtered/`".
3. Rerun numcheck.
4. Append what's still unconfirmed to section 09 under "Unconfirmed numbers", and the judgment calls (step 10) under
   "Judgment calls".

## 8. Model handoff
Puts the charts and tables the user keeps using into their model. Work on a copy; the user's file is replaced only after the
check passes, and no copy is kept afterwards.
1. If MOD rows were inserted since step 1 (by you or the user), rerun `modeldata.py` (step 1) so model_series.csv
   points at today's rows; handoff.py stops if it is stale.
2. `python3 $R/scripts/handoff.py --src "$SRC" --model "$MODEL" --context` (writes `$W/handoff_context.json`).
3. Dispatch the handoff agent (sonnet, `$R/references/handoff_prompt.md`); it writes `$W/model_handoff.json`.
4. Check the model isn't open in Excel (no `~$<model file name>` lock file in its folder; if there is, ask the user to
   close it). Then:
   ```bash
   T=$(mktemp -d)
   cp "$MODEL" "$T/before.xlsx"
   python3 $R/scripts/handoff.py --src "$SRC" --model "$T/before.xlsx" --out "$T/after.xlsx"
   python3 $R/scripts/xlverify.py "$T/before.xlsx" "$T/after.xlsx" --work "$T"
   ```
   xlverify must print 0 differences and no broken XML: every value that was in the model is still there. Then
   `cp "$T/after.xlsx" "$MODEL"` (only if the model file is unchanged since the copy) and remove `$T`.
5. Look at the result: `python3 -c "import sys; sys.path.insert(0,'$R/scripts'); import lo; print(lo.render_pdf('$MODEL', '$W/model_preview'))"`,
   then render the Filings Charts page and the Idio Chart page (`lo.page_png`) and look at them: every chart drawn,
   no text cut off, each alpha-chart note's arrow on its date. LibreOffice draws charts a little differently from
   Excel; judge layout, not pixels.
6. Tell the user in the delivery: the blocks written, notes filled, and any of their cells kept (`kept_users_cells`).



## 9. Render and look
1. Render:
   `python3 $R/scripts/render.py "$P/sections" "$P/<YYYY-MM-DD> <T> Filings Research Report.pdf" --footer "<T> filings research · <Mon YYYY>" --preview "$W/preview"`
   The .md keeps its bracket citations; the PDF turns each into a numbered footnote at the foot of its page,
   restarting at 1 in each section (each `#` / `##` heading). Blue numbers are company documents, orange are our own
   work (citations starting `Calc`, `Model` or `price.csv`); `[unconfirmed]` prints as a small yellow flag. render.py
   checks that every footnote lands on the page of its number and moves a paragraph to the next page when one
   doesn't; a `WARNING: footnote ...` line means one still didn't fit. Tell the user which page and source.
2. Look at every preview PNG for broken images, tables split badly, footnotes, or a blank or wrapped cover. Fix and
   re-render.

## 10. Deliver
Tell the user, in plain English:
- a 2–3 sentence takeaway: the drivers and the forecast build
- the PDF path and its word count (repeat_check)
- what went into the model (step 8): tabs, blocks, notes, and the xlverify result
- the numcheck counts
- an explicit list of judgment calls: the config choices, conflicts settled, how shorthand in their notes was read,
  anything estimated
- if any row the user typed into their model from an outside source (e.g. CDC or IDF figures) was used: which rows, and
  that the report labels them as their model inputs, not company evidence
- the count of gaps left for the street research

Then ask the user (AskUserQuestion): "The filings research recommends this forecast build: <the build in two sentences from the
forecast section's §6.1>. Run /model-forecast now?" On yes, invoke the model-forecast skill for the ticker.
