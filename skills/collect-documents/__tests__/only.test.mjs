import { describe, it, expect } from 'vitest';
import { mkdtempSync, mkdirSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { parseOnly, parseQuarters, filterSelection, localStatus, requestedIds } from '../scripts/only.mjs';

// A selection as selectFilings returns it: newest first, fiscal labels on every filing.
const q = (fy, fq) => ({ fy, fq });
const sel = {
  tenKs: [{ fy: 2025, fq: 4, reportDate: '2025-12-31' }, { fy: 2024, fq: 4, reportDate: '2024-12-31' }],
  tenQs: [{ fy: 2026, fq: 3, reportDate: '2026-09-30' }, { fy: 2026, fq: 2, reportDate: '2026-06-30' },
    { fy: 2026, fq: 1, reportDate: '2026-03-31' }],
  proxies: [{ tenK: {}, proxy: {} }],
  releases: [{ fy: 2026, fq: 3, accn: 'a3' }, { fy: 2026, fq: 2, accn: 'a2' }],
  regFd: [{ accn: 'r1' }],
  window: [q(2026, 3), q(2026, 2), q(2026, 1), q(2025, 4)],
  releaseWindow: [q(2026, 3), q(2026, 2), q(2026, 1), q(2025, 4)],
  skipped: [{ accn: 's1' }],
};

describe('parseOnly', () => {
  it('reads a comma list of kinds', () => {
    expect(parseOnly('calls,10-Q')).toEqual(new Set(['calls', '10-Q']));
  });
  it('rejects an unknown kind, naming the allowed ones (a typo must not silently fetch nothing)', () => {
    expect(() => parseOnly('calls,transcripts')).toThrow(/calls, 10-Q, 10-K, releases/);
  });
});

describe('parseQuarters', () => {
  it('takes explicit fiscal quarters as the manifest keys them (agents write these by hand)', () => {
    expect(parseQuarters('2026Q3,2026Q2', sel)).toEqual(['2026Q3', '2026Q2']);
  });
  it('counts lastN back from the peer\'s own window, and defaults to last2', () => {
    expect(parseQuarters('last3', sel)).toEqual(['2026Q3', '2026Q2', '2026Q1']);
    expect(parseQuarters(undefined, sel)).toEqual(['2026Q3', '2026Q2']);
  });
  it('rejects a malformed quarter', () => {
    expect(() => parseQuarters('Q3 2026', sel)).toThrow(/2026Q3/);
  });
});

describe('filterSelection', () => {
  // A targeted fetch must never pollute the peer folder with half a full run.
  it('calls only: keeps the asked window quarters and nothing else', () => {
    const out = filterSelection(sel, new Set(['calls']), ['2026Q3']);
    expect(out.window).toEqual([q(2026, 3)]);
    for (const k of ['tenKs', 'tenQs', 'proxies', 'releases', 'regFd', 'skipped', 'releaseWindow']) expect(out[k]).toEqual([]);
  });
  it('10-K for a quarter keeps the 10-K of that fiscal year only', () => {
    const out = filterSelection(sel, new Set(['10-K']), ['2025Q2']);
    expect(out.tenKs.map((f) => f.fy)).toEqual([2025]);
    expect(out.tenQs).toEqual([]);
  });
  it('10-Q and releases keep only the asked quarters, and the release window shrinks to them', () => {
    const out = filterSelection(sel, new Set(['10-Q', 'releases']), ['2026Q2']);
    expect(out.tenQs.map((f) => f.reportDate)).toEqual(['2026-06-30']);
    expect(out.releases.map((f) => f.accn)).toEqual(['a2']);
    expect(out.releaseWindow).toEqual([q(2026, 2)]);
    expect(out.window).toEqual([]);
  });
});

describe('localStatus', () => {
  // Local first: a document already on disk is returned, not fetched again.
  it('marks found items with their files on disk as local, everything else todo', () => {
    const dir = mkdtempSync(join(tmpdir(), 'only-'));
    mkdirSync(join(dir, 'Earnings Calls', '_md'), { recursive: true });
    writeFileSync(join(dir, 'Earnings Calls', '_md', 'c.md'), 'x');
    const manifest = { items: {
      'call:2026Q3': { status: 'found', files: ['Earnings Calls/_md/c.md'] },
      'call:2026Q2': { status: 'found', files: ['Earnings Calls/_md/gone.md'] },
      'call:2026Q1': { status: 'missing', files: [] },
    } };
    expect(localStatus(manifest, dir, ['call:2026Q3', 'call:2026Q2', 'call:2026Q1', 'call:2025Q4'])).toEqual({
      'call:2026Q3': 'local', 'call:2026Q2': 'todo', 'call:2026Q1': 'todo', 'call:2025Q4': 'todo',
    });
  });
});

describe('requestedIds', () => {
  it('names the manifest ids a filtered selection will write, so the run can report on exactly those', () => {
    const out = filterSelection(sel, new Set(['calls', '10-Q', '10-K']), ['2026Q3', '2025Q4']);
    expect(requestedIds(out)).toEqual(['10-K:2025-12-31', '10-Q:2026-09-30', 'call:2026Q3', 'call:2025Q4']);
  });
});
