# Checker prompt (filings-analyst, model sonnet)

Read `{WORK}/numcheck.md`. It has four lists: unconfirmed, weak, uncited and bad citations. For every number on
them, find the sentence in `{PHASE}/sections/*.md` (search for the quoted text), open the cited source and check:
- a document citation: open its ORIGINAL markdown ({SOURCE_PATHS_NOTE}) at the cited section
- `[Model, MOD!<cell>]`: find that cell in the `source` column of `{WORK}/series.csv`
- Calc: the number must appear in `{WORK}/drivers_math.md`
Then:
- if the number is right but the citation is wrong or missing, fix the citation (Edit). Model numbers are cited by
  cell, e.g. `[Model, MOD!H61]`
- if the number is wrong, correct it from the source and keep the citation
- if it is the skill's own arithmetic, mark it Calc only if it appears in `{WORK}/drivers_math.md`; otherwise
  rewrite it as an explicit equation with its cited inputs shown
- a weak number (a small number with no nearby anchor in the source): open the cited section; confirm it or fix
  it. If it is confirmed, leave it as it is
- if you can't confirm it, append ` [unconfirmed]` after the number
For every bad citation (a document the filings research never read, or a model citation without a cell), re-source it from a
company document or the model cell, or remove the claim.
Never change a number to match a citation without reading the source. Do no arithmetic beyond checking an equation
already written. Reply with counts: fixed citations, corrected numbers, weak confirmed, marked unconfirmed, removed.

For every quote under "Quotes not found in the cited source": if it is verbatim in another company document, fix the citation; if it is a label or term, drop the quotation marks; if it is a paraphrase, drop the quotation marks or replace it with the real wording. Never invent wording.
