#!/usr/bin/env node
// One Yahoo snapshot of the subject's short data into WORK/short.json: price, dividend yield, shares short, short %
// of float, days to cover (Yahoo's shortRatio), the short-interest date and 3-month average volume. Retries like
// model-multiples/scripts/fetch_comps.mjs. On failure writes {ticker, asof, error} and exits 1; the skill carries on
// and the tab shows n/a. Yahoo omits dividendYield for a stock with no dividend: that is written as 0.
// usage: node fetch_short.mjs WORK TICKER
import fs from 'node:fs';
import path from 'node:path';
import YF from 'yahoo-finance2';

const yf = typeof YF === 'function' ? new YF() : YF;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const yahooSymbol = (t) => (/^[A-Z]+\.[A-Z]$/.test(t) ? t.replace('.', '-') : t);

async function retry(fn, label, waits = [5000, 15000, 45000]) {
  for (let i = 0; ; i++) {
    try { return await fn(); } catch (e) {
      if (i >= waits.length || /not found|No data|Invalid/i.test(e.message)) throw new Error(`${label}: ${e.message}`);
      console.error(`${label} failed (${e.message}); retrying in ${waits[i] / 1000}s`);
      await sleep(waits[i]);
    }
  }
}

const [work, t0] = process.argv.slice(2);
if (!work || !t0) { console.error('usage: node fetch_short.mjs WORK TICKER'); process.exit(2); }
const t = t0.toUpperCase();
const asof = new Date().toLocaleDateString('en-CA');
let out;
try {
  const qs = await retry(() => yf.quoteSummary(yahooSymbol(t), { modules: ['price', 'summaryDetail', 'defaultKeyStatistics'] }),
    `Yahoo ${t}`);
  const k = qs.defaultKeyStatistics || {};
  const s = qs.summaryDetail || {};
  out = {
    ticker: t, asof, source: 'Yahoo Finance quoteSummary (price, summaryDetail, defaultKeyStatistics)',
    price: qs.price?.regularMarketPrice ?? null, dividend_yield: s.dividendYield ?? 0,
    shares_short: k.sharesShort ?? null, short_pct_float: k.shortPercentOfFloat ?? null, days_to_cover: k.shortRatio ?? null,
    short_date: k.dateShortInterest ? new Date(k.dateShortInterest).toISOString().slice(0, 10) : null,
    avg_volume_3m: qs.price?.averageDailyVolume3Month ?? s.averageVolume ?? null,
  };
  if (out.price == null) out = { ticker: t, asof, error: 'Yahoo returned no price' };
} catch (e) {
  out = { ticker: t, asof, error: e.message };
}
fs.mkdirSync(work, { recursive: true });
fs.writeFileSync(path.join(work, 'short.json'), JSON.stringify(out, null, 1));
console.log(out.error ? `FAILED ${out.error}` : `ok: ${t} $${out.price}, short ${out.short_pct_float} of float, ${out.days_to_cover} days to cover`);
process.exit(out.error ? 1 : 0);
