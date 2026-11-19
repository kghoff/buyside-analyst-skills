---
name: research-street
description: Street research on one company - outside views (the Sellside Research folder plus web search for analyst and investor views and gap-closing facts) scored against a ledger of the company's own claims taken from the filings research report. Reports only where outsiders differ, add something, or close a filings research gap, and why they think so; agreement is one short table. Not a consensus-estimates compiler (/model-consensus does that). Delivers a cited, illustrated PDF with a table of contents. Run after /research-filings. Use when the user runs /research-street TICKER or asks for street research.
---

# /research-street

```bash
SK="<this skill's base directory>/scripts"      # the base directory is shown when the skill loads
SKILLS="<this skill's base directory>/.."
```
Skills and agents are named here without a prefix. Installed as a plugin, Claude Code lists them as
`buyside:<name>` (e.g. skill `buyside:model-historicals`, agent `buyside:filings-analyst`): use the name as listed.

`R="$SKILLS/research-street"` (scripts in `$R/scripts`, prompts in `$R/references`).
`R1="$SKILLS/research-filings"` (research-filings' scripts are reused; never edit them from here).
Agents:
- `subagent_type: street-analyst` (no web) for the ledger, readers, synthesis, PM review, visuals, writers and checkers
- `subagent_type: street-researcher` (web, no shell) for the web researchers

The agent ships in the repo's `agents/` folder.

Setup: the PDF is printed by the filings research's render.py with WeasyPrint (`pip install weasyprint`; on a Mac also
`brew install pango`), plus poppler (`pdftotext`, `pdftoppm`, `pdfinfo`) for the checks, previews and sell-side
contact sheets. render.py finds Homebrew's pango by itself.

The scripts do everything code can answer, and the agents do the judgment. Explain everything to the user in plain English.

**Hard rules.**
- **Only what's different.** Report only what differs from the filings research, adds to it, or closes a filings research gap. Agreement
  goes in one table.
- **No consensus compiling:** no averaging of estimates, targets or ratings.
- **Source tiers:** outside views are weighted by the Sellside Research folder order: 1 broker research > 2
  independent research > 3 independent analysis > 4 news and trade press. Web sources map to the same tiers by
  holder type. The synthesis, writer and PM-review prompts carry the rule.
- **You, the main agent,** never search the web and never read the sell-side reports yourself. You read the agents'
  outputs and the scripts' output. Even the web check in step 0 is a researcher dispatch.
- **Paywalls and logins:** never get around them.
- **Never say "done" with a check still open.**

Create a task list with these steps.

## Prompt fills (used in every dispatch)
- `{COMPANY}`, `{TICKER}`, `{AS_OF}`: from `$W/run.json` and the manifest's `company`
- `{SK}`: `$R`; `{SRC}`: `$SRC`; `{WORK}`: `$W`; `{PHASE}`: `$P`
- `{P1_SECTIONS}`: run.json `phase1_sections`; `{P1_REPORT}`: run.json `phase1_report`; `{P1_WORK}`: `$SRC/Filings Research/_work`
- `{P1_SUMMARY}`: the `{P1_SECTIONS}/01-*.md` file (the summary)
- `{NOTES_OR_NONE}`: the paths of `$W/user_notes.md` and `$W/questions.md` that exist, or `none`
- Per dispatch:
  - readers: `{FILES}`, `{OUT_DIR}`
  - researchers: `{TITLE}`, `{LEDGER_IDS}`, `{FOCUS}`, `{EXTRA_READS}` (as listed in step 2, or `none`), `{OUT_DIR}`
  - writers: `{SECTION_NUMBERS}`
  - checkers: `{SECTION_FILES}`, `{NUMCHECK_FILES}`
  - cover: `{N_SELLSIDE}`, `{N_WEB}`, `{N_LEDGER}`, `{P1_DATE}`, `{DATE}`

To keep dispatches short, write each filled prompt to `$W/<role>/<id>.assignment.md`, then dispatch with "Read
`<that path>` and follow it exactly."

## 0. Preflight
`python3 $R/scripts/p2preflight.py --ticker <T> [--src DIR]`
- **`stop`:** tell the user each `missing[].fix` in plain English, then stop.
- **Otherwise:** set `SRC=<src>`, `P=<out>`, `W=<out>/_work`.

Then ask the user one AskUserQuestion with these questions:
- **Confirm the as-of date.** The default is today. If the user changes it, rerun preflight with `--as-of`.
- **"Any notes or questions for the street research?"** A file path, typed notes, or none. Save the notes' text to
  `$W/user_notes.md`, and the questions in them, numbered, to `$W/questions.md`.
- **Only if `newer_docs` is non-empty:** "These company documents are newer than the filings research: <list>. Continue anyway, or
  rerun /research-filings first?" If the user picks rerun, stop.

Web check: dispatch one `street-researcher` (model haiku): "Run one WebSearch for '<COMPANY> investor relations'
and WebFetch results until one returns page content (try up to 3; one site blocking with a 403 is normal); reply
only 'web ok' or 'web failed: <reasons>'". If it fails, tell the user web search isn't available and stop.
If `sellside` is 0, tell the user the report will use web sources only. The cover says so too.

## 1. Ledger
1. `python3 $R/scripts/ledger_extract.py --src "$SRC"`
2. Dispatch the ledger agent (opus, `$R/references/ledger_prompt.md`).
3. `python3 $R/scripts/p2check.py --src "$SRC" ledger`. If there are problems, send them back to the same agent and
   repeat until it passes.

## 2. Sell-side readers and web researchers (in parallel, at most 6 agents at a time)
1. **Readers:** one per group in `$W/run.json` `groups` (sonnet, `sellside_reader_prompt.md`).
   - `{FILES}`: one line per label, `<label> (tier <tier>) → <SRC>/<md>`
   - `{OUT_DIR}`: `$W/readers/<id>`
2. **Researchers:** write `$W/researchers.json` as
   `[{"id": "r1", "title": "...", "ledger_ids": [...], "focus": "..."}]`, then dispatch one researcher per entry
   (sonnet, `researcher_prompt.md`, `{OUT_DIR}` = `$W/research/<id>`). Use these assignments:
   - **One per key driver** (`r1`, `r2`, `r3`, …). Rows: that driver's rows plus its debates.
     Focus: "What do analysts and investors think about this driver's direction, size and causes, and how does it
     differ from the company's account? Find the bull and the bear case."
     `{EXTRA_READS}`: the `{P1_SECTIONS}/*key-drivers*.md` file (and `*key-debates*.md` if there is one).
   - **`ri`: industry direction and the growth plan.** Rows: industry, plan and other.
     Focus: "Do outsiders tell the same story about competition, pricing, payers and new entrants? Do they believe
     the long-range plan and guidance, and which parts do they discount?"
     `{EXTRA_READS}`: the files matching `{P1_SECTIONS}/02-*.md` (industry) and `{P1_SECTIONS}/*management*.md` (management
     credibility).
   - **`rg`: gaps.** Rows: every G row. If there are more than 20, split them in two (`rg1`, `rg2`) along gaps.json
     `group`.
     Focus: "For each gap, find the fact. Prefer primary sources, then secondary; an outside estimate counts only as
     opinion. 'No outside source covers it' is a valid answer."
     `{EXTRA_READS}`: `$W/gaps.json`.
   - **`rt`: turning points.** Rows: every T row.
     Focus: "For each move, what did outsiders say in the weeks before it and right after, dated? Was the Street
     right? Mark hindsight pieces."
     `{EXTRA_READS}`: `$W/turning_points.json`.
3. **Check each agent as it returns:** `python3 $R/scripts/p2check.py --src "$SRC" check <id>`. Send any problems back
   to the same agent, and repeat until it passes.
   - **Then check its numbers and quotes:**
     `python3 $R/scripts/p2numcheck.py --src "$SRC" --report <its notes.md> --out "$W/checks/<id>.numcheck.md"`.
     Send unconfirmed numbers, bad quotes and late sources back to the same agent to fix, and rerun until none are
     left. Weak items are OK.
   - **If a researcher comes back thin** (fewer than 5 marks, or its notes say coverage was thin): resume the same
     agent once (SendMessage): "Widen the search: other phrasings, competitor names, conference names, the CEO and
     CFO by name. Append to fetched.csv, searches.txt, excerpts.md, marks.csv and notes.md; never overwrite them."
     Rerun both checks. After that, accept the result and note it.
   - **Peer documents** (a competitor's own call or filing): if the agent wrote `<its out dir>/doc_requests.txt`, check
     the peer's folder and fetch only what's missing, with collect-documents' targeted fetch (never the full skill):
     `node "$SKILLS/collect-documents/scripts/peer_docs.mjs" --requests <its out dir>/doc_requests.txt --subject <T>`.
     It writes `peer_docs.json` beside the requests. Resume the same agent (SendMessage) with the `found` / `local`
     paths: "Read these peer documents and append to notes.md and marks.csv; cite each by its label." Rerun both
     checks (they accept the peer labels fetched for that agent). One round per agent; anything `missing` or
     `deferred` (Alpha Vantage's daily limit) goes in the thin-coverage notes.
4. **Don't continue** until `python3 $R/scripts/p2check.py --src "$SRC" status` shows every agent at `pass`.

## 3. Merge
`python3 $R/scripts/merge_marks.py --src "$SRC"`. Then tell the user in two lines:
- the mark counts
- how many gaps are closed, estimate-only, or still open

## 4. Synthesis, PM review, response
1. Dispatch the synthesis agent (opus, `synthesis_prompt.md`). If it wrote `$W/synthesis/doc_requests.txt`, fetch and
   resume it as in step 2.3.
2. Dispatch a separate PM reviewer (opus, `pm_review_prompt.md`).
3. Send `pm_review.md` back to the synthesis agent. It answers each challenge under `## Response to the PM review`
   and revises the synthesis where the challenge wins. Disagreement that's left stays in the file.
4. `python3 $R/scripts/p2numcheck.py --src "$SRC" --report "$W/synthesis.md" --out "$W/checks/synthesis.numcheck.md"`.
   Send unconfirmed numbers, bad quotes and late sources back to the synthesis agent, and rerun until none are left.

## 5. Visuals
1. `python3 $R/scripts/p2charts.py --src "$SRC" sheets`
2. Dispatch the visuals agent (sonnet, `visuals_prompt.md`).
3. `python3 $R/scripts/p2charts.py --src "$SRC" all`. On failures, fix the spec in charts.json or grabs.json, then
   rerun.
4. Look at every figure PNG. Re-crop any grab that cuts off the exhibit.

## 6. Write
1. Write `$P/sections/00-cover.md` from the outline's cover template:
   - `{N_SELLSIDE}`: the number of sell-side reports
   - `{N_WEB}`: the number of unique URLs with status `ok` across `research/*/fetched.csv`
   - `{N_LEDGER}`: the number of ledger rows
   - `{P1_DATE}`: run.json `phase1_as_of`
   - `{DATE}`: today
   
   If there are no sell-side reports, add "No sell-side reports were in the folder; web sources only." to the meta line.
2. `python3 $R/scripts/appendix.py --src "$SRC"`
3. Dispatch 3 writers in parallel (opus, `writer_prompt.md`), with `{SECTION_NUMBERS}` = 02–04, 05–07 and 08–09.
   Then dispatch 1 writer for 01, which reads all the other sections first.
4. Replace each `(needs calc: …)` yourself. Write an explicit equation with its cited inputs, or remove the claim.

## 7. Check
1. `python3 $R/scripts/repeat_check.py --src "$SRC"`. If paragraphs are flagged, or the word count is outside
   15,000–25,000, send `$W/repeat.md` to the writer of those sections, who trims or cross-references. Rerun until
   it's clean.
2. `python3 $R/scripts/p2numcheck.py --src "$SRC" --report "$P/sections"` gives the totals. Then run it once per
   section file (`--report <file> --out "$W/numcheck/<section>.md"`).
3. If anything is unconfirmed, weak, uncited, a bad citation, a bad quote or late, dispatch checkers (sonnet,
   `checker_prompt.md`), one per writer group (02–04, 05–07, 08–09, 01), in parallel.
4. Rerun both scripts. Whatever is still unconfirmed goes at the end of section 09, under "### Unconfirmed numbers".

## 8. Render and look
1. Render (the first line lists the peer documents fetched for agents, so their footnotes print as outside views):
   ```bash
   python3 -c "import sys; sys.path.insert(0, '$R/scripts'); import p2common; print('\n'.join(i['label'] for i in p2common.peer_items('$SRC')))" > "$W/outside_labels.txt"
   python3 $R1/scripts/render.py "$P/sections" "$P/<YYYY-MM-DD> <T> Street Research Report.pdf" --footer "<T> street research · <Mon YYYY>" --preview "$W/preview" --outside-labels "$W/outside_labels.txt"
   ```
   The table of contents is on by default; keep it in every report.
   The .md keeps its bracket citations; the PDF turns each into a numbered footnote at the foot of its page,
   restarting at 1 in each section (each `#` / `##` heading). Purple numbers are outside views (sell-side reports,
   investor letters, web pages, peers' own calls and filings), blue are company documents and the filings research report, orange are our own work
   (citations starting `Calc`, `Model` or `price.csv`); `[unconfirmed]` prints as a small yellow flag. render.py
   checks that every footnote lands on the page of its number and moves a paragraph to the next page when one
   doesn't; a `WARNING: footnote ...` line means one still didn't fit. Tell the user which page and source.
2. Look at every preview PNG for broken images, tables split badly, footnotes, and a blank or wrapped cover or
   contents page. Fix and re-render.
   render.py skips an image it can't find without a warning, so first check every figure path exists:
   `cd "$P" && grep -oh "](fig/[^)]*)\|src=\"fig/[^\"]*" sections/*.md | grep -o "fig/[^)\"]*" | sort -u | while read f; do [ -f "$f" ] || echo "MISSING $f"; done`
   Any `MISSING` line (or a `../fig/` path) is a broken figure: fix the path and re-render.

## 9. Deliver
Tell the user, in plain English:
- **The takeaway,** in 2–3 sentences: do outsiders agree on the key drivers, and what is the biggest difference?
- **The PDF path** and its page count.
- **Sources:** sell-side reports read, peer documents fetched (and any still missing), web pages read, pages blocked
  (and whether dropping some in as PDFs would help), and searches run. A peer's call or filing is never on the blocked
  list: it is fetched in step 2.3.
- **Gaps:** closed with a fact, estimate only, and still open.
- **Check results:** the numcheck counts and the repeat-check result.
- **Judgment calls:** how researchers were split, thin areas, and any hindsight sources excluded.
