#!/usr/bin/env node
// /collect-documents entry point. Pulls SEC filings, earnings 8-K exhibits and Alpha
// Vantage transcripts for one ticker into <out>/<TICKER>/, tracked in
// _manifest.json. Usage: node gather.mjs TICKER [--out DIR] [--only KINDS --quarters Q]
// --only (calls, 10-Q, 10-K, releases) fetches just those documents for the --quarters asked (default last2):
// the targeted fetch other skills use for a peer's call or filing (see SKILL.md "Targeted fetch").

import { mkdir, writeFile, mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve, dirname, basename } from 'node:path';
import { parseArgs } from 'node:util';
import { secFetch } from './http.mjs';
import { researchDir } from '../../../lib/settings.mjs';
import {
  resolveCik, fetchSubmissions, fetchFiscalTags, selectFilings, fetchExhibits, classifyExhibit, filingUrl,
} from './sec.mjs';
import { cleanEdgarHtml, convertToMarkdown } from './convert.mjs';
import { renderHtmlToPdf, withBaseHref, markdownToHtmlDoc } from './render.mjs';
import { loadAvKeys, createTranscriptFetcher, formatTranscript, isKnownMiss } from './transcripts.mjs';
import {
  loadManifest, saveManifest, setItem, isDone, visibleItems, createClaimer, syncPlaceholder, safeName as safe,
} from './manifest.mjs';
import { shortLabel, quarterKey } from './fiscal.mjs';
import { relabel } from './relabel.mjs';
import { parseOnly, parseQuarters, filterSelection, requestedIds, localStatus } from './only.mjs';

const CATEGORIES = ['10-Ks', '10-Qs', 'Earnings Calls', 'Press Releases', 'Investor Decks', 'Investor Events', 'Segment Recasts', 'Proxy Statements', 'Sellside Research'];

function fail(msg) {
  process.stderr.write(`gather: ${msg}\n`);
  process.exit(1);
}

const { positionals, values } = parseArgs({ allowPositionals: true, options: { out: { type: 'string' }, only: { type: 'string' }, quarters: { type: 'string' } } });
const ticker = (positionals[0] || '').toUpperCase();
if (!ticker) fail('usage: node gather.mjs TICKER [--out DIR] [--only KINDS --quarters Q]');
const targeted = values.only !== undefined || values.quarters !== undefined;
if (targeted && values.only === undefined) fail('--quarters needs --only (calls, 10-Q, 10-K, releases)');
const dir = resolve(values.out || researchDir(), ticker);

try {
  await main();
} catch (e) {
  fail(e?.message ?? String(e));
}

async function main() {
  const company = await resolveCik(ticker);
  if (!company) fail(`unknown ticker "${ticker}": not in SEC company_tickers.json`);
  const since = new Date(Date.now() - 11 * 365.25 * 86_400_000).toISOString().slice(0, 10);
  const sub = await fetchSubmissions(company.cik, since);
  const fiscalTags = await fetchFiscalTags(company.cik);
  let sel = selectFilings({ filings: sub.filings, fiscalTags, fiscalYearEnd: sub.fiscalYearEnd });
  if (sel.tenKs.length === 0) fail(`no 10-K filings for ${ticker} (foreign filers on 20-F are not supported)`);
  if (targeted) sel = filterSelection(sel, parseOnly(values.only), parseQuarters(values.quarters, sel));

  for (const c of CATEGORIES) await mkdir(join(dir, c), { recursive: true });
  relabel(dir); // folders gathered before year-first names
  const manifest = loadManifest(dir);
  Object.assign(manifest, { ticker, cik: company.cik, company: sub.name, fiscalYearEnd: sub.fiscalYearEnd });
  if (fiscalTags.size === 0) {
    const warning = 'no XBRL fiscal tags; quarter labels use period-end math (check labels)';
    process.stderr.write(`gather: WARNING ${warning}\n`);
    manifest.note = warning;
  }
  const tmp = await mkdtemp(join(tmpdir(), 'gather-'));
  const stats = { fetched: 0, skipped: 0 };
  const claim = createClaimer(manifest.items);
  const wanted = targeted ? requestedIds(sel) : [];
  const before = localStatus(manifest, dir, wanted);

  // Run one item unless already complete (default: found with files on disk).
  // Errors become 'missing' and the run continues.
  async function step(id, entry, work, isComplete = (e) => isDone(dir, e)) {
    if (isComplete(manifest.items[id])) { stats.skipped++; return manifest.items[id]; }
    stats.fetched++;
    let result;
    try {
      result = await work();
    } catch (e) {
      result = { status: 'missing', files: [], reason: e.message };
    }
    setItem(manifest, id, { ...entry, by: 'script', ...result });
    saveManifest(dir, manifest);
    return manifest.items[id];
  }

  // Markdown copies live in a `_md/` subfolder so each category folder shows PDFs first.
  async function writeMdAndPdf(base, md, html) {
    const mdPath = join(dirname(base), '_md', `${basename(base)}.md`);
    await mkdir(join(dir, dirname(mdPath)), { recursive: true });
    await writeFile(join(dir, mdPath), md);
    const htmlPath = join(tmp, 'doc.html');
    await writeFile(htmlPath, html);
    try {
      await renderHtmlToPdf(htmlPath, join(dir, `${base}.pdf`));
    } catch (e) {
      return { status: 'missing', files: [mdPath], reason: `PDF render failed: ${e.message}` };
    }
    return { status: 'found', files: [mdPath, `${base}.pdf`] };
  }

  async function saveSecDocument(url, category, label) {
    const base = join(category, safe(label));
    const res = await secFetch(url);
    if (/\.pdf$/i.test(url)) {
      await writeFile(join(dir, `${base}.pdf`), Buffer.from(await res.arrayBuffer()));
      return { status: 'found', files: [`${base}.pdf`], note: 'original is a PDF; no Markdown copy' };
    }
    const html = await res.text();
    const md = `<!-- source: ${url} -->\n\n${convertToMarkdown(cleanEdgarHtml(html))}\n`;
    return writeMdAndPdf(base, md, withBaseHref(html, url));
  }

  async function saveFiling(id, category, label, url) {
    const final = claim(category, label, id, id);
    await step(id, { category, label: final, url }, () => saveSecDocument(url, category, final));
  }

  // 8-K exhibits: press releases + decks (2.02), decks only (7.01). The index
  // entry lists its exhibit ids; it reruns until every one of them is done
  // (done exhibits still skip individually). Returns the categories saved.
  async function save8kExhibits(f, labelFor, keep) {
    const id = `8k:${f.accn}`;
    const indexDone = (e) => e?.status === 'found' && Array.isArray(e.children)
      && e.children.every((c) => isDone(dir, manifest.items[c]));
    const idx = await step(id, { category: '_index', label: `8-K ${f.accn}`, url: filingUrl(company.cik, f) }, async () => {
      const exhibits = (await fetchExhibits(company.cik, f.accn)).filter((ex) => keep(classifyExhibit(ex)));
      const children = [];
      let allFound = true;
      for (const ex of exhibits) {
        const kind = classifyExhibit(ex);
        const category = kind === 'deck' ? 'Investor Decks' : 'Press Releases';
        const docFilename = ex.url.split('/').pop();
        const exId = `ex:${f.accn}:${docFilename}`;
        const label = claim(category, labelFor(kind, ex), exId, docFilename);
        children.push(exId);
        const item = await step(exId, { category, label, url: ex.url }, () => saveSecDocument(ex.url, category, label));
        if (item.status !== 'found') allFound = false;
      }
      return allFound
        ? { status: 'found', files: [], children, note: `${exhibits.length} exhibits` }
        : { status: 'missing', files: [], children, reason: 'one or more exhibits failed' };
    }, indexDone);
    if (!Array.isArray(idx.children)) return null; // index fetch failed; the 8-K itself is the gap
    return new Set(idx.children.map((c) => manifest.items[c]?.category));
  }

  try {
    // 1. Annual and quarterly reports (ids keyed on period end; labels stay fiscal)
    for (const f of sel.tenKs) {
      await saveFiling(`10-K:${f.reportDate}`, '10-Ks', `${ticker} ${f.fy} 10-K`, filingUrl(company.cik, f));
    }
    for (const f of sel.tenQs) {
      await saveFiling(`10-Q:${f.reportDate}`, '10-Qs', `${ticker} ${shortLabel(f)} 10-Q`, filingUrl(company.cik, f));
    }

    // Annual proxies (DEF 14A), one per 10-K, labeled with the fiscal year they report on
    for (const { tenK, proxy } of sel.proxies) {
      const id = `proxy:${tenK.reportDate}`;
      if (proxy) {
        await saveFiling(id, 'Proxy Statements', `${ticker} ${tenK.fy} proxy filed ${proxy.filingDate}`, filingUrl(company.cik, proxy));
      } else {
        syncPlaceholder(manifest, dir, id, false, {
          category: 'Proxy Statements', label: `${ticker} ${tenK.fy} proxy`,
          reason: 'no DEF 14A on EDGAR after this 10-K yet (annual proxies usually follow the 10-K within 4 months)',
        });
      }
    }
    saveManifest(dir, manifest);

    // 2. 8-K exhibits. Names carry the filing date (and exhibit type), so
    // several 2.02 8-Ks in one quarter (e.g. Tesla's deliveries reports) never collide.
    const covered = { 'Press Releases': new Set(), 'Investor Decks': new Set() };
    for (const f of sel.releases) {
      const q = shortLabel(f);
      const cats = await save8kExhibits(f, (kind, ex) => (kind === 'deck'
        ? `${q} ${ticker} deck ${f.filingDate} ${ex.type}`
        : `${q} ${ticker} release ${f.filingDate}${ex.type === 'EX-99.1' ? '' : ` ${ex.type}`}`), () => true);
      // A failed index fetch is already a gap; don't also call the quarter release-less.
      for (const c of cats || ['Press Releases']) covered[c]?.add(quarterKey(f));
    }
    for (const f of sel.regFd) {
      await save8kExhibits(f, (_kind, ex) => `${f.filingDate} ${ticker} deck ${ex.type}`, (kind) => kind === 'deck');
    }
    // Gap placeholders say "tried and failed" for a whole window; a targeted run never makes them.
    for (const q of targeted ? [] : sel.releaseWindow) {
      const key = quarterKey(q);
      syncPlaceholder(manifest, dir, `pr:${key}`, covered['Press Releases'].has(key), {
        category: 'Press Releases', label: `${shortLabel(q)} ${ticker} press release`,
        reason: 'no Item 2.02 8-K on EDGAR for this quarter (may be on the IR site or filed under 7.01/8.01)',
      });
    }
    for (const q of targeted ? [] : sel.window) {
      const key = quarterKey(q);
      syncPlaceholder(manifest, dir, `deck:${key}`, covered['Investor Decks'].has(key), {
        category: 'Investor Decks', label: `${shortLabel(q)} ${ticker} deck`,
        reason: 'no deck filed with the SEC for this quarter; IR agent searches the IR site',
      });
    }
    saveManifest(dir, manifest);

    // 3. Earnings call transcripts
    const fetchTranscript = createTranscriptFetcher(loadAvKeys());
    for (const [i, q] of sel.window.entries()) {
      const label = `${shortLabel(q)} ${ticker} call`;
      const avQuarter = quarterKey(q);
      const id = `call:${avQuarter}`;
      if (isKnownMiss(manifest.items[id], i)) { stats.skipped++; continue; }
      await step(id, {
        category: 'Earnings Calls', label, url: `alphavantage:EARNINGS_CALL_TRANSCRIPT/${ticker}/${avQuarter}`,
      }, async () => {
        const r = await fetchTranscript(ticker, avQuarter);
        if (r.status !== 'found') return { status: r.status, files: [], reason: r.reason };
        const md = formatTranscript(r.data);
        return writeMdAndPdf(join('Earnings Calls', safe(label)), md, markdownToHtmlDoc(label, md));
      });
    }

    for (const f of sel.skipped) {
      setItem(manifest, `skip:${f.accn}`, {
        category: f.form.startsWith('10-K') ? '10-Ks' : '10-Qs', label: `${ticker} ${f.form} filed ${f.filingDate}`,
        status: 'skipped', files: [], url: filingUrl(company.cik, f),
        reason: `${f.form.includes('T') ? 'transition-period report' : 'amendment'}; not collected`, by: 'script',
      });
    }
    saveManifest(dir, manifest);
  } finally {
    await rm(tmp, { recursive: true, force: true });
  }

  // 4. Summary
  const items = visibleItems(manifest);
  const by = (s) => items.filter((e) => e.status === s);
  console.log(`${ticker} → ${dir}`);
  if (targeted) {
    // One line per requested document: found | local (already on disk) | missing | deferred, label → md path.
    const md = (e) => (e?.files || []).find((f) => f.endsWith('.md')) || (e?.files || [])[0] || '';
    for (const id of wanted) {
      const e = manifest.items[id];
      const docs = id.startsWith('8k:') ? (e?.children || []).map((c) => [c, manifest.items[c]]) : [[id, e]];
      if (docs.length === 0) console.log(`missing ${id} →  : ${e?.reason || 'not fetched'}`);
      for (const [cid, d] of docs) {
        const status = before[id] === 'local' ? 'local' : (d?.status || 'missing');
        console.log(`${status} ${d?.label || cid} → ${md(d) ? join(ticker, md(d)) : ''}${d?.reason && status !== 'found' && status !== 'local' ? ` : ${d.reason}` : ''}`);
      }
    }
    return;
  }
  console.log(`found ${by('found').length} · missing ${by('missing').length} · deferred ${by('deferred').length} · skipped ${by('skipped').length}`);
  console.log(`this run: fetched ${stats.fetched}, already done ${stats.skipped}`);
  if (sel.tenKs.length < 10) console.log(`note: only ${sel.tenKs.length} 10-Ks on EDGAR`);
  for (const e of [...by('missing'), ...by('deferred')]) console.log(`  GAP ${e.category} / ${e.label}: ${e.reason}`);
}
