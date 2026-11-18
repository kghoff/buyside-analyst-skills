// Yahoo chart quotes -> stooq-format CSV plus Adj Close. Pure (no network) so it is tested on a saved response.
// Close = split-adjusted traded price (P/E, price chart); Adj Close = also dividend-adjusted (total-return series).
const NY = { timeZone: 'America/New_York' };

export function toCsv(quotes) {
  const rows = quotes
    .filter((q) => q.close != null && Number.isFinite(Number(q.close)))
    .map((q) => [new Date(q.date).toLocaleDateString('en-CA', NY), q.open, q.high, q.low, q.close,
      q.adjclose ?? q.close, q.volume ?? 0]);
  rows.sort((a, b) => (a[0] < b[0] ? -1 : 1));
  return ['Date,Open,High,Low,Close,Adj Close,Volume', ...rows.map((r) => r.join(','))].join('\n') + '\n';
}
