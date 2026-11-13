#!/usr/bin/env node
// Pull every free analyst data point for one ticker into WORK/snapshots/<asof>.json (one file per day; a rerun on
// the same day replaces it). Yahoo through the yahoo-finance2 library (its raw crumb endpoint rate-limits), with
// retries; Nasdaq (Zacks data) is optional. No tab is ever built from a partial Yahoo fetch: on failure nothing is
// written and the exit code is 1.
// usage: node fetch.mjs TICKER WORKDIR [--asof YYYY-MM-DD]
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import YF from 'yahoo-finance2';

const yf = typeof YF === 'function' ? new YF() : YF;
const UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36';
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function retry(fn, label, waits = [5000, 15000, 45000]) {
  for (let i = 0; ; i++) {
    try {
      return await fn();
    } catch (e) {
      if (i >= waits.length) throw new Error(`${label}: ${e.message}`);
      console.error(`${label} failed (${e.message}); retrying in ${waits[i] / 1000}s`);
      await sleep(waits[i]);
    }
  }
}

// Share-class tickers: Yahoo wants BRK-B (BRK.B returns an empty object, no error); Nasdaq wants BRK.B. Foreign
// exchange suffixes (SAP.DE, 7203.T) stay as they are.
export const yahooSymbol = (t) => (/^[A-Z]+\.[A-Z]$/.test(t) ? t.replace('.', '-') : t);

// Yahoo knows nothing about the ticker: no price, no rating history and no estimates.
export const yahooEmpty = (snap) =>
  snap.price?.value == null && !snap.yahoo?.history?.length && !snap.yahoo?.trend?.length;

async function nasdaq(t, what) {
  const r = await fetch(`https://api.nasdaq.com/api/analyst/${t}/${what}`,
    { headers: { 'User-Agent': UA, Accept: 'application/json' } });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  const j = await r.json();
  if (!j.data) throw new Error(JSON.stringify(j.status || j).slice(0, 200));
  return j.data;
}

export async function fetchAll(t, asof) {
  const ys = yahooSymbol(t);
  const qs = await retry(() => yf.quoteSummary(ys, {
    modules: ['price', 'upgradeDowngradeHistory', 'earningsTrend', 'recommendationTrend', 'financialData'],
  }), 'Yahoo quoteSummary');
  const start = new Date(`${asof}T00:00:00Z`);
  start.setUTCFullYear(start.getUTCFullYear() - 6);
  const ch = await retry(() => yf.chart(ys, { period1: start.toISOString().slice(0, 10), interval: '1mo', events: 'split' }),
    'Yahoo split history');
  const splits = (ch.events?.splits || []).map((s) => ({
    date: new Date(s.date).toISOString().slice(0, 10), ratio: s.numerator / s.denominator,
  }));
  const out = {
    ticker: t, asof, fetched_at: new Date().toISOString(),
    price: { value: qs.price?.regularMarketPrice ?? null, time: qs.price?.regularMarketTime ?? null,
             currency: qs.price?.currency ?? null },
    yahoo: { history: qs.upgradeDowngradeHistory?.history || [], trend: qs.earningsTrend?.trend || [],
             recommendation: qs.recommendationTrend?.trend || [], financial: qs.financialData || {} },
    splits,
    nasdaq: { forecast: null, ratings: null, errors: [] },
  };
  for (const [k, what] of [['forecast', 'earnings-forecast'], ['ratings', 'ratings']]) {
    try { out.nasdaq[k] = await nasdaq(t, what); } catch (e) { out.nasdaq.errors.push(`${what}: ${e.message}`); }
  }
  return out;
}

async function main() {
  const [tick, work, ...rest] = process.argv.slice(2);
  if (!tick || !work) {
    console.error('usage: node fetch.mjs TICKER WORKDIR [--asof YYYY-MM-DD]');
    process.exit(2);
  }
  const k = rest.indexOf('--asof');
  const asof = k >= 0 ? rest[k + 1] : new Date().toLocaleDateString('en-CA');
  const T = tick.toUpperCase();
  let snap;
  try {
    snap = await fetchAll(T, asof);
  } catch (e) {
    console.error(`FAILED: ${e.message}. Nothing written.`);
    process.exit(1);
  }
  if (yahooEmpty(snap)) {
    console.error(`Yahoo returned no data for ${T} (no price, no rating history, no estimates) — check the ticker. `
      + 'Nothing written.');
    process.exit(1);
  }
  const dir = path.join(work, 'snapshots');
  fs.mkdirSync(dir, { recursive: true });
  const file = path.join(dir, `${asof}.json`);
  fs.writeFileSync(`${file}.tmp`, JSON.stringify(snap, null, 1));
  fs.renameSync(`${file}.tmp`, file);
  const warn = [];
  if (!snap.yahoo.history.length) warn.push('no rating history on Yahoo');
  if (!snap.yahoo.trend.length) warn.push('no consensus estimates on Yahoo');
  if (snap.price.value == null) warn.push('no price on Yahoo');
  console.log(JSON.stringify({ file, actions: snap.yahoo.history.length, periods: snap.yahoo.trend.map((x) => x.period),
    price: snap.price.value, splits: snap.splits, nasdaq_errors: snap.nasdaq.errors, warnings: warn }, null, 1));
}

if (process.argv[1] && import.meta.url === pathToFileURL(fs.realpathSync(process.argv[1])).href) await main();
