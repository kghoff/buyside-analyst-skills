#!/usr/bin/env node
// Yahoo daily bars around the reaction day into WORK/yahoo_after.json: the reaction day's open and close, the
// previous close, and the latest close. Px Data has closes only, so the gap at the open and open-to-close need
// this. Retries like fetch_earnings.mjs. On failure writes {ticker, error} and exits 1; the skill carries on and
// the gap rows show '?'.
// usage: node fetch_after.mjs WORK TICKER YYYY-MM-DD
import fs from 'node:fs';
import path from 'node:path';
import YF from 'yahoo-finance2';

const yf = typeof YF === 'function' ? new YF() : YF;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const sym = (t) => (/^[A-Z]+\.[A-Z]$/.test(t) ? t.replace('.', '-') : t);
const iso = (d) => new Date(d).toISOString().slice(0, 10);
async function retry(fn, label, waits = [5000, 15000, 45000]) {
  for (let i = 0; ; i++) {
    try { return await fn(); } catch (e) {
      if (i >= waits.length || /not found|No data|Invalid/i.test(e.message)) throw new Error(`${label}: ${e.message}`);
      await sleep(waits[i]);
    }
  }
}
const [work, t0, day] = process.argv.slice(2);
if (!work || !t0 || !/^\d{4}-\d\d-\d\d$/.test(day || '')) {
  console.error('usage: node fetch_after.mjs WORK TICKER YYYY-MM-DD');
  process.exit(2);
}
const t = t0.toUpperCase();
let out;
try {
  const from = new Date(new Date(day).getTime() - 10 * 86400000);
  const c = await retry(() => yf.chart(sym(t), { period1: from, interval: '1d' }), `Yahoo chart ${t}`);
  const q = (c.quotes || []).filter((x) => x.close != null && x.open != null);
  const i = q.findIndex((x) => iso(x.date) === day);
  if (i < 1) throw new Error(`no bar for ${day}`);
  out = { ticker: t, asof: iso(Date.now()), source: 'Yahoo Finance chart (daily bars)', reaction_day: day,
    open: q[i].open, close: q[i].close, prev_close: q[i - 1].close, price: q[q.length - 1].close,
    price_date: iso(q[q.length - 1].date) };
} catch (e) { out = { ticker: t, error: e.message }; }
fs.mkdirSync(work, { recursive: true });
fs.writeFileSync(path.join(work, 'yahoo_after.json'), JSON.stringify(out, null, 1));
console.log(out.error ? `FAILED ${out.error}` : `ok: ${t} ${day} open ${out.open} close ${out.close}`);
process.exit(out.error ? 1 : 0);
