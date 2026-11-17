#!/usr/bin/env node
// One Yahoo snapshot per comp into WORK/comps/<T>.json (price, market cap, 3-month ADV, TTM financialData, earnings
// and revenue estimates for this year and next). Retries like model-consensus/scripts/fetch.mjs. A comp that fails
// is written as {ticker, error} and the run continues; the exit code is 1 only when the subject (first ticker) fails.
// usage: node fetch_comps.mjs WORK SUBJECT [COMP ...]
import fs from 'node:fs';
import path from 'node:path';
import YF from 'yahoo-finance2';

const yf = typeof YF === 'function' ? new YF() : YF;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const yahooSymbol = (t) => (/^[A-Z]+\.[A-Z]$/.test(t) ? t.replace('.', '-') : t);   // BRK.B -> BRK-B

async function retry(fn, label, waits = [5000, 15000, 45000]) {
  for (let i = 0; ; i++) {
    try { return await fn(); } catch (e) {
      if (i >= waits.length) throw new Error(`${label}: ${e.message}`);
      console.error(`${label} failed (${e.message}); retrying in ${waits[i] / 1000}s`);
      await sleep(waits[i]);
    }
  }
}

const [work, ...tickers] = process.argv.slice(2);
if (!work || !tickers.length) { console.error('usage: node fetch_comps.mjs WORK SUBJECT [COMP ...]'); process.exit(2); }
fs.mkdirSync(path.join(work, 'comps'), { recursive: true });
const asof = new Date().toLocaleDateString('en-CA');
let subjectFailed = false;
for (const [i, t] of tickers.map((x) => x.toUpperCase()).entries()) {
  let out;
  try {
    const qs = await retry(() => yf.quoteSummary(yahooSymbol(t), { modules: ['price', 'financialData', 'earningsTrend'] }),
      `Yahoo ${t}`);
    out = {
      ticker: t, asof, source: 'Yahoo Finance quoteSummary (price, financialData, earningsTrend)',
      price: qs.price?.regularMarketPrice ?? null, currency: qs.price?.currency ?? null,
      marketCap: qs.price?.marketCap ?? null, adv3m: qs.price?.averageDailyVolume3Month ?? null,
      financial: qs.financialData || {}, trend: qs.earningsTrend?.trend || [],
    };
  } catch (e) {
    out = { ticker: t, asof, error: e.message };
    if (i === 0) subjectFailed = true;
  }
  fs.writeFileSync(path.join(work, 'comps', `${t}.json`), JSON.stringify(out, null, 1));
  console.log(`${t}: ${out.error ? 'FAILED ' + out.error : 'ok'}`);
}
process.exit(subjectFailed ? 1 : 0);
