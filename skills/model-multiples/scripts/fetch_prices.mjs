#!/usr/bin/env node
// Full daily history per ticker from Yahoo into OUT/<ticker>_us_d.csv (stooq's name; columns + Adj Close).
// One try plus at most one retry after 15s (no loops). A failed ticker writes no file; exit 1 if any failed, so the
// skill falls back to the stooq pause for the whole run (one source per run).
// usage: node fetch_prices.mjs OUT TICKER [TICKER ...]
import fs from 'node:fs';
import path from 'node:path';
import YF from 'yahoo-finance2';
import { toCsv } from './pricecsv.mjs';

const yf = typeof YF === 'function' ? new YF() : YF;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const yahooSymbol = (t) => (/^[A-Z]+\.[A-Z]$/.test(t) ? t.replace('.', '-') : t);
const [out, ...tickers] = process.argv.slice(2);
if (!out || !tickers.length) { console.error('usage: node fetch_prices.mjs OUT TICKER [TICKER ...]'); process.exit(2); }
fs.mkdirSync(out, { recursive: true });
let failed = false;
for (const t of tickers.map((x) => x.toUpperCase())) {
  const get = () => yf.chart(yahooSymbol(t), { period1: '1970-01-01', interval: '1d', events: 'div|split' });
  const file = path.join(out, `${t.toLowerCase()}_us_d.csv`);
  fs.rmSync(file, { force: true });   // a failed ticker must not leave a stale file from an earlier run
  try {
    let r;
    try { r = await get(); } catch (e) {
      if (/not found|No data|Invalid/i.test(e.message)) throw e;
      console.error(`Yahoo ${t} failed (${e.message}); retrying in 15s`);
      await sleep(15000); r = await get();
    }
    const lines = toCsv(r.quotes || []).trim().split('\n').slice(1);
    if (!lines.length) throw new Error('no daily closes');
    fs.writeFileSync(file + '.tmp', [ 'Date,Open,High,Low,Close,Adj Close,Volume', ...lines ].join('\n') + '\n');
    fs.renameSync(file + '.tmp', file);   // a crash never leaves a truncated CSV
    console.log(JSON.stringify({ ticker: t, file, rows: lines.length, first: lines[0].split(',')[0],
      last: lines.at(-1).split(',')[0], dividends: (r.events?.dividends || []).length }));
  } catch (e) {
    failed = true;
    console.error(`Yahoo ${t}: ${e.message}`);
    console.log(JSON.stringify({ ticker: t, error: e.message }));
  }
}
process.exit(failed ? 1 : 0);
