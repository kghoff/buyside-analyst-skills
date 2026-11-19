# collect-documents: why things are the way they are

## Targeted fetch (`--only` / `--quarters`, `peer_docs.mjs`), 2026-11-18
- Other skills' agents need a few of a competitor's documents (a call, a 10-Q). The research agents have no shell by
  design, so they write `doc_requests.txt` and the main agent runs `peer_docs.mjs`. Agents never fetch.
- It reuses gather.mjs, not a second fetcher, so names, `_md/` copies and manifest ids match a full run and a later
  `/collect-documents PEER` skips what was fetched. `only.mjs` filters `selectFilings`' output; the steps are unchanged.
- A targeted run never writes the `pr:` / `deck:` gap placeholders: in the manifest a gap means "tried and failed",
  and a targeted run didn't try the other quarters.
- Local first: a document `found` with its files on disk is reported `local` and not fetched. Any run still rewrites
  `_manifest.json`'s `updated_at`; nothing else changes (checked on DXCM, 2026-11-18).
- `lastN` counts back from the peer's own fiscal window (`sel.window`), not the calendar.
- No gather-level test drives the real steps (they need SEC and Alpha Vantage); the logic lives in pure `only.mjs` and
  `peer_docs.mjs` functions, which are tested, and the gather wiring was checked by hand on DXCM.
