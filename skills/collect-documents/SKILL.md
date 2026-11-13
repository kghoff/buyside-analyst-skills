---
name: collect-documents
description: Collect every raw research document for a public company into one local folder (the first step of any company work-up: collect every raw document before reading any of them): 10 years of 10-Ks, 10 years of 10-Qs (the same fiscal years as the 10-Ks, plus the current year), earnings press releases, earnings call transcripts, investor decks, investor event transcripts, segment recasts and 10 years of annual proxy statements (DEF 14A), saved as PDF + Markdown; also files and converts the sell-side research PDFs the user drops into the ticker's Sellside Research folder. Use when the user runs /collect-documents TICKER or asks to gather/batch all filings and transcripts for a ticker.
argument-hint: TICKER [--out DIR]
---

# /collect-documents

```bash
SK="<this skill's base directory>/scripts"      # the base directory is shown when the skill loads
SKILLS="<this skill's base directory>/.."
RD=$(python3 "$SKILLS/../lib/settings.py" research_dir)   # your research folder: research_dir in the settings file
```
Skills and agents are named here without a prefix. Installed as a plugin, Claude Code lists them as
`buyside:<name>` (e.g. skill `buyside:model-historicals`, agent `buyside:filings-analyst`): use the name as listed.

Arguments: `$ARGUMENTS` (a ticker, optionally followed by `--out DIR`; default output root is `$RD`, the `research_dir` in your settings file (your Desktop's Research folder unless you changed it)).

## Step 1: Run the script (SEC + Alpha Vantage)

If `"$SKILLS/collect-documents/node_modules"` is missing, first run `npm install --prefix "$SKILLS/collect-documents"`.

```bash
node "$SKILLS/collect-documents/scripts/gather.mjs" $ARGUMENTS
```

Run it with the maximum Bash timeout (600000 ms). If it times out, rerun the identical command; it resumes from the manifest. If it exits non-zero, show the user the error and STOP; don't dispatch the agent.

File names put the fiscal year first (`DXCM 2024 Q1 10-Q`, `2024 Q1 DXCM release 2024-05-01`) so every folder sorts by date. The script renames any folder gathered with the old quarter-first names (`Q1 24 ...`) before it starts; to rename one without a rerun: `node "$SKILLS/collect-documents/scripts/relabel.mjs" <DIR>`.

Proxy statements: one annual DEF 14A per 10-K, labeled with the fiscal year it reports on (`DXCM 2024 proxy filed 2025-03-27`, the proxy that follows the FY2024 10-K). Special-meeting proxies, extra soliciting material (DEFA14A) and preliminary drafts (PRE 14A) are not collected (house default). A `proxy:` gap for the newest year usually just means it isn't filed yet; a rerun picks it up.

The first line of output is `TICKER → DIR`. Take DIR from that line; never build the path yourself.

## Step 2: Read the manifest

Read `DIR/_manifest.json`. Note:
- the company name
- the 12-quarter window (the quarters with a `call:` entry)
- the open script gaps: `pr:*` and `deck:*` ids with status `missing`
- the existing `agent:*` entries (a previous IR agent pass)

## Step 3: Dispatch the IR agent

If there are `agent:*` entries AND no open `pr:`/`deck:` gaps, skip this step and say in the report that a previous IR pass exists and no script gaps are open.

Otherwise dispatch ONE `general-purpose` agent with the prompt below, filling in the bracketed values.

> You are completing a buy-side research folder for {COMPANY} ({TICKER}) at `{DIR}`. SEC filings and Alpha Vantage transcripts are already there; don't touch them. Your job is the material that's only on the company's investor relations (IR) site or the web, for fiscal quarters {OLDEST_QUARTER} through {NEWEST_QUARTER}:
>
> 1. **Open gaps** the SEC didn't have: {OPEN_GAP_IDS_WITH_LABELS}. `pr:` ids are earnings press releases (save into `Press Releases/`), `deck:` ids are quarterly earnings decks (save into `Investor Decks/`). Fill each one with THAT SAME id (`--status found` plus its files), named like the gap's label, which puts the fiscal year first (e.g. `2024 Q3 {TICKER} deck.pdf`), or leave it alone if you can't find it.
> 2. **Investor events** in the window: investor/analyst days, capital markets days, product/strategy events, and major conference presentations by the CEO/CFO. For each, save a transcript if one is published (IR site, or a company-hosted page). If there's none, save the slides. If it's video only, register it as `missing` with the video URL and reason "video only, no transcript". Save into `Investor Events/` named like `2024-06-13 {TICKER} Investor Day.pdf`, with id `agent:event-YYYY-MM-DD-<slug>`.
> 3. **Segment recasts / reconciliations**: when the company re-segmented or published historical recast or reconciliation tables (often under "other documents", "financial information" or as an 8-K exhibit linked from IR). Save into `Segment Recasts/`, named with the date first (`2024-06-13 {TICKER} segment recast.pdf`).
>
> Already registered by a previous pass; don't redo these: {EXISTING_AGENT_IDS_OR_NONE}.
>
> How to save:
> - PDFs: `curl -L -A "Mozilla/5.0" -o "{DIR}/<Category>/<name>.pdf" "<url>"`. If `file` doesn't report a PDF, delete the file and register the item `missing` with the reason.
> - HTML pages (e.g. transcripts): save the HTML to a temp file, then `node "$SKILLS/collect-documents/scripts/convert.mjs" page.html "{DIR}/<Category>/_md/<name>.md"` and `node "$SKILLS/collect-documents/scripts/render.mjs" page.html "{DIR}/<Category>/<name>.pdf"`. Markdown copies always go in the category's `_md/` subfolder. Never type out document text yourself.
> - Register EVERY item you save or fail to find:
>   `node "$SKILLS/collect-documents/scripts/manifest.mjs" add "{DIR}" --id "<id>" --category "<Category>" --label "<name>" --status found|missing --url "<source url>" --file "<Category>/<name>.pdf" [--file "<Category>/_md/<name>.md"] [--reason "<why missing>"]`
> - Always register exactly one summary entry per category you searched: `--id agent:searched-events` (category `Investor Events`) and `--id agent:searched-recasts` (category `Segment Recasts`), with `--status skipped --reason "searched <where>; found N"`.
>
> Rules:
> - Every name starts with its year: `YYYY Qn ...` for a fiscal quarter, `YYYY-MM-DD ...` for a dated event, never `Q3 24 ...`, so each folder sorts by date.
> - Only save content you actually fetched. Never write a transcript or summary from memory.
> - Don't get around paywalls or logins. If something needs one, register it `missing` with the reason.
> - Never overwrite existing files.
> - Stop after about 40 items or 30 minutes.
> - Finish with a short list of what you found and what you couldn't.

## Step 4: File sell-side research

Sell-side reports sit behind the user's own logins (reports the user has access to through brokerage accounts or research subscriptions), so the skill never downloads them. The user drops the PDFs into `DIR/Sellside Research/` (the script creates the folder), and this step files them. Never fetch these reports yourself, and never get around a login or paywall.

1. `node "$SKILLS/collect-documents/scripts/inbox.mjs" pending "DIR" sellside` lists the PDFs not yet registered, with page count, PDF title and first-page text. If the list is empty, skip to step 5.
   The user also drops web pieces here (Seeking Alpha, newsletters, fund letters, news and trade press printed to PDF). They are filed the same way, by tier. A non-research reference document (a guide, a cheat sheet) is not a report: leave it out of the plan and tell the user.
2. From each report's first page decide, and write to a temp `plan.json` as `[{"file", "date", "firm", "type", "title", "tier"}]`:
   - `file`: exactly as `pending` printed it (it may include a tier folder).
   - `date`: the report's own publication date (YYYY-MM-DD), not the download or print date.
   - `firm`: short name: JPM, Morgan Stanley, BofA, Goldman Sachs, William Blair, Morningstar, CFRA, Argus, Schwab, LSEG StarMine, SmartConsensus; for web pieces the outlet: Seeking Alpha, MD+DI, HME News, Reuters...
   - `type`, one of: `initiation`, `deep dive`, `industry`, `preview`, `flash note`, `earnings recap`, `rating change`, `event takeaways`, `survey`, `company report` (a standing full report such as Morningstar's or CFRA's), `quant rating` (a model-generated rating page: Schwab Equity Ratings, LSEG StarMine, Argus A6, SmartConsensus), `article` (an analysis or opinion piece: Seeking Alpha, Substack, newsletter), `investor letter`, `short report`, `news`.
   - `title`: the headline as printed (blank for a quant rating with none). If you can't identify the firm or date from the first page, read more of the PDF before guessing.
   - `tier`: leave it out for firms ranked in the `FIRM_TIERS` list in `scripts/inbox.mjs` (the script knows them). Otherwise give it: `1` broker research (banks, research brokers, industry specialists), `2` independent research (rating shops, quant ratings), `3` independent analysis (Seeking Alpha, Substack, newsletters, fund/investor letters, short sellers, university student funds), `4` news and trade press.
3. `node "$SKILLS/collect-documents/scripts/inbox.mjs" register "DIR" sellside plan.json` renames each to `<date> <firm> <type> - <title>.pdf` (so each folder sorts by date), moves it into its tier folder (`1 Broker Research`, `2 Independent Research`, `3 Independent Analysis`, `4 News and Trade Press`), registers it with its tier, and records the original file name. It checks the whole plan first and renames nothing if any entry is wrong. Reports filed before tiers existed (still at the folder root) move with `inbox.mjs tidy "DIR" sellside`.
4. Step 5 converts them: registered reports show up in `slides.mjs pending` like decks. Use the report prompt below (not the slide prompt) for `Sellside Research` items. Their Markdown also gets a dropped-text check against the PDF's text layer; `finish` prints `thinPages` for pages that may have lost text. Look at those pages before reporting; after fixing one by hand, `node "$SKILLS/collect-documents/scripts/slides.mjs" recheck "DIR" "<id>"` redoes the check.

Report prompt:

> Convert sell-side research report pages to Markdown for a buy-side analyst. For each page number in {PAGES} of the report in `{WORK}`: Read the image `page-NNN.png` (NNN = 3-digit page number) AND the text file `page-NNN.txt` (the part before `----- OCR -----` is the PDF's own text layer; the OCR parts are only for numbers inside pictures). Write `page-NNN.md` in the same folder. Skip pages whose `.md` already exists. Do not write anything else. Read every page yourself; never copy one page's Markdown to make another.
>
> What to write for each page:
> - Prose: copy the wording from the text layer exactly. Never paraphrase, shorten or summarize. Rejoin lines broken mid-sentence and words hyphenated across lines. Use the image for reading order (in multi-column layouts read each column top to bottom, sidebar after the main text), headings (`##` / `###`), bullets and bold.
> - Tables (estimates, financial summaries, valuation, key data): Markdown tables with every row and column, numbers exactly as printed (keep $, %, parentheses, units, and estimate markers such as 2027E).
> - Charts: a line `Chart: <chart title> (<units>)`, then a Markdown table of the data labels printed on the chart. Only printed labels: never estimate a value from bar heights or axes; write "not labeled" where there is no label. Skip axis tick values.
> - Rating / price-target / key-data boxes: a small table or list, as printed.
> - The analyst block on the cover (names, titles, firm, phone, email): keep it, as printed. Running headers, footers and page numbers on later pages: skip.
> - A page that is only legal disclosures, analyst certification, rating definitions or ratings-distribution text: write exactly `[Disclosures page: legal text not converted; see the PDF]` and nothing else. If such a page also has a rating / price-target history table or chart, convert that table or chart, skip the legal text, and end the page with the line `[Legal text not converted; see the PDF]`. Methodology text (how a score or rating is built) is not legal text: convert it.
> - Photos or logos with no data: one line `[Image: short description]`.
> - Web pages printed to PDF: skip site navigation, ads, cookie notices and related-article lists; write only the article, and end the page with the line `[Legal text not converted; see the PDF]` if you skipped anything.
> - Don't add commentary, summaries or any number you calculated.
>
> Finish by listing the pages you wrote.

## Step 5: Convert slide decks and reports to Markdown

Earnings decks and investor event slides are PDFs whose charts and tables are often pictures. Claude reads each slide image and writes it as Markdown; a script checks every number against the slide's own text + OCR. Needs `pdftoppm`/`pdftotext` (`brew install poppler`) and `tesseract` (`brew install tesseract`).

1. `node "$SKILLS/collect-documents/scripts/slides.mjs" pending "DIR"` lists the decks without a Markdown copy (reruns skip converted ones). If the list is empty, skip this step.
2. For each deck: `node "$SKILLS/collect-documents/scripts/slides.mjs" prep "DIR" "<id>"` (renders `page-NNN.png` + `page-NNN.txt` into its `work` folder; prints `pages` and `toRead`, the pages that aren't blank: only those need reading). Use a 600000 ms timeout; rerun if it times out (it resumes).
3. Split the slides into batches of at most 25 (one deck can be several batches; small decks can share a batch). Dispatch `general-purpose` agents with `model: sonnet`, at most 5 at a time, each with the prompt below.
4. When a deck's batches are all back: `node "$SKILLS/collect-documents/scripts/slides.mjs" finish "DIR" "<id>"`. It refuses if any slide is unwritten; dispatch an agent for the missing pages and finish again. It writes `<Category>/_md/<name>.md`, adds it to the manifest and deletes the work folder. Note each deck's `unconfirmed` count for the report.

> Convert slide images to Markdown for a buy-side model. For each page number in {PAGES} of the deck in `{WORK}`: Read the image `page-NNN.png` (NNN = 3-digit page number), and write `page-NNN.md` in the same folder. Skip pages whose `.md` already exists. Do not write anything else. Read every page image yourself; never copy one page's Markdown to make another, even if they look alike.
>
> What to write for each slide:
> - Every word and number printed on the slide, in reading order. The slide title as `### Title`.
> - Tables (reconciliations, guidance, segment data) as Markdown tables, every row and column, numbers exactly as printed (keep $, %, parentheses, units such as "($MM)"). If two tables sit side by side, write them as two separate tables.
> - Charts: a line `Chart: <chart title> (<units>)`, then a Markdown table of the data labels printed on the chart, by category or period (e.g. `| Quarter | Revenue | Organic growth |`). Only printed labels: never estimate a value from bar heights or axes; write "not labeled" if a bar or point has no label. Skip axis tick values.
> - Footnotes and source notes, as printed.
> - Photos, logos, diagrams with no data: one line `[Image: short description]`.
> - Don't add a slide-number heading, commentary, summaries or any number you calculated.
>
> Finish by listing the pages you wrote.

## Step 6: Report

Run `node "$SKILLS/collect-documents/scripts/manifest.mjs" render <DIR>`. Then tell the user:
- the folder path
- counts by category
- every gap (missing/deferred) by name with its reason
- slide decks converted, and each one with unconfirmed numbers (count), which the user should spot-check against the PDF
- sell-side reports filed (firm, date, type), and any page flagged for possibly dropped text
- if any transcripts are `deferred`, that rerunning `/collect-documents TICKER` later will finish them (reruns only fetch what's missing)

Never say "done" while hiding a gap.
