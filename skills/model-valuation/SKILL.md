---
name: model-valuation
description: Add the Valuation tab to a company model (TICKER_model.xlsx) - what the stock is worth and whether the setup is worth owning. An agent (valuation-analyst) picks 1-3 multiples with reasons (P/E first unless ruled out, never one alone), anchors every reward and risk multiple to the Multiples ranges, comps or research, and works the reverse DCF itself through bear / base / bull scenario tries that run through model-dcf's own math. The tab shows 12-month reward, risk and R/R per multiple and blended, reward-to-volatility and the 1-sigma check, an R/R ladder, the 3-year IRR against the hurdle with the 3 R's and the double path, the DCF scenarios with gap flags, a probability tree and optional normalized earnings power. Every judgment is a yellow input cell the user owns, with its anchor and a reason; a rerun keeps every value the user changed. Also writes a valuation note (Markdown + PDF). Works for any listed company. Run after /model-dcf and /model-multiples; rerun each print. Use when the user runs /model-valuation TICKER or asks what a stock is worth, for a price target, risk/reward, an IRR or bull / base / bear scenarios.
---

# /model-valuation

Adds one tab, **Valuation**, that answers two questions: what is the stock worth, and is the setup worth owning?
It also writes a valuation note. **Any company**: nothing here is specific to one stock. Use plain English, and tell
the user every judgment call. Read `NOTES.md` before changing scripts.

```bash
SK="<this skill's base directory>/scripts"      # the base directory is shown when the skill loads
SKILLS="<this skill's base directory>/.."
RD=$(python3 "$SKILLS/../lib/settings.py" research_dir)   # your research folder: research_dir in the settings file
```
Skills and agents are named here without a prefix. Installed as a plugin, Claude Code lists them as `buyside:<name>`.

Yellow means the agent chose it and the user owns it. There is **no approval pause**: the agent decides, the code
checks every number, and the report tells the user every call. A rerun keeps any yellow cell the user changed.

## Requirements
- Python 3 with openpyxl, PyMuPDF (`fitz`) and Pillow; pytest to run the tests.
- LibreOffice for the recalculation and picture (`brew install --cask libreoffice`).
- WeasyPrint for the note's PDF (research-filings' `render.py`). Without it the note is Markdown only, and you say so.
- The model needs MOD with at least 8 forecast quarters, Px Data, a DCF tab and a Multiples tab.

## Step 1: Locate and check
1. `python3 "$SKILLS/model-ratios/scripts/locate_model.py" --ticker <T>` (or the path the user names). Set `M` to the
   model and `W=<model dir>/_model_work/model-valuation` (`mkdir -p "$W"`). All working files stay in `$W`.
2. If `~$<model file name>` exists next to `M`, ask the user to close Excel and wait.
3. `shasum -a 256 "$M"`: keep it for Step 8 (copy over). Never write to `M` before then; keep no backup copies.
4. A Valuation tab already there is normal (rerun each print). The build replaces it; the user's changed yellow
   cells are kept.

## Step 2: Context
`python3 -I "$SK/context.py" --model "$M" --work "$W" --ticker <T>` (add `--research-dir "$RD"` if the research
folder is not the setting's). It writes `$W/context.json`, `$W/context.md`, `$W/dcf_ctx.json` and
`$W/valuation_brief.md` (reused if newer than both reports). It stops, naming the skill to run, when MOD's forecast,
the DCF, Multiples or Px Data tab is missing, or MOD has fewer than 8 forecast quarters.
- It also stops when the DCF tab is out of date: its value per share is not what its own inputs give, or its rows
  and year columns are not where model-dcf now puts them (e.g. the tab was built for other revenue drivers than the
  current forecast plan's). Tell the user the printed reason and to rerun /model-dcf, then /model-valuation. Do not
  carry on: the scenarios would be typed into the wrong cells.
- Tell the user which brief sections were cut or missing (`brief_missing`, and the brief's summary).

## Step 3: Agent
Dispatch the `valuation-analyst` agent with the assignment `references/assignment.md` (the skill's folder) and the
paths: `W`, `$W/context.md`, `$W/context.json`, `$W/valuation_brief.md` and the research root `$RD/<T>/`.

## Step 4: Scenario loop
The agent works the reverse DCF itself. When it replies `TRY <n> WRITTEN`:
1. Run, always as its own process:
   ```bash
   python3 -I "$SK/scenario_eval.py" eval --dcf "$W/dcf_ctx.json" --try "$W/scenarios_try_<n>.json" \
     --ntm-eps <context.json metrics.eps.ntm.value> --ntm1-eps <context.json metrics.eps.ntm1.value> \
     --out "$W/scenarios_result_<n>.json"
   ```
2. Write its printed table to `$W/scenarios_result_<n>.md`.
3. SendMessage the same agent: "Result <n> is in scenarios_result_<n>.md".
4. Repeat until a try has `"final": true` or n = 5. At n = 5 without final, tell the agent this is the last round
   and it must make it final.

If eval exits with an error (an unknown input name, a bad shape), send the message to the agent as that round's
result and let it fix the try; this counts as a round.

## Step 5: Plan checks
When the agent replies `PLAN WRITTEN`:
1. `python3 -I "$SK/plan.py" --plan "$W/valuation_plan.json" --context "$W/context.json"`
2. `python3 -I "$SK/anchors.py" --plan "$W/valuation_plan.json" --values <context.json values> --context
   "$W/context.json"` (add `--research-dir "$RD"` if not the setting's).

Each prints one problem per line and exits 1 on any. On problems, send them all to the agent once to fix, then run
both again. If they still fail, stop: show the user the problems in plain English and do not build. The model stays
untouched.

## Step 6: Build and verify
1. `python3 "$SK/build.py" --model "$M" --work "$W" --ticker <T> --out "$W/out.xlsx"`. It never touches `M`. Keep the
   printed summary for the report: `user_kept` (cells the user had changed, agent value vs theirs) and `warnings`.
2. `python3 "$SK/verify.py" --model "$M" --out "$W/out.xlsx" --work "$W"` (add `--research-dir "$RD"` if not the
   setting's). It must print `"ok": true`. It
   recalculates in LibreOffice and compares every checked cell with the chapter math, scans for errors, proves every
   other part of the file is byte-identical, checks colours and the multiple pairing, re-types each DCF scenario into
   a copy of the DCF tab, and checks the anchors again. Keep its `recalculated` path for Step 7.
   On failure, fix an obvious cause and rebuild once; never hand-edit the output. If it still fails, stop and do not
   copy over: show the user the first failed cells and problems in plain English. The model stays untouched.
3. Look at `$W/valuation.png`: yellow inputs, the Reasoning column filled, no `#` errors except #N/A.

## Step 7: Note
`python3 "$SK/note.py" --work "$W" --ticker <T> --out-dir "$RD/<T>/Valuation" --values <verify's recalculated file>`
(add `--date YYYY-MM-DD` for another as-of date). This must run before Step 8 deletes `$W/verify/`. It writes
`<date> <T> Valuation Note.md` and `.pdf`. If it prints `"pdf": null`, tell the user the PDF was skipped and why (`pdf_skipped`).

## Step 8: Copy over
1. `shasum -a 256 "$M"` again. Changed since Step 1 = the user edited the model meanwhile: stop and rebuild from
   Step 6. If `~$<model file name>` exists, ask the user to close Excel and wait.
2. Unchanged: `cp "$W/out.xlsx" "$M"`, then `mv "$W/inputs_written.next.json" "$W/inputs_written.json"` (the record
   of what this build wrote, so the next rerun can tell the user's changes from the agent's).
3. Delete every copy of the model the run made (no backup copies): `$W/out.xlsx`, `$W/values/`, `$W/verify/` and
   `$W/dcf_stale/` if present. Keep the plan, tries, results, context, brief, `layout.json` and `valuation.png`.

## Step 9: Report (plain English)
- The overall verdict (Buy / Hold / Sell, row 3 at the top of the tab: the agent's call, a yellow cell the user owns) and its reason.
- The recommended multiples and why (and why P/E is not primary, if it isn't).
- Reward, risk, R/R and the verdict, per multiple and blended.
- Reward-to-vol and the 1-standard-deviation check.
- The 3-year IRR against the hurdle, its 3 R's (revenue, margin, multiple) and the double path.
- The DCF bear / base / bull values and what today's price implies, driver by driver.
- The gap flags (a DCF case more than 25% from its multiple-based target) and the agent's explanation of each.
- The probability-weighted value and where today's price sits.
- Which cells the user had changed (`user_kept`) and that they were kept.
- Every judgment call:
  - every entry in the plan's `notes`, and each scenario round with why it was rejected;
  - NTM is the sum of MOD's next four forecast quarters, NTM+1 quarters 5-8, the 3-year metric the year-3 quarters
    (with fewer, the IRR horizon is the last full year; say so);
  - today's price, net debt and diluted shares link to the DCF tab, so both tabs use one bridge;
  - multiples pair with their own value: levered metrics with equity value, unlevered with EV;
  - house inputs (hurdle, buy and pound R/R, discount, horizon, market growth) are chapter 11's defaults unless the
    agent changed one with a reason;
  - every number the agent chose is anchored to a cell, a research line or a forward sum, and was checked.
- The brief's cut and missing sections.
- The build's warnings.
- The note's path (and whether the PDF was skipped).
- That the Valuation tab is after Multiples, and a reminder to open the file in Excel, where it recalculates.
