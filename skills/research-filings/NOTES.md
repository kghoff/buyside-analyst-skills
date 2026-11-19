# research-filings: why things are the way they are

## numcheck: a bare label is a citation, 2026-11-18
- numcheck used to keep only bracket texts with a comma (`[DXCM 2025 10-K, Item 7]`). A transcript has no pages, so
  research-street agents cite peer calls bare (`[2026 Q3 DXCM call]`); every quote in such a sentence was reported
  "cites nothing". A comma-free bracket now counts when it is exactly a known source label; editorial brackets
  (`move[s]`) still don't.

## render.py `--outside-labels`, 2026-11-18
- Footnote colour comes from the label's shape. A peer's own call has a company-document shape, so the caller
  (research-street) lists such labels and they print purple, as outside views.
