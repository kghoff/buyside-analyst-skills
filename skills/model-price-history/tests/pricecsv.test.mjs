// The CSV is stooq's format plus Adj Close: Close is the traded price (P/E), Adj Close adds dividends (returns).
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { toCsv } from '../scripts/pricecsv.mjs';

const fix = JSON.parse(fs.readFileSync(new URL('./fixtures/yahoo_chart_abt.json', import.meta.url)));

test('header is stooq plus Adj Close, one row per day with a close', () => {
  const lines = toCsv(fix.quotes).trim().split('\n');
  assert.equal(lines[0], 'Date,Open,High,Low,Close,Adj Close,Volume');
  assert.equal(lines.length - 1, fix.quotes.filter((q) => q.close != null).length);
});

test('dates are New York trading dates, ascending', () => {
  const d = toCsv(fix.quotes).trim().split('\n').slice(1).map((l) => l.split(',')[0]);
  assert.match(d[0], /^2025-01-0\d$/);
  assert.deepEqual([...d].sort(), d);
});

// Yahoo's Adj Close is scaled to today's price, so later dividends keep it below Close even at the end of this
// window. What shows the dividend is the Adj Close / Close ratio stepping up across the ex-date (2025-01-15).
test('a dividend payer: Adj Close is below Close, and the ratio steps up across the ex-date', () => {
  const rows = toCsv(fix.quotes).trim().split('\n').slice(1).map((l) => l.split(','));
  const ratio = (r) => Number(r[5]) / Number(r[4]);
  assert.ok(Number(rows[0][5]) < Number(rows[0][4]));
  const ex = fix.events.dividends[0].date.slice(0, 10);
  const before = rows.filter((r) => r[0] < ex).at(-1);
  const after = rows.find((r) => r[0] >= ex);
  assert.ok(ratio(after) > ratio(before) + 0.003);
});

test('rows with no close are dropped, never written as blanks', () => {
  const q = [{ date: '2025-01-02T14:30:00.000Z', open: 1, high: 1, low: 1, close: null, adjclose: null, volume: 0 }];
  assert.equal(toCsv(q).trim().split('\n').length, 1);
});
