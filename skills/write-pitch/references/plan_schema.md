# pitch_plan.json: the contract

The analyst writes `pitch_plan.json`; code checks it (`plan.py` for structure, `anchors.py` for truth) and builds the
decks, the pitch sheet, the Markdown copy and the SUM boxes from it. Anything that breaks a rule below comes back to
you as a problem to fix. The values used in the checks (slide types, layouts, text budgets, SUM boxes, calls and the
fallback hurdles) live in the skill's `scripts/common.py`; this page repeats them so you don't need to open it. The
hurdles themselves are the user's inputs on the Valuation tab (section 12, R20).

## Contents
1. The whole shape
2. Top-level fields
3. numbers: values, the `{key}` rule and anchors
4. Getting cell references from the digest
5. quotes
6. slides: the ten core slides
7. slides: support and appendix
8. pitch_sheet
9. sum_boxes
10. notes
11. Text budgets
12. Every rule the code enforces

## 1. The whole shape
```json
{
  "ticker": "XYZ", "as_of": "2026-11-19", "call": "Long", "action": "Buy",
  "starting_verdicts": {"valuation": "Buy", "short": "No short"},
  "override": null, "hurdle_override": null,
  "most_important_thing": "one sentence",
  "pitch_20s": "the 20-second pitch",
  "numbers": {
    "price":      {"value": 72.40, "shown": "$72.40", "anchor": "Valuation!C5"},
    "base_ret":   {"value": 0.31,  "shown": "+31%",   "anchor": "Valuation!F20"},
    "eps_27_ours":{"value": 3.30,  "shown": "3.30",   "anchor": "SUM!J12"},
    "irr_3y":     {"value": 0.125, "shown": "12.5%",  "anchor": "calc: (target_3y/price)^(1/3)-1"}
  },
  "quotes": [{"id": "q1", "text": "exact words", "file": "Earnings Calls/_md/2026 Q3 XYZ call.md", "line": 214}],
  "slides": [
    {"type": "title", "title": "LONG XYZ", "takeaway": "...",
     "image": {"pdf": "Investor Decks/2026 Q3 XYZ deck.pdf", "page": 4, "crop": [0.1, 0.2, 0.9, 0.8]},
     "notes": "speaker notes", "source": "company Q3 deck p4"},
    {"type": "thesis", "title": "Three Thesis Points", "takeaway": "...",
     "points": [{"head": "...", "body": "... {eps_27_ours} ..."}, {"head": "...", "body": "..."},
                {"head": "...", "body": "..."}],
     "notes": "...", "source": "..."},
    {"type": "risks", "title": "Two Key Risks", "takeaway": "...",
     "risks": [{"head": "...", "prob": 0.25, "if_hits": "...", "mitigant": "..."},
               {"head": "...", "prob": 0.15, "if_hits": "...", "mitigant": "..."}],
     "tripwires": ["...", "..."], "notes": "...", "source": "..."},
    {"type": "risk_reward", "title": "Risk / Reward", "takeaway": "...",
     "cases": [{"name": "Bull", "eps": "{bull_eps}", "pe": "{bull_pe}", "ret": "{bull_ret}", "prob": "{bull_p}"}],
     "ladder": "Valuation", "irr": "{irr_3y}",
     "three_rs": {"roll": "{r_roll}", "revisions": "{r_rev}", "rerating": "{r_rer}"},
     "notes": "...", "source": "Valuation tab"},
    {"type": "table", "section": "support", "supports": "thesis.1", "title": "...", "takeaway": "...",
     "table": {"header": ["", "2026E", "2027E"], "rows": [["Revenue", "{rev_26}", "{rev_27}"]]},
     "notes": "...", "source": "..."},
    {"type": "quote", "section": "appendix", "title": "...", "takeaway": "...", "quotes": ["q1"],
     "notes": "...", "source": "..."},
    {"type": "checklist", "section": "appendix", "title": "Stock-Selection Checklist", "takeaway": "...",
     "items": [{"q": "Business momentum positive or improving?", "a": "Yes"}], "notes": "...", "source": "..."}
  ],
  "pitch_sheet": {"script_3min": ["12 short paragraphs, chapter 3's steps"], "napkin": ["3-5 bullets"],
                  "hard_questions": [{"q": "...", "a": "..."}], "know_cold": ["price", "base_ret", "irr_3y"]},
  "sum_boxes": {"Thesis Summary": "...", "Trading Plan": "...", "Valuation Thoughts": "...",
                "Buy price": "{buy_price}", "No-brainer price": "{nobrainer_price}", "Mgmt contact": null},
  "notes": ["every judgment call, plain English"]
}
```
The example is cut down: a real plan has all ten core slides, three risk_reward cases, 10-25 support slides and the
appendix slides `pitch_brief.md` section 3 lists (the two checklists among them).

## 2. Top-level fields
| Field | What goes in it |
|---|---|
| `ticker` | The ticker, upper case. |
| `as_of` | Today's date, `YYYY-MM-DD`. |
| `call` | One of `Long`, `Short`, `Watch` (common.CALLS). |
| `action` | The size of the conviction in a few words: "Small buy", "Buy", "Pound the table", "Short", "Wait for {buy_price}". `{key}`s are allowed and checked. "Pound" needs the pound R/R (R21). |
| `starting_verdicts` | `valuation`: the value of the Valuation tab row labelled "Overall verdict (the agent's call: Buy / Hold / Sell)" (`Buy`, `Hold` or `Sell`); if that cell is empty (the valuation plan had no verdict), write `Hold` and say so in `notes`. `short`: the Short Check row "Verdict (agent's call)" (the user's own input) as the tab shows it (`Alpha short`, `Filler short`, `Watchlist`, `No short`); if that cell is empty, the row "Verdict (the rule)" (cell B5). `null` when there is no Short Check tab. Verdicts are compared ignoring case. |
| `override` | `null` when `call` follows the mapping (Buy → Long, Sell → Short, Hold → Watch). Otherwise `{"reason": "...", "evidence": "..."}`; `evidence` cites `file:line` or `Tab!Cell`. It covers the call only, never the hurdles. |
| `hurdle_override` | `null` unless a `Long` misses the IRR hurdle or the buy R/R (R20). Then `{"reason": "...", "evidence": "..."}`, cited the same way: why it is still a Long. It is the only thing that waives the hurdle check. |
| `most_important_thing` | One sentence: the differentiated view on where a number in the statements is heading. |
| `pitch_20s` | The full 20-second pitch (box budget, 420): position, why mispriced, what's changing, the number that matters, the valuation gap, the ask. It opens the pitch sheet; slide 2's `takeaway` is a version of it cut to 160 characters. |
| `numbers` | Every number the plan shows (section 3). |
| `quotes` | Every verbatim quote the plan uses (section 5). |
| `slides` | The ten core slides in order, then support, then appendix (sections 6-7). |
| `pitch_sheet` | The 2-page pitch sheet's text (section 8). |
| `sum_boxes` | Text for the SUM tab's write-pitch boxes (section 9). |
| `notes` | Every judgment call (section 10). |

## 3. numbers: values, the `{key}` rule and anchors
Each entry is `"<key>": {"value": <number>, "shown": "<string>", "anchor": "<anchor>"}`.
- **key**: lower case letters, digits and `_` (`price`, `eps_27_ours`, `eps_27_street`, `irr_3y`). Choose readable
  names; they appear in `know_cold`.
- **value**: the number itself, as a plain number. Percentages as fractions (31% → `0.31`); multiples as the number
  (18.5x → `18.5`); money in the units the cell holds.
- **shown**: exactly how it appears on the slide: `"$72.40"`, `"+31%"`, `"(18%)"`, `"18.5x"`, `"3.30"`, `"$1,204m"`.
  The rounding of `shown` sets the check's tolerance: `"$72.40"` must match to the cent, `"+31%"` to the whole
  percent, `"12.5%"` to a tenth of a percent.
- **The `{key}` rule.** Text never contains a typed number. Wherever a number appears in any text field (titles,
  takeaways, bodies, notes, table cells, the pitch sheet, SUM boxes), write `{key}`; the builder replaces it with
  `shown`. Every `{key}` used must exist in `numbers`. Years used as labels ("2027E", "Q3 26") are labels, not
  numbers, and may be typed; so may counts of things in your own sentence structure ("three thesis points"). Anything
  that measures the company or the stock goes through `numbers`.
- **Required keys** (the call check reads them): `price` (today's price), `base_ret` (12-month base return),
  `risk_ret` (12-month risk-case return, negative), `irr_3y` (3-year IRR at today's price), `target_3y` (3-year
  target price), `buy_price` and `nobrainer_price`. Add `rr_12m` (= base_ret / abs(risk_ret)) if you show the R/R.
  `buy_price` = `target_3y` / (1 + IRR hurdle)^3 and `nobrainer_price` = `target_3y` / (1 + no-brainer IRR)^3, the
  IRR hurdle being the Valuation tab's "IRR hurdle" input as the digest shows it (`calc: target_3y/1.15^3` for 15%;
  the house default 20% only when the tab has none, `calc: target_3y/1.2^3`) and the no-brainer IRR 30%
  (`calc: target_3y/1.3^3`). Code checks both against the hurdle it was given (R23).
- **Anchors**, three forms:
  1. `Tab!Cell`, e.g. `Valuation!F20`, `SUM!J12`, `MOD!H45`: a cell in the model. `value` must equal the
     recalculated cell at the rounding `shown` implies. Use the cell that holds the number, not one that links to it,
     when both exist; either passes if the values match.
  2. `file:line`, e.g. `Earnings Calls/_md/2026 Q3 XYZ call.md:214`: a line in a research file. The path is relative
     to the research root (the folder `<research_dir>/<TICKER>/` the assignment names). The
     `shown` number must be printed on that line, as a whole number (commas ignored), with its unit next to it:
     `%` (or `percent`, `pct`), `x` (or `times`), `bps` (or `bp`, `basis points`), `m` (or `mn`, `million`), `bn`
     (or `billion`), `k` (or `thousand`); a `$` with no `m` / `bn` / `k` needs a `$` before it. So `"$1,204m"` matches
     `$1,204 million` and `1,204 million` but not `1,204 days`, and `"$1.2bn"` does not match `1,204 million`: copy
     the form printed on the line. A sign must not be contradicted: `"+5%"` fails on "fell 5%" or "(5%)", `"-5%"` or
     `"(5%)"` fails on "grew 5%" (the three words before the number and the one after its unit are read for fell /
     declined / down / decrease and rose / grew / up / increase); an unsigned `"5%"` passes on "fell 5%" but not on a
     number printed negative ("-5%", "(5%)"). Use it for numbers the model doesn't hold:
     guidance, a market size, a sell-side estimate, a number from the user's notes (file
     `Pitch/_work/user_notes.md`).
  3. `calc: <expression>`, e.g. `calc: (target_3y/price)^(1/3)-1`, `calc: target_3y/1.2^3`: arithmetic over other
     keys. Allowed: key names, numbers, `+ - * / ^ ( )`, `abs`, `min`, `max`. The result must equal `value` at the
     shown rounding. It must use at least one key (`calc: 0.25` proves nothing; constants only beside a key, as in
     `target_3y/1.2^3`). Every key it uses must itself be anchored (no circles), and a calc on a key that fails its
     own check fails too.
- **Repeats agree.** Two keys with the same anchor must have the same `shown`. Better: use one key everywhere the
  number appears.

## 4. Getting cell references from the digest
The digest (`digest.md`) prints the model's numbers with their cells:
- **MOD**: one table per section. Above each table a line `columns: 2025=H, 2026E=M, Q3 26=K, ...` maps each period
  to its column letter; each row starts `| r<row> <label> |`. The cell is the column letter plus the row number: the
  2026E value of row `r45 Revenue` with `2026E=M` is `MOD!M45`.
- **Other tabs**: one line per row, `r12 (<row label>): B=1.2, C=0.3`; the cell is the letter plus the row
  (`Valuation!B12`). A `headers:` line above maps each column letter to its header and the header's own cell, e.g.
  `F=12-mo base (F4)`, so you can tell which column is which.
- **Notes**: `A1 (<row label>) = <value>: <note>`; the source note on a typed number often names the document line
  you can cite instead.
- **Bulk blocks** (long daily or weekly history): summarised as first, last, min, max and percentile with their rows.
  Anchor a first or last value to the row given; don't anchor to a row the digest didn't show you.
- Tab names with spaces are written as they are: `Short Check!C9`, `Px Events!F31`.

## 5. quotes
`{"id": "q1", "text": "...", "file": "<path relative to the research root>", "line": 214}`.
- `text` must appear verbatim on that one line of that file (spaces may differ; case and punctuation may not). Quote
  a phrase or a sentence, not a paragraph; at most 400 characters. Never fix a transcript's grammar.
- Find the line with Grep after you have read the passage. Prefer the Markdown copy (`_md/`) of a document.
- Slides name quotes by id in their `quotes` list. Every id used must exist. Say who is speaking and when in the
  slide text or the notes ("CFO, Q3 26 call").

## 6. slides: the ten core slides
Every slide has `type`, `title`, `takeaway`, `notes` (speaker notes: what to say, "Likely question:", "Answer:") and
`source` (the tab, report section or document). The first ten slides are, in this order (common.CORE_TYPES):
`title`, `summary`, `setup`, `thesis`, `risks`, `why_now`, `valuation`, `different`, `risk_reward`, `catalysts`.
Core slides carry no `section`.

| type | Fields beyond the common ones | What code adds |
|---|---|---|
| `title` | `image` (optional): `{"pdf": "<file>", "page": n, "crop": [x0, y0, x1, y1]}`, the crop as fractions of page width and height from the top-left; or `{"png": "<file in the tabs folder>"}`. The `title` carries the call: "LONG XYZ", "SHORT XYZ", "WATCH XYZ". | the picture |
| `summary` | `takeaway`: the 20-second pitch cut to 160 characters; `bullets` (optional, 0-3) | the cap table and our-vs-Street grid from SUM |
| `setup` | `bullets` (3-5): the set-up story; `events` (optional): `[{"date": "YYYY-MM-DD", "label": "..."}]` for the big moves to label | the price chart with Px Events markers |
| `thesis` | `points`: exactly 3 `{"head", "body"}` | |
| `risks` | `risks`: exactly 2 `{"head", "prob", "if_hits", "mitigant"}`, `prob` a number strictly between 0 and 1: your own judgment, not a model number, so it needs no `{key}` or anchor (it is a structured field, not text); `tripwires`: 2-4 strings | each `prob` as a percent labelled "our estimate" |
| `why_now` | `bucket`: the alpha bucket's name (pitch_brief.md section 8); `bullets` (3-5) | |
| `valuation` | `bullets` (2-4) | the P/E history chart from Multiples |
| `different` | `table` (`header`, `rows`): ours vs Street on the key lines; `bullets` (2-4): implied vs ours per key driver | |
| `risk_reward` | `cases`: three entries named `Bull`, `Base`, `Bear`, each `{"name", "eps", "pe", "ret", "prob"}` as `{key}` strings; `ladder`: `"Valuation"` (the R/R ladder by entry price is read from that tab); `irr`: `"{irr_3y}"`; `three_rs`: `{"roll", "revisions", "rerating"}` as `{key}` strings. A short adds `short`: `{"type", "crowding", "borrow", "var_size", "takeout"}`, each a line of text (bullet budget) from Short Check that may hold `{key}`s. `lead` (optional; the Watch call's opening line): the buy price, the no-brainer price and today's 3-year IRR, as text with `{key}`s (bullet budget). | the cases table, the ladder and its chart |
| `catalysts` | `bullets` (3-6): dated events, the next print and the preview's stance, the incremental buyer; `tripwires` (optional) | |

## 7. slides: support and appendix
Every slide after the tenth carries `"section": "support"` or `"section": "appendix"` and a `type` from
common.SUPPORT_LAYOUTS: `text_chart`, `table`, `quote`, `two_column`, `image`, `checklist`. There are 10 to 25 support
slides. Support slides also carry `supports`: `thesis.1`, `thesis.2`, `thesis.3`, `risks.1` or `risks.2` (at least
one support slide for each). Put the support slides before the appendix slides.
| type | Fields |
|---|---|
| `text_chart` | `bullets` (2-5) and `image` (a tab picture `{"png": ...}` or a PDF crop) |
| `table` | `table`: `{"header": [...], "rows": [[...], ...]}`; every cell is a label or a `{key}` |
| `quote` | `quotes`: 1-3 quote ids; `bullets` (optional): what the quotes prove |
| `two_column` | `left` and `right`: each `{"head": "...", "bullets": [...]}` (Likes / Dislikes, bull / bear) |
| `image` | `image` and an optional `caption` |
| `checklist` | `items`: 3-15 `{"q", "a"}`; `q` the question (row budget, 90), `a` a short answer (cell budget): "Yes", "No", "Partly", or a `{key}`. The two appendix checklists use it: the 15-question stock-selection checklist, and the 7-area risk checklist (`q` names the area and gives your one-line answer; `a` is the verdict, e.g. "Low risk", "High risk"). |

## 8. pitch_sheet
- `script_3min`: exactly 12 short paragraphs in the 3-to-5-minute script's order (pitch_brief.md section 10).
- `napkin`: 3-5 bullets.
- `hard_questions`: 3-5 `{"q", "a"}` with your answers. In the first draft (before the PM has run) write the hardest
  questions you expect yourself; after the PM review, replace them with the hardest challenges left standing.
- `know_cold`: 5-10 number keys (each must exist in `numbers`; at most 10 so the sheet stays two pages), at least `price`, `base_ret`, `risk_ret`, `irr_3y`,
  `buy_price` and our vs Street EPS for next year.

## 9. sum_boxes
Keys only from common.SUM_BOXES: `Thesis Summary`, `Trading Plan`, `Valuation Thoughts`, `Buy price`,
`No-brainer price`, `Mgmt contact`. Text boxes are plain sentences with `{key}` numbers; the price boxes are a single
`{key}` (`"{buy_price}"`). `null` means leave the box alone; use `null` for `Mgmt contact` unless the user's notes give
a contact. Code writes a box only if it is empty or still holds what the last run wrote; anything the user typed stays.

## 10. notes
A list of plain-English sentences, one per judgment call: the call and any override, the bucket, each probability,
which multiple or case you leaned on, how you set the buy and no-brainer prices, any number you could not anchor and
left out, any PM challenge you conceded or defended. The user reads these in the report.

## 11. Text budgets
Characters, counted after each `{key}` is replaced by its `shown` (common.BUDGET):
| Budget | Limit | Fields |
|---|---|---|
| title | 70 | every slide `title` |
| takeaway | 160 | every slide `takeaway` |
| bullet | 170 | thesis `head`; risk `head`, `if_hits`, `mitigant`; each item of `bullets` and `tripwires`; each `napkin` item; each `hard_questions` `q`; two_column `head`s and `bullets`; `caption`; `bucket`; risk_reward `lead` and each `short` field |
| box | 420 | thesis `body`; `most_important_thing`; `pitch_20s`; each `script_3min` paragraph; each `hard_questions` `a`; each text value of `sum_boxes` |
| note | 1500 | every slide `notes` |
| quote | 400 | each quote `text` |
| row | 90 | each checklist `q` (15 rows must fit one slide) |
| cell | 24 | each table `header` and `rows` cell; each risk_reward case field; `irr`; each `three_rs` field; each checklist `a` |

## 12. Every rule the code enforces
Every problem line `plan.py` sends you starts with the id of the rule it breaks (`[R7] slide 12 (table): ...`). This
list is exactly what it checks; the rest of this page is how to write a good plan, which the PM checks instead.

Structure (`plan.py`):
- **[R1]** The file is valid JSON holding one object.
- **[R2]** `call` is one of `Long`, `Short`, `Watch`.
- **[R3]** `numbers` is a non-empty object holding every required key: `price`, `base_ret`, `risk_ret`, `irr_3y`,
  `target_3y`, `buy_price`, `nobrainer_price`.
- **[R4]** Every number key is lower-case letters, digits and `_`; every entry is an object with a finite numeric
  `value`, a non-empty `shown` and a non-empty `anchor`.
- **[R5]** `slides` is a list whose first 10 are the core types in order: `title`, `summary`, `setup`, `thesis`,
  `risks`, `why_now`, `valuation`, `different`, `risk_reward`, `catalysts`.
- **[R6]** Every later slide has `section` `support` or `appendix` and a `type` in `text_chart`, `table`, `quote`,
  `two_column`, `image`, `checklist`.
- **[R7]** Every slide is an object with non-empty `title`, `takeaway`, `notes` and `source`.
- **[R8]** Counts and shapes by slide type. `bullets`: `summary` 0-3; `setup` and `why_now` 3-5; `valuation`
  and `different` 2-4; `catalysts` 3-6; `text_chart` 2-5. `tripwires`: `risks` 2-4; `catalysts` 0-4. `bullets` and
  `tripwires` are lists of non-empty strings; `caption`, `bucket`, `lead` and `irr` are text. A `quote` slide names 1-3 quote ids. A `two_column` slide's `left` and
  `right` are each an object with a non-empty `head` and a `bullets` list. A `checklist` slide has 3-15 `items`, a list
  of objects with non-empty `q` and `a`. A `table` is an object with a non-empty `header` list and a `rows` list whose
  rows are lists. An `image` is an object with `png` or `pdf`. `events` is a list of objects, each with a `date`
  (`YYYY-MM-DD`) and a non-empty `label`. A field's shape is checked on any slide that carries it (the builders print
  it wherever it is); the counts belong to the slide type.
- **[R9]** `thesis` has exactly 3 `points`, a list of objects with non-empty `head` and `body`.
- **[R10]** `risks` has exactly 2 `risks`, a list of objects with non-empty `head`, `if_hits` and `mitigant`, and a
  `prob` that is a number strictly between 0 and 1.
- **[R11]** `risk_reward` has `cases`, a list of objects with non-empty `name`, `eps`, `pe`, `ret` and `prob`, named
  `Bull`, `Base` and `Bear` (case ignored); `three_rs` is an object with non-empty `roll`, `revisions` and
  `rerating`; `short`, if present, is an object.
- **[R12]** There are 10 to 25 slides with `section` `support`; each has `supports` set to `thesis.1`, `thesis.2`,
  `thesis.3`, `risks.1` or `risks.2`; each of those five is supported at least once.
- **[R13]** Every `{key}` written in `action`, `pitch_20s`, `most_important_thing`, `override`, `hurdle_override`, any slide field,
  `pitch_sheet`, `sum_boxes` or `notes` exists in `numbers`.
- **[R14]** No typed numbers in the budgeted text fields (section 11; quote `text` is exempt), nor in `action` or the
  `reason` and `evidence` of `override` and `hurdle_override`. How the check works: it takes out the `{key}`s, splits
  the text on spaces, trims surrounding punctuation from each word, and flags a word that starts with a digit (after
  any sign or currency): `$72.40`, `15%`, `12x`, `40bps`, `$1.2bn`, `31m`, `5k`, `1,250`, and a plain `40` or `4`.
  Labels pass: years (`2027`, `2027E`, `2025-27`), quarter, half and fiscal labels (`Q3 26`, `3Q26`, `1H26`,
  `FY 27`), filings (`10-K`), dates (`2026-02-03`, `March 3`, `12 May`), a number after slide, step, section or page,
  and any word that starts with a letter (`Q3`, `FY27`, `Valuation!F20`). Write counts in words ("three thesis
  points"). `risks[].prob` is a structured field, not text, so it is not scanned.
- **[R15]** `quotes` is a list of objects, each with `id`, `text`, `file` and a whole-number `line`; a slide's
  `quotes` is a list of ids, and every id it names exists in `quotes`.
- **[R16]** Every text field is within its budget (section 11), counted after each `{key}` is replaced by its `shown`.
- **[R17]** `pitch_sheet` is an object whose four fields are lists: `script_3min` exactly 12 paragraphs and `napkin`
  3-5 bullets, each non-empty text; `hard_questions` 3-5 objects with non-empty `q` and `a`; every `know_cold` key
  exists in `numbers`, and `know_cold` includes `price`, `base_ret`, `risk_ret`, `irr_3y` and `buy_price`; at most 10
  keys.
- **[R18]** `sum_boxes`, if present, is an object whose keys are among the six SUM box names and whose values are text
  or `null`; `Buy price` and `No-brainer price` are a single `{key}`; no text starts with `=` or holds control
  characters.
- **[R19]** The call against the verdicts (the skill reads them from the tabs; failing that, `starting_verdicts`;
  case and surrounding spaces ignored). A Valuation verdict that is not empty and not Buy, Hold or Sell is a problem
  (fix the cell). If the Valuation verdict is Buy, Sell or Hold, a call other than its mapping (Buy → Long,
  Sell → Short, Hold → Watch) needs `override` with a non-empty `reason` and `evidence`. `Short` needs the short
  verdict `alpha short`, override or not; with no Short Check tab a Short is impossible.
- **[R20]** A `Long` needs numeric `irr_3y`, `base_ret` and `risk_ret`, and must clear both the IRR hurdle and the
  buy R/R: if `irr_3y` is below the IRR hurdle *or* `base_ret` / |`risk_ret`| is below the buy R/R, it needs
  `hurdle_override` with a non-empty `reason` and `evidence`, or the call `Watch` (`override` does not waive it). A
  `risk_ret` of 0 counts as infinite R/R when `base_ret` is above 0, and as missing the R/R when it is not. A `Long`
  also fails while any of `irr_3y`, `base_ret`, `risk_ret`, `target_3y`, `buy_price` or `nobrainer_price` failed its
  anchor check (the skill passes anchors.py's problems in). The hurdles are the Valuation tab's "IRR hurdle" and "Buy
  at R/R" inputs; when the tab has none, common.HURDLES: 20% 3-year IRR, 2:1 to buy, 3:1 to pound the table.
- **[R21]** On a `Long`, an `action` containing "pound" needs `base_ret` / |`risk_ret`| at or above the pound R/R (the
  Valuation tab's "Table-pound at R/R", default 3:1).
- **[R22]** `ticker`, `as_of`, `action`, `most_important_thing` and `pitch_20s` are non-empty text; `notes`, if
  present, is a list of sentences.
- **[R23]** `buy_price` is `target_3y` / (1 + IRR hurdle)^3 and `nobrainer_price` is `target_3y` / (1 + 30%)^3, within
  0.5% or the rounding `shown` implies, whichever is wider; the IRR hurdle is the one R20 uses.

Truth (`anchors.py`; the skill runs it before `plan.py` and passes its problems to R20):
- **[A1]** A `Tab!Cell` anchor's value equals the recalculated cell at the rounding `shown` implies.
- **[A2]** A `file:line` anchor's `shown` number is printed on that line of that file (path relative to the research
  root), with the shown unit next to it and no sign the words contradict (section 3).
- **[A3]** A `calc:` anchor evaluates, over the other keys' values, to `value` at the shown rounding; only names,
  numbers, `+ - * / ^ ( )`, `abs`, `min`, `max`; it uses at least one key, and none of its keys failed.
- **[A4]** A quote's `text` is verbatim on its `line` of its `file`.
- **[A5]** Two keys with the same anchor have the same `shown`.

Problems come back to you as one line each; fix every one. A number still failing after two rounds is printed as
UNVERIFIED in the speaker notes and the report, so anchor carefully the first time.
