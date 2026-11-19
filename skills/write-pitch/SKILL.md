---
name: write-pitch
description: Write the stock pitch for a company from everything the earlier skills produced - a long PowerPoint pitch deck, a core deck (slides 1-10), a 2-page pitch sheet, a Markdown copy, and SUM's write-pitch boxes. An agent (pitch-analyst) reads the filings and street research, the earlier agents' reasoning, the valuation / short / earnings notes, a digest of every tab of the model and pictures of its charts; keeps a plate file; makes the call (Long / Short / Watch) from Valuation's and Short Check's verdicts against the Valuation tab's hurdles, overriding only with cited evidence; and writes the pitch plan with every number anchored to a cell, a research line or a calc. A second agent plays the PM and attacks the draft; the analyst concedes or defends with evidence. Code checks the structure, the call against the hurdles and every number and quote, builds the decks, the sheet and the PDFs, and writes only the empty (or still its own) SUM boxes: thesis summary, trading plan, valuation thoughts, buy and no-brainer prices, management contact. Works for any listed company. Run after /model-summary; rerun each print. Use when the user runs /write-pitch TICKER or asks for a pitch, a pitch deck or an elevator pitch.
---

# /write-pitch

Writes the pitch: what we think, why the Street is wrong, what it's worth and how we get paid. **Any company**:
nothing here is specific to one stock. Explain everything in plain English, and tell the user every judgment call
(yours, the analyst's and the PM's).

```bash
SK="<this skill's base directory>/scripts"      # the base directory is shown when the skill loads
SKILL="<this skill's base directory>"           # absolute: it fills {SKILL} in the assignments
```
Skills and agents are named here without a prefix. Installed as a plugin, Claude Code lists them as `buyside:<name>`.

There is **no approval pause**: the analyst decides, a PM agent attacks it, code checks every number, and the report
tells the user every call. The only change to the model is SUM's write-pitch boxes, and only the ones that are empty
or still hold what the last run wrote; anything the user typed stays.

**Keep no model copies.** From Step 4 on, the run holds copies of the model (`$W/values`, later `$W/out.xlsx`, and
`$W/build` with the decks drawn from them). On every stop or abort after Step 4, for any reason (a failed check, a
verify problem, a changed checksum, the user calling it off, a look-step fault you can't fix), first run
`rm -rf "$W/values" "$W/out.xlsx" "$W/build"`, then tell the user.

## Requirements
- Python 3 with openpyxl, python-pptx, python-docx, PyMuPDF and Pillow, installed for the system `python3` (every
  script runs with `python3 -I`, which ignores `pip install --user` packages); pytest to run the tests.
- LibreOffice for the recalculation, the tab pictures and the PDFs (`brew install --cask libreoffice`).
- The model needs MOD with a forecast, DCF, Multiples, Valuation and SUM; the research folder needs the filings and
  street research reports. Short Check (needed for a short call), Earnings, Consensus, the industry tabs, Filings
  Charts, Idio Chart and the valuation / short / preview / after-print notes are used when present.

## Step 1: Preflight
`python3 -I "$SK/preflight.py" --ticker <T>` (add `--model <path>` if the user names a model, `--research <dir>` if
the research folder is not `research_dir/<T>` from the settings file). It prints JSON. Set
`M` = `model`, `MD` = the model's folder, `R` = `research`, `P` = `pitch_dir`, `W` = `work`, `MODE` = `mode`
(`first`, or `rerun` when `$W/plate.md` exists) and keep `optional_missing` and `warnings`.
`mkdir -p "$W" "$MD/_model_work/write-pitch"`.
- `status` = `stop`: tell the user, in plain English, each `missing` item and its `fix` (the skill to run, or the
  `python3 -m pip install ...` line for a Python package that does not import under `-I`), and the
  `stale` quarter if set (a quarter was reported after the last valuation note or SUM build: rerun /model-valuation,
  then /model-summary). Stop.
- Tell the user every `warnings` line (e.g. freshness could not be checked) and the `optional_missing` list.

## Step 2: Lock and checksum
1. If `~$<model file name>` exists next to `M`, ask the user to close Excel and wait.
2. `SHA=$(shasum -a 256 "$M" | cut -d' ' -f1)`: keep it for Step 10. Never write to `M` before then; keep no backup
   copies.

## Step 3: Ask the user
One AskUserQuestion: "Any notes, views or primary research for this pitch (expert calls, channel checks, management
conversations, an angle to test)?" Write what they say, as they said it, to `$W/user_notes.md`. If they have none,
`rm -f "$W/user_notes.md"` (an old run's notes must not pass as new) and use `none`.

## Step 4: Digest and tab pictures
Clear what an earlier run left: `rm -rf "$W/values" "$W/look" "$W/build" "$W/unverified.json" "$W/anchor_problems.json"`.
```bash
V=$(python3 -I -c 'import sys; sys.path.insert(0, sys.argv[1]); import lo; print(lo.recalc(sys.argv[2], sys.argv[3]))' "$SK" "$M" "$W/values")
python3 -I "$SK/digest.py" --values "$V" --out "$W/digest.md"
python3 -I "$SK/render_tabs.py" --values "$V" --out "$W/tabs"
```
`lo.recalc` makes a recalculated copy of the model in `$W/values/` (a minute or two; the model is only read).
`digest.py` writes every tab's text, notes and numbers with their cells; `render_tabs.py` writes PNG tiles of every tab
and `$W/tabs/index.md`. `$V` stays until Step 10 (the checks read it); then it is deleted.

## Step 5: The analyst
1. Reading list: `python3 -I "$SK/reading_list.py" --research "$R" --model-dir "$MD" --work "$W"`; on `rerun` add
   `--since $(date -r "$W/plate.md" +%F)` (the old plate is listed first, then only what changed since it). It prints
   the numbered list in the spec's reading order and a "Missing (optional)" section. Tell the user what is missing.
2. Fill `$SKILL/references/assignment.md` into `$W/analyst.assignment.md`. Replace every `{KEY}`:

   | Key | Value |
   |---|---|
   | `{TICKER}` | the ticker |
   | `{COMPANY}` | `company` in `$R/_manifest.json` if present, else the ticker |
   | `{AS_OF}` | today, YYYY-MM-DD |
   | `{MODE}` | `MODE` |
   | `{SKILL}` | `$SKILL`, the absolute skill folder (the agent runs elsewhere; a relative path points nowhere) |
   | `{WORK}`, `{RESEARCH}` | `$W`, `$R` (absolute) |
   | `{DIGEST}`, `{TAB_INDEX}` | `$W/digest.md`, `$W/tabs/index.md` |
   | `{READING_LIST}` | reading_list.py's whole output |
   | `{OPTIONAL_MISSING}` | preflight's `optional_missing`, comma-separated, or `none` |
   | `{OLD_PLATE_OR_NONE}` | `` `$W/plate.md` `` on `rerun`, else `none` (the plate stays in place; the analyst updates it) |
   | `{USER_NOTES_OR_NONE}` | the text of `$W/user_notes.md`, or `none` |

   Then `grep -o '{[A-Z_]*}' "$W/analyst.assignment.md"` must print nothing.
3. Dispatch the `pitch-analyst` agent (model opus) with: "Read `$W/analyst.assignment.md` and follow it exactly."
   (the absolute path). Keep its id: it gets the PM review and the check problems later. Wait for `PLAN WRITTEN`.
   Relay its five lines to the user briefly (the call, the most important thing, base / risk and R/R with the
   3-year IRR, buy and no-brainer prices, the weakest part).

## Step 6: The PM
1. Fill `$SKILL/references/pm_assignment.md` the same way into `$W/pm.assignment.md` (it uses `{TICKER}`, `{WORK}`,
   `{RESEARCH}`, `{DIGEST}`, `{SKILL}`); the grep must print nothing.
2. Dispatch a second, separate `pitch-analyst` agent (model opus) with: "Read `$W/pm.assignment.md` and follow it
   exactly." Wait for `REVIEW WRITTEN`; tell the user the verdict line.
3. SendMessage the analyst (by its id): "The PM review is in `$W/pm_review.md`; follow 'When you get the PM review'
   in your assignment." Wait for `PLAN REVISED`; tell the user the call now and the challenges left standing.

## Step 7: Checks (at most 2 rounds back to the analyst)
1. The verdicts and hurdles: `python3 -I "$SK/labels.py" --values "$V"`. It reads, by their labels in column A
   (values in B), Valuation's "Overall verdict (the agent's call: Buy / Hold / Sell)" (empty = Hold), Short Check's
   "Verdict (agent's call)" (else "Verdict (the rule)"; no tab = none), and Valuation's "IRR hurdle", "Buy at R/R"
   and "Table-pound at R/R". It prints JSON whose keys are plan.py's flags; pass each non-null one. Keep its `notes`
   for the report (each is a fallback the user must hear).
2. Run both:
   ```bash
   python3 -I "$SK/plan.py" --plan "$W/pitch_plan.json" --valuation-verdict "<valuation_verdict>" \
       --short-verdict "<short_verdict>" --irr-hurdle <irr_hurdle> --buy-rr <buy_rr> --pound-rr <pound_rr>
   python3 -I "$SK/anchors.py" --plan "$W/pitch_plan.json" --values "$V" --research "$R" --json "$W/anchor_problems.json"
   ```
   Each prints one problem per line (or `plan OK` / `anchors OK`) and exits 1 on any.
3. Problems → SendMessage the analyst: "Code found these problems; follow 'When you get check problems' in your
   assignment." and paste every line of both. Wait for `PLAN REVISED`; run both again. At most 2 rounds.
4. After round 2:
   - plan.py problems stop the run: tell the user each one in plain English and build nothing. The model is
     untouched. Delete the model copies: `rm -rf "$W/values" "$W/out.xlsx" "$W/build"`.
   - anchors.py problems: `cp "$W/anchor_problems.json" "$W/unverified.json"`. build_deck.py names each one as
     UNVERIFIED in the speaker notes of the slides that use it (nowhere on the slide face), and the report lists
     every one. With none, make sure no old file is left:
     `rm -f "$W/unverified.json" "$W/anchor_problems.json"`.

## Step 8: Build
1. Names: `python3 -I "$SK/names.py" --pitch-dir "$P" --ticker <T>` prints `long`, `core`, `sheet`, `md`:
   `<date> <T> Pitch.pptx`, `<date> <T> Pitch (core).pptx`, `<date> <T> Pitch Sheet.docx`, `<date> <T> Pitch.md`. If
   any file of that set exists it adds ` (2)`, ` (3)`… to every name: never overwrite an earlier pitch. Build into
   `$B` under those file names; Step 9 moves them into `$P`.
2. Build:
   ```bash
   B="$W/build"; mkdir -p "$B"
   python3 -I "$SK/build_deck.py" --plan "$W/pitch_plan.json" --template "$SKILL/assets/pitch_template.pptx" \
       --values "$V" --research "$R" --tabs "$W/tabs" --out-long "$B/<long name>" --out-core "$B/<core name>"     # add --unverified "$W/unverified.json" if it exists
   python3 -I "$SK/build_sheet.py" --plan "$W/pitch_plan.json" --out "$B/<sheet name>"
   python3 -I "$SK/build_md.py" --plan "$W/pitch_plan.json" --pm-review "$W/pm_review.md" --out "$B/<md name>"
   python3 -I "$SK/export_pdf.py" "$B/<long name>" --out-dir "$B"      # and the same for the core deck and the sheet
   ```
   Each PDF lands next to its source with the same name.

## Step 9: Look
1. `python3 -I "$SK/export_pdf.py" --pngs "$B/<long name>.pdf" --out-dir "$W/look/deck"` and the same for the
   sheet's PDF into `$W/look/sheet`. Read every PNG. Check the core deck's PDF has 10 pages (slides 1-10).
2. Look for text running out of its box, tables cut off, empty or unreadable charts, a picture in the wrong place, a
   sheet longer than 2 pages. Fix the cause: text too long goes back to the analyst (SendMessage the slide and what
   to shorten; then Step 7 again on the changed plan); a layout fault is the builder's to fix. Rebuild (Step 8.2)
   and look again. Never hand-edit an output. If you cannot make it right, stop: delete the model copies
   (`rm -rf "$W/values" "$W/out.xlsx" "$W/build"`) and tell the user what is wrong and on which slide.
3. When it looks right, `mkdir -p "$P"` and `mv -n` each file of `$B` (decks, sheet, Markdown, PDFs) into `$P`; then
   check `$B` is empty. `-n` never overwrites: a file left behind means one of that name appeared since names.py ran,
   so rerun names.py and move it under the new name.

## Step 10: SUM boxes
```bash
python3 -I "$SK/sum_boxes.py" --model "$M" --plan "$W/pitch_plan.json" \
    --record "$MD/_model_work/write-pitch/sum_written.json" --out "$W/out.xlsx" > "$W/sum_boxes.json"
python3 -I "$SK/verify.py" --before "$M" --after "$W/out.xlsx" --expect "$W/sum_boxes.json"
```
sum_boxes.py edits the XML of a copy (never openpyxl's save): a box is written only if empty or still equal to what
the last run wrote; anything else is the user's and stays. verify.py must print `verify OK` and exit 0: it proves
every other part of the workbook is byte-identical. Any problem: stop, do not copy, delete the model copies
(`rm -rf "$W/values" "$W/out.xlsx" "$W/build"`) and tell the user the problems in plain English.
1. If `written` is empty, the model needs no change: skip to 4.
2. `shasum -a 256 "$M"` again: if it differs from `SHA`, the user saved meanwhile: stop, delete the copies
   (`rm -rf "$W/values" "$W/out.xlsx" "$W/build"`) and tell the user to rerun /write-pitch.
3. Check `~$<model file name>` again (ask the user to close Excel). Then `cp "$W/out.xlsx" "$M"`.
4. `mv "$MD/_model_work/write-pitch/sum_written.next.json" "$MD/_model_work/write-pitch/sum_written.json"` (the record
   of what this run wrote, so the next run can tell the user's changes from its own).
5. Delete every copy of the model the run made (keep none): `rm -rf "$W/values" "$W/out.xlsx" "$W/look" "$W/build"`.
   Keep the plate, the plan, the PM review, the digest, the tab pictures, `unverified.json` and `sum_boxes.json`.

## Step 11: Report
Tell the user, in plain English:
- The call and the action, and any override of the Valuation or Short Check verdict with its reason and evidence
  (`override` in the plan); labels.py's `notes` (an empty verdict read as Hold, a rule verdict used, a house hurdle).
- The most important thing, the three thesis points, the two risks, the 12-month base / risk and R/R, the 3-year IRR,
  the buy and no-brainer prices.
- The PM's verdict (pass to IC / not good enough yet / kill), what the analyst conceded, and every challenge left
  standing (they are on the "PM challenges" slide and the hard questions).
- The file paths in `$P`: long deck, core deck, pitch sheet, Markdown copy and their PDFs.
- The anchors result, and **every UNVERIFIED item** (`unverified.json`: the number or quote and why it failed). The
  run is not done until the user has seen them.
- SUM boxes: written (`written`), kept because the user typed in them (`kept`), left alone (`skipped_null`), not
  found (`missing`: rerun /model-summary), and sum_boxes' `warnings`; or that the model was not changed.
- Every judgment call: each entry of the plan's `notes`, your own (fixes in the look step, anything shortened).
- The missing optional inputs (preflight's `optional_missing` and the reading list's "Missing" section) and
  preflight's `warnings`.
- Next steps: rehearse with the pitch sheet (the 20-second pitch, the 3-minute script, the hard questions); rerun
  /write-pitch after the next print (after /model-update, /model-valuation and /model-summary); open the model in
  Excel, where SUM recalculates.
