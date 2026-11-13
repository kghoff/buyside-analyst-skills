// Fiscal-quarter math. Fiscal years are named by the calendar year in which
// they end (Apple's Oct 2024–Sep 2025 year is FY2025).

const DAY = 86_400_000;
const toDate = (iso) => new Date(`${iso}T00:00:00Z`);

export const addDays = (iso, n) => new Date(toDate(iso).getTime() + n * DAY).toISOString().slice(0, 10);
export const daysBetween = (a, b) => Math.round((toDate(b) - toDate(a)) / DAY);

// SEC submissions give fiscalYearEnd as "MMDD", e.g. "0926".
export function fyeMonthOf(fiscalYearEnd) {
  const m = Number(String(fiscalYearEnd || '1231').slice(0, 2));
  return m >= 1 && m <= 12 ? m : 12;
}

// Fallback when a filing has no XBRL fy/fp tags. 52/53-week filers end
// periods a few days into the next month; shifting back 7 days snaps them
// to the intended month.
export function fiscalFromPeriodEnd(iso, fyeMonth) {
  const d = new Date(toDate(iso).getTime() - 7 * DAY);
  const year = d.getUTCFullYear();
  const month = d.getUTCMonth() + 1;
  const monthsToFye = (fyeMonth - month + 12) % 12;
  return { fy: month <= fyeMonth ? year : year + 1, fq: 4 - Math.floor(monthsToFye / 3) };
}

export const quarterKey = ({ fy, fq }) => `${fy}Q${fq}`;
// Year first ("2025 Q1") so file names sort by date.
export const shortLabel = ({ fy, fq }) => `${fy} Q${fq}`;
export const nextQuarter = ({ fy, fq }) => (fq === 4 ? { fy: fy + 1, fq: 1 } : { fy, fq: fq + 1 });
export const prevQuarter = ({ fy, fq }) => (fq === 1 ? { fy: fy - 1, fq: 4 } : { fy, fq: fq - 1 });

// The n most recent quarters ending at `latest`, newest first.
export function windowQuarters(latest, n) {
  const out = [];
  let q = { fy: latest.fy, fq: latest.fq };
  for (let i = 0; i < n; i++) {
    out.push(q);
    q = prevQuarter(q);
  }
  return out;
}

// Earnings 8-Ks (and production/deliveries 8-Ks) report the most recently
// ENDED quarter. `periods` are 10-Q/10-K period ends ({ end, fy, fq }). Take
// the latest known period before the filing, then advance one quarter per 91
// days elapsed: normal earnings (25-60 days later) stay on that period, while
// a filing a day or more past the next quarter-end lands in that quarter.
export function quarterForRelease(filingDate, periods) {
  const p = [...periods].sort((a, b) => b.end.localeCompare(a.end)).find((x) => x.end < filingDate);
  if (!p) return null;
  let q = { fy: p.fy, fq: p.fq };
  for (let i = Math.floor(daysBetween(p.end, filingDate) / 91); i > 0; i--) q = nextQuarter(q);
  return q;
}
