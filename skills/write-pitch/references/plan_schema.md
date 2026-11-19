# pitch_plan.json: the contract

The analyst writes `pitch_plan.json`; code checks it (`plan.py` for structure, `anchors.py` for truth) and builds the
decks, the pitch sheet, the Markdown copy and the SUM boxes from it. Anything that breaks a rule below comes back to
you as a problem to fix. The values used in the checks (slide types, layouts, text budgets, SUM boxes, hurdles, calls)
live in the skill's `scripts/common.py`; this page repeats them so you don't need to open it.

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
  "starting_verdicts": {"valuation": "Buy", "short": "no short"},
  "override": null,
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
     "notes": "...", "source": "..."}
  ],
  "pitch_sheet": {"script_3min": ["12 short paragraphs, chapter 3's steps"], "napkin": ["3-5 bullets"],
                  "hard_questions": [{"q": "...", "a": "..."}], "know_cold": ["price", "base_ret", "irr_3y"]},
  "sum_boxes": {"Thesis Summary": "...", "Trading Plan": "...", "Valuation Thoughts": "...",
                "Buy price": "{buy_price}", "No-brainer price": "{nobrainer_price}", "Mgmt contact": null},
  "notes": ["every judgment call, plain English"]
}
```
The example is cut down: a real plan has all ten core slides, three risk_reward cases, 10-25 support slides and the
appendix slides `pitch_brief.md` section 3 lists.

## 2. Top-level fields
| Field | What goes in it |
|---|---|
| `ticker` | The ticker, upper case. |
| `as_of` | Today's date, `YYYY-MM-DD`. |
| `call` | One of `Long`, `Short`, `Watch` (common.CALLS). |
| `action` | The size of the conviction in a few words: "Small buy", "Buy", "Pound the table", "Short", "Wait for {buy_price}". |
| `starting_verdicts` | `valuation`: the Valuation tab's verdict as the tab shows it (`Buy`, `Hold`, `Sell`). `short`: the Short Check tab's verdict in lower case (`alpha short`, `filler short`, `watchlist`, `no short`), or `null` when there is no Short Check tab. |
| `override` | `null` when `call` follows the mapping (Buy → Long, Sell → Short, Hold → Watch). Otherwise `{"reason": "...", "evidence": "..."}`; `evidence` cites `file:line` or `Tab!Cell`. |
| `most_important_thing` | One sentence: the differentiated view on where a number in the statements is heading. |
| `pitch_20s` | The 20-second pitch: position, why mispriced, what's changing, the number that matters, the valuation gap, the ask. |
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
- **Anchors**, three forms:
  1. `Tab!Cell`, e.g. `Valuation!F20`, `SUM!J12`, `MOD!H45`: a cell in the model. `value` must equal the
     recalculated cell at the rounding `shown` implies. Use the cell that holds the number, not one that links to it,
     when both exist; either passes if the values match.
  2. `file:line`, e.g. `Earnings Calls/_md/2026 Q3 XYZ call.md:214`: a line in a research file. The path is relative
     to the research root (the folder `<research_dir>/<TICKER>/` the assignment names). The
     `shown` number must be printed on that line (`$`, `,`, `%`, `x` and parentheses for negatives are allowed to
     differ). Use it for numbers the model doesn't hold: guidance, a market size, a sell-side estimate, a number from
     the user's notes (file `Pitch/_work/user_notes.md`).
  3. `calc: <expression>`, e.g. `calc: (target_3y/price)^(1/3)-1`, `calc: target_3y/1.2^3`: arithmetic over other
     keys. Allowed: key names, numbers, `+ - * / ^ ( )`, `abs`, `min`, `max`. The result must equal `value` at the
     shown rounding. Every key it uses must itself be anchored (no circles).
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
| `summary` | `bullets` (optional, 3-5) | the cap table and our-vs-Street grid from SUM |
| `setup` | `bullets` (3-5): the set-up story; `events` (optional): `[{"date": "YYYY-MM-DD", "label": "..."}]` for the big moves to label | the price chart with Px Events markers |
| `thesis` | `points`: exactly 3 `{"head", "body"}` | |
| `risks` | `risks`: exactly 2 `{"head", "prob", "if_hits", "mitigant"}`, `prob` a number strictly between 0 and 1; `tripwires`: 2-4 strings | |
| `why_now` | `bucket`: the alpha bucket's name (pitch_brief.md section 8); `bullets` (3-5) | |
| `valuation` | `bullets` (2-4) | the P/E history chart from Multiples |
| `different` | `table` (`header`, `rows`): ours vs Street on the key lines; `bullets` (2-4): implied vs ours per key driver | |
| `risk_reward` | `cases`: three entries named `Bull`, `Base`, `Bear`, each `{"name", "eps", "pe", "ret", "prob"}` as `{key}` strings; `ladder`: `"Valuation"` (the R/R ladder by entry price is read from that tab); `irr`: `"{irr_3y}"`; `three_rs`: `{"roll", "revisions", "rerating"}` as `{key}` strings. A short adds `short`: `{"type", "crowding", "borrow", "var_size", "takeout"}` from Short Check. | the cases table, the ladder and its chart |
| `catalysts` | `bullets` (3-6): dated events, the next print and the preview's stance, the incremental buyer; `tripwires` (optional) | |

## 7. slides: support and appendix
Every slide after the tenth carries `"section": "support"` or `"section": "appendix"` and a `type` from
common.SUPPORT_LAYOUTS: `text_chart`, `table`, `quote`, `two_column`, `image`. Support slides also carry `supports`:
`thesis.1`, `thesis.2`, `thesis.3`, `risks.1` or `risks.2` (at least one support slide for each).
| type | Fields |
|---|---|
| `text_chart` | `bullets` (2-5) and `image` (a tab picture `{"png": ...}` or a PDF crop) |
| `table` | `table`: `{"header": [...], "rows": [[...], ...]}`; every cell is a label or a `{key}` |
| `quote` | `quotes`: 1-3 quote ids; `bullets` (optional): what the quotes prove |
| `two_column` | `left` and `right`: each `{"head": "...", "bullets": [...]}` (Likes / Dislikes, bull / bear) |
| `image` | `image` and an optional `caption` |

## 8. pitch_sheet
- `script_3min`: exactly 12 short paragraphs in the 3-to-5-minute script's order (pitch_brief.md section 10).
- `napkin`: 3-5 bullets.
- `hard_questions`: 3-5 `{"q", "a"}`, the hardest from the PM review, with your answers.
- `know_cold`: number keys (each must exist in `numbers`), at least `price`, `base_ret`, `risk_ret`, `irr_3y`,
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
| bullet | 170 | thesis `head`; risk `head`, `if_hits`, `mitigant`; each item of `bullets` and `tripwires`; each `napkin` item; each `hard_questions` `q`; two_column `head`s; `caption`; `bucket` |
| box | 420 | thesis `body`; `most_important_thing`; `pitch_20s`; each `script_3min` paragraph; each `hard_questions` `a`; each text value of `sum_boxes` |
| note | 1500 | every slide `notes` |
| quote | 400 | each quote `text` |
| cell | 24 | each table `header` and `rows` cell; each risk_reward case field |

## 12. Every rule the code enforces
Structure (`plan.py`):
1. `call` is one of `Long`, `Short`, `Watch`.
2. The first 10 slides are the core types in order: `title`, `summary`, `setup`, `thesis`, `risks`, `why_now`,
   `valuation`, `different`, `risk_reward`, `catalysts`.
3. Every later slide has `section` `support` or `appendix` and a `type` in `text_chart`, `table`, `quote`,
   `two_column`, `image`.
4. `thesis` has exactly 3 points; `risks` exactly 2 risks, each `prob` strictly between 0 and 1.
5. `risk_reward` has `Bull`, `Base` and `Bear` cases.
6. Every `{key}` used anywhere exists in `numbers`; text has no typed numbers in their place.
7. Every quote id a slide names exists in `quotes`.
8. Every slide has non-empty `notes` and `source`.
9. `pitch_sheet.hard_questions` has 3-5 items.
10. `sum_boxes` keys are a subset of the six SUM box names.
11. Every text field is within its budget (section 11).
12. The call against the verdicts: Buy → Long, Sell → Short, Hold → Watch; any other call needs `override` with a
    non-empty `reason` and `evidence`. `Short` needs the short verdict `alpha short`. A `Long` whose `irr_3y` is below
    20% *and* whose `base_ret` / |`risk_ret`| is below 2.0 needs `override` or the call `Watch` (common.HURDLES:
    2:1 to buy, 3:1 to pound the table, 20% 3-year IRR).

Truth (`anchors.py`):
13. A `Tab!Cell` anchor's value equals the recalculated cell at the rounding `shown` implies.
14. A `file:line` anchor's `shown` number is printed on that line of that file (path relative to the research root).
15. A `calc:` anchor evaluates, over the other keys' values, to `value` at the shown rounding; only names, numbers,
    `+ - * / ^ ( )`, `abs`, `min`, `max`.
16. A quote's `text` is verbatim on its `line` of its `file`.
17. Two keys with the same anchor have the same `shown`.

Problems come back to you as one line each; fix every one. A number still failing after two rounds is printed as
UNVERIFIED in the speaker notes and the report, so anchor carefully the first time.
