// SEC EDGAR: ticker→CIK, filing history, fiscal tags, filing selection, 8-K exhibits.

import * as cheerio from 'cheerio';
import { secFetch } from './http.mjs';
import {
  fyeMonthOf, fiscalFromPeriodEnd, quarterKey, windowQuarters, quarterForRelease, addDays,
} from './fiscal.mjs';

const ANNUALS = 10;
const QUARTERS = 12;
const pad = (cik) => String(cik).padStart(10, '0');

export async function resolveCik(ticker) {
  const data = await (await secFetch('https://www.sec.gov/files/company_tickers.json')).json();
  const t = ticker.toUpperCase().replace('.', '-'); // SEC spells BRK.B as BRK-B
  const hit = Object.values(data).find((c) => c.ticker === t);
  return hit ? { cik: pad(hit.cik_str), name: hit.title } : null;
}

// EDGAR returns filings as parallel arrays; turn them into row objects.
export function rowsFromColumns(cols) {
  return cols.accessionNumber.map((accn, i) => ({
    accn,
    form: cols.form[i],
    filingDate: cols.filingDate[i],
    reportDate: cols.reportDate[i],
    primaryDocument: cols.primaryDocument[i],
    items: cols.items?.[i] || '',
  }));
}

export async function fetchSubmissions(cik, sinceDate) {
  const sub = await (await secFetch(`https://data.sec.gov/submissions/CIK${pad(cik)}.json`)).json();
  const filings = rowsFromColumns(sub.filings.recent);
  // Busy filers (lots of Form 4s) push older 10-Ks into paginated files.
  for (const page of sub.filings.files || []) {
    if (page.filingTo < sinceDate) continue;
    const cols = await (await secFetch(`https://data.sec.gov/submissions/${page.name}`)).json();
    filings.push(...rowsFromColumns(cols));
  }
  return { name: sub.name, fiscalYearEnd: sub.fiscalYearEnd, filings };
}

// The company's own fy/fp per accession, from a dei tag on every 10-K/10-Q cover.
export function parseFiscalTags(concept) {
  const map = new Map();
  for (const rows of Object.values(concept.units || {})) {
    for (const r of rows) {
      const fq = r.fp === 'FY' ? 4 : Number(String(r.fp).replace('Q', ''));
      if (r.accn && r.fy && fq >= 1 && fq <= 4 && !map.has(r.accn)) map.set(r.accn, { fy: r.fy, fq });
    }
  }
  return map;
}

export async function fetchFiscalTags(cik) {
  try {
    const url = `https://data.sec.gov/api/xbrl/companyconcept/CIK${pad(cik)}/dei/EntityCommonStockSharesOutstanding.json`;
    return parseFiscalTags(await (await secFetch(url)).json());
  } catch {
    return new Map(); // selectFilings falls back to period-end math
  }
}

function uniqBy(list, keyFn) {
  const seen = new Set();
  return list.filter((x) => (seen.has(keyFn(x)) ? false : seen.add(keyFn(x))));
}

export function selectFilings({ filings, fiscalTags, fiscalYearEnd }) {
  const fyeMonth = fyeMonthOf(fiscalYearEnd);
  const TRANSITION_OR_AMENDED = new Set(['10-K/A', '10-Q/A', '10-KT', '10-QT', '10-KT/A', '10-QT/A']);
  const periodic = filings
    .filter((f) => (f.form === '10-K' || f.form === '10-Q') && f.reportDate)
    .map((f) => {
      const tag = fiscalTags.get(f.accn) || fiscalFromPeriodEnd(f.reportDate, fyeMonth);
      return { ...f, fy: tag.fy, fq: f.form === '10-K' ? 4 : tag.fq };
    })
    .sort((a, b) => b.reportDate.localeCompare(a.reportDate));
  const skippedFrom = (since) => filings.filter((f) => TRANSITION_OR_AMENDED.has(f.form) && f.filingDate >= since);
  if (periodic.length === 0) return { tenKs: [], tenQs: [], proxies: [], releases: [], regFd: [], window: [], releaseWindow: [], skipped: [] };

  const latest = periodic[0];
  const periods = periodic.map((f) => ({ end: f.reportDate, fy: f.fy, fq: f.fq }));
  const is8K = (f, item) => f.form === '8-K' && new RegExp(`\\b${item.replace('.', '\\.')}\\b`).test(f.items);

  const mapped = filings
    .filter((f) => is8K(f, '2.02'))
    .map((f) => ({ ...f, ...quarterForRelease(f.filingDate, periods) }))
    .filter((f) => f.fy);
  // Anchor on the later of the newest periodic filing and the newest release,
  // so a quarter whose earnings are out (10-Q not yet filed) is included.
  const rank = (q) => q.fy * 4 + q.fq;
  const anchor = mapped.reduce((a, r) => (rank(r) > rank(a) ? r : a), latest);
  const window = windowQuarters(anchor, QUARTERS);

  const cutoff = addDays(latest.reportDate, -3 * 365);
  const regFd = filings
    .filter((f) => is8K(f, '7.01') && !is8K(f, '2.02') && f.filingDate >= cutoff)
    .sort((a, b) => b.filingDate.localeCompare(a.filingDate));

  // Dedupe on period end, not the XBRL fiscal label, so a mis-tagged fy can't drop a real filing.
  const tenKs = uniqBy(periodic.filter((f) => f.form === '10-K'), (f) => f.reportDate).slice(0, ANNUALS);
  // 10-Qs cover the same fiscal years as the 10-Ks (plus the current year), so
  // model-historicals can build 10 years of quarters (Q4 comes from the 10-K).
  const oldestFy = tenKs.length ? tenKs[tenKs.length - 1].fy : latest.fy;
  const tenQs = uniqBy(periodic.filter((f) => f.form === '10-Q' && f.fy >= oldestFy), (f) => f.reportDate);
  const skipped = skippedFrom(tenKs.length ? tenKs[tenKs.length - 1].reportDate : '');
  // Earnings releases cover the same fiscal years as the 10-Qs (house default): /model-kpis needs every
  // year's reconciliations and /model-price-history every quarter's release date. Transcripts and decks keep `window`.
  const releaseWindow = windowQuarters(anchor, Math.max(QUARTERS, rank(anchor) - (oldestFy * 4 + 1) + 1));
  const inReleaseWindow = new Set(releaseWindow.map(quarterKey));
  const releases = mapped
    .filter((f) => inReleaseWindow.has(quarterKey(f)))
    .sort((a, b) => b.filingDate.localeCompare(a.filingDate));

  return { tenKs, tenQs, proxies: selectProxies(filings, tenKs), releases, regFd, window, releaseWindow, skipped };
}

// The annual proxy (DEF 14A) for each 10-K: the first one filed from a month before
// that 10-K up to a month before the next. Later DEF 14As in the same span are
// special-meeting proxies (annual proxies only). proxy is null when not filed yet.
export function selectProxies(filings, tenKs) {
  const proxies = filings.filter((f) => f.form === 'DEF 14A').sort((a, b) => a.filingDate.localeCompare(b.filingDate));
  return tenKs.map((k, i) => {
    const from = addDays(k.filingDate, -30);
    const to = i > 0 ? addDays(tenKs[i - 1].filingDate, -30) : '9999';
    return { tenK: k, proxy: proxies.find((p) => p.filingDate >= from && p.filingDate < to) || null };
  });
}

export function filingUrl(cik, f) {
  return `https://www.sec.gov/Archives/edgar/data/${Number(cik)}/${f.accn.replace(/-/g, '')}/${f.primaryDocument}`;
}

export function parseExhibitIndex(html) {
  const $ = cheerio.load(html);
  const out = [];
  $('table.tableFile').first().find('tr').each((_, tr) => {
    const td = $(tr).find('td');
    if (td.length < 4) return;
    const type = $(td[3]).text().trim().toUpperCase();
    const href = $(td[2]).find('a').attr('href');
    if (!href || !type.startsWith('EX-99')) return;
    out.push({
      type,
      description: $(td[1]).text().trim(),
      url: new URL(href.replace(/^\/ix\?doc=/, ''), 'https://www.sec.gov').href,
    });
  });
  return out;
}

export async function fetchExhibits(cik, accn) {
  const url = `https://www.sec.gov/Archives/edgar/data/${Number(cik)}/${accn.replace(/-/g, '')}/${accn}-index.htm`;
  return parseExhibitIndex(await (await secFetch(url)).text());
}

const DECK_RE = /presentation|slides|deck|investor\s*day/i;

export function classifyExhibit(ex) {
  const name = ex.url.split('/').pop();
  return DECK_RE.test(ex.description) || DECK_RE.test(name) || /\.pdf$/i.test(name) ? 'deck' : 'release';
}
