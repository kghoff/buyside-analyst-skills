import { describe, it, expect } from 'vitest';
import {
  fyeMonthOf, fiscalFromPeriodEnd, quarterKey, shortLabel,
  windowQuarters, quarterForRelease, addDays,
} from '../scripts/fiscal.mjs';

describe('fiscalFromPeriodEnd', () => {
  // Labels must match how the company names its own quarters, or transcripts
  // and press releases land in the wrong quarter.
  it('handles a December year end', () => {
    expect(fiscalFromPeriodEnd('2025-03-31', 12)).toEqual({ fy: 2025, fq: 1 });
    expect(fiscalFromPeriodEnd('2025-12-31', 12)).toEqual({ fy: 2025, fq: 4 });
  });
  it('names a September fiscal year by the calendar year it ends in (Apple)', () => {
    expect(fiscalFromPeriodEnd('2024-12-28', 9)).toEqual({ fy: 2025, fq: 1 });
    expect(fiscalFromPeriodEnd('2025-09-27', 9)).toEqual({ fy: 2025, fq: 4 });
  });
  it('snaps 52/53-week periods that end a few days into the next month (NVIDIA)', () => {
    expect(fiscalFromPeriodEnd('2025-01-26', 1)).toEqual({ fy: 2025, fq: 4 });
    expect(fiscalFromPeriodEnd('2025-02-01', 1)).toEqual({ fy: 2025, fq: 4 });
    expect(fiscalFromPeriodEnd('2025-04-27', 1)).toEqual({ fy: 2026, fq: 1 });
  });
});

describe('labels and windows', () => {
  it('parses the SEC fiscalYearEnd string', () => {
    expect(fyeMonthOf('0926')).toBe(9);
    expect(fyeMonthOf(undefined)).toBe(12);
  });
  it('formats keys and short labels', () => {
    expect(quarterKey({ fy: 2025, fq: 1 })).toBe('2025Q1');
    expect(shortLabel({ fy: 2025, fq: 1 })).toBe('2025 Q1');
  });
  it('builds a 12-quarter window, newest first, crossing year boundaries', () => {
    const w = windowQuarters({ fy: 2025, fq: 4 }, 12);
    expect(w).toHaveLength(12);
    expect(w[0]).toEqual({ fy: 2025, fq: 4 });
    expect(w[11]).toEqual({ fy: 2023, fq: 1 });
  });
  it('adds days to an ISO date', () => {
    expect(addDays('2025-12-31', 1)).toBe('2026-01-01');
  });
});

describe('quarterForRelease', () => {
  const periods = [
    { end: '2025-03-31', fy: 2025, fq: 1 },
    { end: '2025-06-30', fy: 2025, fq: 2 },
  ];
  it('maps an earnings 8-K to the latest period that ended before it', () => {
    expect(quarterForRelease('2025-07-25', periods)).toEqual({ fy: 2025, fq: 2 });
  });
  it('maps to the next quarter when the release beat its 10-Q to EDGAR', () => {
    // Q3 ended 2025-09-30, release 2025-10-25, Q3 10-Q not filed yet:
    // the latest known period (Q2) is 117 days old.
    expect(quarterForRelease('2025-10-25', periods)).toEqual({ fy: 2025, fq: 3 });
  });
  it('maps a deliveries 8-K filed Oct 2 to the quarter that just ended (Tesla)', () => {
    // Filed 94 days after the Jun 30 period, but reports Q3 (ended Sep 30).
    expect(quarterForRelease('2025-10-02', periods)).toEqual({ fy: 2025, fq: 3 });
  });
  it('keeps a late 10-K-season release in Q4', () => {
    expect(quarterForRelease('2025-03-01', [{ end: '2024-12-31', fy: 2024, fq: 4 }])).toEqual({ fy: 2024, fq: 4 });
  });
  it('returns null when no period precedes the filing', () => {
    expect(quarterForRelease('2020-01-01', periods)).toBeNull();
  });
});
