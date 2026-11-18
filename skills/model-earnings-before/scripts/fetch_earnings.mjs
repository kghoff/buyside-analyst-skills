#!/usr/bin/env node
// Yahoo data for the earnings preview into WORK/earnings.json: price, the next earnings date, the options-implied
// move and the last 4 EPS surprises. Yahoo shows the LAST earnings date until the company announces the next one;
// then earnings_date is in the past and context.py estimates the date instead. The implied move is the at-the-money
// straddle (call mid + put mid) on the first expiry after the print, divided by the price: only fetched when the
// print is still ahead (a straddle with no print in it is not a print move). Retries like fetch_short.mjs. On
// failure writes {ticker, asof, error} and exits 1; the skill carries on (price from Px Data, no implied move).
// usage: node fetch_earnings.mjs WORK TICKER
import fs from 'node:fs';
import path from 'node:path';
import YF from 'yahoo-finance2';

const yf = typeof YF === 'function' ? new YF() : YF;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const yahooSymbol = (t) => (/^[A-Z]+\.[A-Z]$/.test(t) ? t.replace('.', '-') : t);
const iso = (d) => (d ? new Date(d).toISOString().slice(0, 10) : null);

async function retry(fn, label, waits = [5000, 15000, 45000]) {
  for (let i = 0; ; i++) {
    try { return await fn(); } catch (e) {
      if (i >= waits.length || /not found|No data|Invalid/i.test(e.message)) throw new Error(`${label}: ${e.message}`);
      console.error(`${label} failed (${e.message}); retrying in ${waits[i] / 1000}s`);
      await sleep(waits[i]);
    }
  }
}

const mid = (o) => (o && o.bid > 0 && o.ask > 0 ? (o.bid + o.ask) / 2 : o?.lastPrice ?? null);

const [work, t0] = process.argv.slice(2);
if (!work || !t0) { console.error('usage: node fetch_earnings.mjs WORK TICKER'); process.exit(2); }
const t = t0.toUpperCase();
const asof = new Date().toLocaleDateString('en-CA');
let out;
try {
  const q = await retry(() => yf.quoteSummary(yahooSymbol(t), { modules: ['price', 'calendarEvents', 'earningsHistory'] }),
    `Yahoo ${t}`);
  const price = q.price?.regularMarketPrice ?? null;
  const ed = iso(q.calendarEvents?.earnings?.earningsDate?.[0]);
  out = {
    ticker: t, asof, source: 'Yahoo Finance quoteSummary (price, calendarEvents, earningsHistory) and options',
    price, earnings_date: ed, implied_move: null, straddle: null,
    surprises: (q.earningsHistory?.history || []).map((h) => ({
      quarter: iso(h.quarter), estimate: h.epsEstimate ?? null, actual: h.epsActual ?? null,
      surprise: h.surprisePercent ?? null })),
  };
  if (price == null) out = { ticker: t, asof, error: 'Yahoo returned no price' };
  else if (ed && ed > asof) {
    try {
      const base = await retry(() => yf.options(yahooSymbol(t)), `Yahoo options ${t}`);
      const exp = (base.expirationDates || []).find((d) => iso(d) > ed);
      if (exp) {
        const o = await retry(() => yf.options(yahooSymbol(t), { date: exp }), `Yahoo options ${t} ${iso(exp)}`);
        const ch = o.options?.[0] || { calls: [], puts: [] };
        const call = ch.calls.reduce((a, c) => (!a || Math.abs(c.strike - price) < Math.abs(a.strike - price) ? c : a), null);
        const put = call && ch.puts.find((p) => p.strike === call.strike);
        if (call && put && mid(call) != null && mid(put) != null) {
          out.straddle = { expiry: iso(exp), strike: call.strike, call: mid(call), put: mid(put) };
          out.implied_move = (mid(call) + mid(put)) / price;
        }
      }
    } catch (e) {
      out.options_error = e.message;           // the preview carries on without an implied move
    }
  }
} catch (e) {
  out = { ticker: t, asof, error: e.message };
}
fs.mkdirSync(work, { recursive: true });
fs.writeFileSync(path.join(work, 'earnings.json'), JSON.stringify(out, null, 1));
console.log(out.error ? `FAILED ${out.error}`
  : `ok: ${t} $${out.price}, earnings date ${out.earnings_date} (${out.earnings_date > asof ? 'ahead' : 'past: will be estimated'}), implied move ${out.implied_move ?? 'n/a'}, ${out.surprises.length} surprises`);
process.exit(out.error ? 1 : 0);
