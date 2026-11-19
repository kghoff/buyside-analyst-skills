# buyside-analyst-skills

Claude Code skills for the fundamental buyside analyst: collect a company's documents, build and analyze its model,
research it from its filings and from the Street, forecast, value and track consensus. Packaged as the Claude Code
plugin `buyside`. Explain everything in plain English.

## The skills, in run order
| # | Skill | Adds |
|---|---|---|
| 1 | collect-documents | 10-Ks, 10-Qs, releases, calls, decks, events, proxies, sell-side and investor letters → `<research_dir>/<TICKER>/` as PDF + Markdown |
| 2 | model-historicals | 10-year quarterly + annual income statement, balance sheet, cash flow (MOD tab) |
| 3 | model-ratios | growth, margins, ROIC / ROE / ROA, leverage, cash conversion, FCF inside MOD |
| 4 | model-kpis | non-GAAP reconciliations and company-specific operating metrics |
| 5 | model-price-history | Px Data, Px Events, Idio Chart tabs; daily prices from Yahoo (plain close for P/E, total return for returns; stooq only as fallback) |
| 6 | research-filings | report from the company's own documents; key drivers; forecast structure; Filings Charts tab |
| 7 | research-street | where sell-side and investors differ from the company, and why |
| 8 | model-forecast | driver-based quarterly 3-statement forecast (user approves the plan first) |
| 9 | model-dcf | 30-year key-driver DCF with reverse DCF; the user owns the inputs |
| 10 | model-multiples | where the stock trades: history, vs S&P, vs peers, ranges, reverse P/E, forward table, comp sheet with Include? toggles, P/E-vs-growth line through the peers, P/E vs core-peer median chart (Multiples tab) |
| 11 | model-valuation | what it's worth and whether the setup is worth owning: the agent's Buy / Hold / Sell verdict, 1-3 multiples with reasons, 12-month R/R per multiple and blended, R/R ladder, 3-year IRR and the 3 R's, DCF bear / base / bull from an agent-run reverse DCF, probability tree, valuation note (Valuation tab) |
| 12 | model-short | short check: FEV scorecard, short type and bucket, verdict, IRR wedge, risk case, print move, crowding, borrow, VaR sizing (Short Check tab) + short note |
| 13 | model-earnings-before | earnings preview: call and stance by rule, print R/R and implied PSUC, set-up, model checks, base rates, implied move, guidance trail, variance grid, frozen forecast (Earnings tab) + preview note |
| 14 | model-update | the reported quarter into MOD from the release (8-K Ex. 99.1), old forecast held in orange placeholders until the 10-Q, the 10-Q gaps on a rerun, restatements on approval, new guidance for Filings Charts, and a thesis-aware targeted forecast roll the user approves; rerun each print |
| 15 | model-earnings-after | after-print wrap: actual vs frozen forecast, SFOT, move vs expected and implied, estimates and valuation before / after, IRR now, guidance and long-term pace, checkpoint and react call (Earnings bands 9-15), Call Notes tab, after-print note; rerun at T+7 |
| 16 | model-summary | SUM tab, the first sheet: the PM's one-page view. Cap table with 3M ADV, NTM FCF yield, 3-year target and IRR, 12-month base and risk on the primary multiple, internal estimates vs Street on the Street's own basis (GAAP or non-GAAP by evidence, margins in bps) with Expected Delta and multiples per year, the probability tree, multiple ranges, the tactical R/R ladder. Every number links to its home tab; empty yellow boxes for write-pitch; conditional formatting on returns, IRR, R/R and Street variance |
| 17 | write-pitch | the pitch: an Opus analyst reads everything and makes the call, a PM attacks it; long PowerPoint deck, core deck (slides 1-10), 2-page pitch sheet, Markdown copy in Pitch/, SUM's write-pitch boxes |
| – | model-industry | optional: industry P&L and peer comparison tabs |
| – | model-consensus | optional: broker ratings, targets, estimates, rating history, consensus snapshots; rerun each print |

Naming: `collect-` gathers raw material, `model-` adds to the Excel model, `research-` writes a report, `write-`
(future) produces a deliverable such as a pitch deck. A new skill takes the prefix of what it produces.

## Rules every skill follows
- Works for any listed company. Nothing company-specific in scripts, prompts or lists; DXCM appears only as an example.
- The user owns the model:
  - shasum it before the build and again before copying over it; changed = stop and rebuild
  - ask the user to close Excel if `~$<file>` exists
  - never write a live model in tests
  - keep no backup copies
  - working files go in `<model dir>/_model_work/<skill>/`
- Never save the user's workbook through openpyxl. Edit the XML parts, and check that every other part is byte-identical.
- Colours: typed numbers blue with a source note; formulas black; links to other tabs green; user inputs yellow.
- Never type a number that isn't printed in a source. Readers cite file and line; a code check proves the number is on that line.
- Read Markdown before PDF. The company's own release is the primary source.
- Decide, keep going, and tell the user every judgment call. A call the user never hears about is the worst outcome.
- Every report or PDF has a table of contents after the cover.
- Settings come only from `lib/settings.*`; never hardcode them. The five settings are `sec_contact`, `research_dir`, `alpha_vantage_keys`, `chrome_path` and `xbrl_cli` (the path to the separate edgar-xbrl-financials CLI, which model-industry uses).

## Adding or changing a skill
Brainstorm → spec and plan in `docs/` (git-ignored, local only) → build with tests → `bash run-tests.sh --full` → update the
README skills table and this file's table.

## Layout and testing
- `skills/<name>/`: SKILL.md (what Claude follows), scripts/, tests/, references/ (prompts), NOTES.md (why things are the way they are; read it before changing scripts)
- `agents/`: helper agents the skills dispatch (filings-analyst, street-analyst, street-researcher, forecast-planner, valuation-analyst, short-analyst, earnings-analyst, pitch-analyst)
- `lib/settings.py|mjs`: the settings file reader
- `bash run-tests.sh`: every suite plus `check-refs.sh` (no personal paths or names), skipping tests marked `slow`
  (they start LibreOffice); use it while working, and on one skill run only that skill's suite.
  `bash run-tests.sh --full` runs everything; run it before any merge. Both must end ALL PASS.
- A new test starts LibreOffice only when the recalculation is what it checks: share one recalculated copy per
  suite (a session fixture) and mark such tests `@pytest.mark.slow`.
  Personal terms to keep out of the repo go one per line in `.refs-blocklist` (git-ignored; check-refs reads it).

---

## Operating rules

These rules apply to every task in this project unless explicitly overridden.
Bias: caution over speed on non-trivial work. Use judgment on trivial tasks.

### Rule 1 — Think Before Coding
State assumptions explicitly. If uncertain, ask rather than guess.
Present multiple interpretations when ambiguity exists.
Push back when a simpler approach exists.
Stop when confused. Name what's unclear.

### Rule 2 — Simplicity First
Minimum code that solves the problem. Nothing speculative.
No features beyond what was asked. No abstractions for single-use code.
Test: would a senior engineer say this is overcomplicated? If yes, simplify.

### Rule 3 — Surgical Changes
Touch only what you must. Clean up only your own mess.
Don't "improve" adjacent code, comments, or formatting.
Don't refactor what isn't broken. Match existing style.

### Rule 4 — Goal-Driven Execution
Define success criteria. Loop until verified.
Don't follow steps. Define success and iterate.
Strong success criteria let you loop independently.

### Rule 5 — Use the model only for judgment calls
Use me for: classification, drafting, summarization, extraction.
Do NOT use me for: routing, retries, deterministic transforms.
If code can answer, code answers.

### Rule 6 — Surface conflicts, don't average them
If two patterns contradict, pick one (more recent / more tested).
Explain why. Flag the other for cleanup.
Don't blend conflicting patterns.

### Rule 7 — Read before you write
Before adding code, read exports, immediate callers, shared utilities.
"Looks orthogonal" is dangerous. If unsure why code is structured a way, ask.

### Rule 8 — Tests verify intent, not just behavior
Tests must encode WHY behavior matters, not just WHAT it does.
A test that can't fail when business logic changes is wrong.

### Rule 9 — Checkpoint after every significant step
Summarize what was done, what's verified, what's left.
Don't continue from a state you can't describe back.
If you lose track, stop and restate.

### Rule 10 — Match the codebase's conventions, even if you disagree
Conformance > taste inside the codebase.
If you genuinely think a convention is harmful, surface it. Don't fork silently.

### Rule 11 — Fail loud
"Completed" is wrong if anything was skipped silently.
"Tests pass" is wrong if any were skipped.
Default to surfacing uncertainty, not hiding it.
## Bug-Fixing Strategy

1. **Diagnose with `/investigate`** (gstack, if installed). Four-phase root cause analysis.
2. **Write a failing test.** Prove the bug exists. Use a pytest or vitest test in the skill's tests folder.
3. **Fix with a subagent.** Give it the failing test and specific files.
4. **Verify.** All tests pass, `bash run-tests.sh --full` ends ALL PASS.

---

## Skill routing (if these skills are installed)

When the user's request matches an available skill, ALWAYS invoke it using the Skill
tool as your FIRST action. Do NOT answer directly, do NOT use other tools first.
The skill has specialized workflows that produce better results than ad-hoc answers.

Key routing rules:
- Product ideas, "is this worth building", brainstorming → invoke office-hours
- Bugs, errors, "why is this broken", 500 errors → invoke investigate
- Ship, deploy, push, create PR → invoke ship
- QA, test the site, find bugs → invoke qa
- Code review, check my diff → invoke review
- Update docs after shipping → invoke document-release
- Weekly retro → invoke retro
- Design system, brand → invoke design-consultation
- Visual audit, design polish → invoke design-review
- Architecture review → invoke plan-eng-review
- Save progress, checkpoint, resume → invoke checkpoint
- Code quality, health check → invoke health
