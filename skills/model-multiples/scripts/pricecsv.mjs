// Yahoo chart quotes -> stooq-format CSV plus Adj Close. Pure (no network) so it is tested on a saved response.
// Close = split-adjusted traded price (P/E, price chart); Adj Close = also dividend-adjusted (total-return series).
const NY = { timeZone: 'America/New_York' };
export const nyDate = (d) => new Date(d).toLocaleDateString('en-CA', NY);

export function toCsv(quotes) {
  const byDate = new Map();   // Yahoo can repeat today's bar intraday: the last one per New York date wins
  for (const q of quotes) {
    if (q.close == null || !Number.isFinite(Number(q.close))) continue;
    const fill = (v) => (v == null ? q.close : v);
    byDate.set(nyDate(q.date), [nyDate(q.date), fill(q.open), fill(q.high), fill(q.low), q.close,
      q.adjclose ?? q.close, q.volume ?? 0]);
  }
  const rows = [...byDate.values()].sort((a, b) => (a[0] < b[0] ? -1 : 1));
  return ['Date,Open,High,Low,Close,Adj Close,Volume', ...rows.map((r) => r.join(','))].join('\n') + '\n';
}
