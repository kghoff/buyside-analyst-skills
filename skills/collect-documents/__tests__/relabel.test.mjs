import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { mkdtempSync, mkdirSync, writeFileSync, rmSync, existsSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { yearFirst, relabel } from '../scripts/relabel.mjs';
import { loadManifest, saveManifest, setItem } from '../scripts/manifest.mjs';

let dir;
beforeEach(() => { dir = mkdtempSync(join(tmpdir(), 'gather-relabel-')); });
afterEach(() => { rmSync(dir, { recursive: true, force: true }); });

describe('yearFirst (year-first names sort by date in Finder)', () => {
  it('moves the year ahead of the quarter in every kind of label', () => {
    expect(yearFirst('DXCM Q1 14 10-Q')).toBe('DXCM 2014 Q1 10-Q');
    expect(yearFirst('Q4 17 DXCM release 2018-01-08 EX-99.01')).toBe('2017 Q4 DXCM release 2018-01-08 EX-99.01');
    expect(yearFirst('Q1 21 DXCM call.md')).toBe('2021 Q1 DXCM call.md');
  });
  // a rerun must not turn "2014 Q1 10-Q" into "2014 2010 Q1-Q"
  it('leaves year-first and undated names alone', () => {
    for (const s of ['DXCM 2014 Q1 10-Q', '2023 Q1 DXCM deck', 'DXCM 2014 10-K', '2023-06-23 DXCM Investor Day'])
      expect(yearFirst(s)).toBe(s);
  });
});

describe('relabel', () => {
  it('renames files and the manifest together, and a second run changes nothing', () => {
    mkdirSync(join(dir, '10-Qs', '_md'), { recursive: true });
    const files = ['10-Qs/_md/DXCM Q1 14 10-Q.md', '10-Qs/DXCM Q1 14 10-Q.pdf'];
    for (const f of files) writeFileSync(join(dir, f), 'x');
    const m = loadManifest(dir);
    setItem(m, '10-Q:2014-03-31', { category: '10-Qs', label: 'DXCM Q1 14 10-Q', status: 'found', files });
    setItem(m, 'deck:2020Q2', { category: 'Investor Decks', label: 'Q2 20 DXCM deck', status: 'missing', files: [] });
    saveManifest(dir, m);

    expect(relabel(dir)).toEqual({ files: 2, labels: 2 });
    const after = loadManifest(dir).items;
    expect(after['10-Q:2014-03-31'].label).toBe('DXCM 2014 Q1 10-Q');
    expect(after['deck:2020Q2'].label).toBe('2020 Q2 DXCM deck');
    for (const f of after['10-Q:2014-03-31'].files) expect(existsSync(join(dir, f))).toBe(true);
    expect(existsSync(join(dir, files[1]))).toBe(false);
    expect(relabel(dir)).toEqual({ files: 0, labels: 0 });
  });
  it('refuses rather than overwrite a file that already has the new name', () => {
    writeFileSync(join(dir, 'Q1 21 DXCM call.md'), 'old');
    writeFileSync(join(dir, '2021 Q1 DXCM call.md'), 'new');
    saveManifest(dir, loadManifest(dir));
    expect(() => relabel(dir)).toThrow(/already exists/);
    expect(existsSync(join(dir, 'Q1 21 DXCM call.md'))).toBe(true);
  });
});
