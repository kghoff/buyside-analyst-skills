import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { mkdtempSync, writeFileSync, rmSync, readFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { execFileSync } from 'node:child_process';
import {
  loadManifest, saveManifest, setItem, isDone, renderMarkdown, visibleItems, createClaimer, syncPlaceholder,
} from '../scripts/manifest.mjs';

const CLI = new URL('../scripts/manifest.mjs', import.meta.url).pathname;
let dir;
beforeEach(() => { dir = mkdtempSync(join(tmpdir(), 'gather-test-')); });
afterEach(() => { rmSync(dir, { recursive: true, force: true }); });

describe('isDone (drives incremental reruns: done items cost zero network calls)', () => {
  it('is true only when status is found and every file still exists', () => {
    writeFileSync(join(dir, 'a.md'), 'x');
    const m = loadManifest(dir);
    setItem(m, '10-K:2025', { category: '10-Ks', label: 'X 2025 10-K', status: 'found', files: ['a.md'] });
    expect(isDone(dir, m.items['10-K:2025'])).toBe(true);
    rmSync(join(dir, 'a.md'));
    expect(isDone(dir, m.items['10-K:2025'])).toBe(false);
  });
  it('retries missing and deferred items', () => {
    expect(isDone(dir, { status: 'missing', files: [] })).toBe(false);
    expect(isDone(dir, { status: 'deferred', files: [] })).toBe(false);
    expect(isDone(dir, undefined)).toBe(false);
  });
});

describe('loadManifest', () => {
  // A half-written manifest must not be mistaken for "nothing collected yet",
  // or the next save would silently wipe every recorded item.
  it('throws on a corrupt manifest instead of treating it as empty', () => {
    writeFileSync(join(dir, '_manifest.json'), '{"items": {"10-K:20');
    expect(() => loadManifest(dir)).toThrow(/corrupt manifest/);
  });
  // A manifest saved without items (e.g. hand-edited) must not crash setItem.
  it('normalizes a missing items field to an empty object', () => {
    writeFileSync(join(dir, '_manifest.json'), '{"ticker": "X"}');
    expect(loadManifest(dir).items).toEqual({});
  });
  it('leaves no temp file behind after saving', () => {
    saveManifest(dir, { ticker: 'X', items: {} });
    expect(readFileSync(join(dir, '_manifest.json'), 'utf8')).toContain('"ticker": "X"');
    expect(() => readFileSync(join(dir, '_manifest.json.tmp'))).toThrow();
  });
});

describe('renderMarkdown', () => {
  it('lists every gap with its reason and hides internal index entries', () => {
    const m = { ticker: 'X', company: 'X Corp', cik: '1', items: {} };
    setItem(m, 'call:2025Q1', { category: 'Earnings Calls', label: 'Q1 25 X call', status: 'deferred', files: [], reason: 'AV limit' });
    setItem(m, '8k:abc', { category: '_index', label: '8-K abc', status: 'found', files: [] });
    const md = renderMarkdown(m);
    expect(md).toContain('## Gaps');
    expect(md).toContain('| Earnings Calls | Q1 25 X call | deferred | AV limit |');
    expect(md).not.toContain('8-K abc');
  });
  // FAIL LOUD: a failed 8-K index fetch means its exhibits were never seen,
  // so it must show up as a gap instead of hiding under the internal category.
  it('shows a non-found index entry as an 8-K exhibits gap', () => {
    const m = { ticker: 'X', items: {} };
    setItem(m, '8k:abc', { category: '_index', label: '8-K abc', status: 'missing', files: [], reason: 'HTTP 503' });
    const md = renderMarkdown(m);
    expect(md).toContain('| 8-K exhibits | 8-K abc | missing | HTTP 503 |');
    expect(md).not.toContain('_index');
  });
  it('visibleItems hides only found index entries', () => {
    const m = { items: {} };
    setItem(m, '8k:a', { category: '_index', label: 'a', status: 'found' });
    setItem(m, '8k:b', { category: '_index', label: 'b', status: 'missing' });
    expect(visibleItems(m).map((e) => [e.label, e.category])).toEqual([['b', '8-K exhibits']]);
  });
});

describe('createClaimer (two documents must never share a file name)', () => {
  it('keeps the name an id already owns across reruns', () => {
    const claim = createClaimer({ 'ex:1:a.htm': { category: 'Press Releases', label: 'Q1 25 X release' } });
    expect(claim('Press Releases', 'Q1 25 X release', 'ex:1:a.htm', 'a.htm')).toBe('Q1 25 X release');
  });
  it('suffixes a name taken by another id, then numbers it if the suffix is taken too', () => {
    const claim = createClaimer({});
    expect(claim('Press Releases', 'R', 'id1', 's')).toBe('R');
    expect(claim('Press Releases', 'R', 'id2', 's')).toBe('R (s)');
    expect(claim('Press Releases', 'R', 'id3', 's')).toBe('R (s) 2');
    expect(claim('Press Releases', 'R', 'id4', 's')).toBe('R (s) 3');
    expect(claim('Investor Decks', 'R', 'id5', 's')).toBe('R');
  });
  // macOS file systems ignore case and safe() maps ':' to '-', so these collide on disk.
  it('treats names that map to the same file as taken', () => {
    const claim = createClaimer({});
    claim('10-Ks', 'X 10-K:a', 'id1', 's');
    expect(claim('10-Ks', 'x 10-k-a', 'id2', 's')).toBe('x 10-k-a (s)');
  });
});

describe('syncPlaceholder (a window quarter with no SEC document is a gap)', () => {
  const entry = { category: 'Press Releases', label: 'Q1 25 X press release', reason: 'none on EDGAR' };
  it('writes a missing script entry for an uncovered quarter', () => {
    const m = { items: {} };
    syncPlaceholder(m, dir, 'pr:2025Q1', false, entry);
    expect(m.items['pr:2025Q1']).toMatchObject({ ...entry, status: 'missing', files: [], by: 'script' });
  });
  it('never clobbers an entry the IR agent filled', () => {
    writeFileSync(join(dir, 'pr.pdf'), 'x');
    const m = { items: {} };
    setItem(m, 'pr:2025Q1', { ...entry, status: 'found', files: ['pr.pdf'], by: 'agent' });
    syncPlaceholder(m, dir, 'pr:2025Q1', false, entry);
    expect(m.items['pr:2025Q1']).toMatchObject({ status: 'found', by: 'agent' });
  });
  it('removes the placeholder once the SEC has the document', () => {
    const m = { items: {} };
    syncPlaceholder(m, dir, 'pr:2025Q1', false, entry);
    syncPlaceholder(m, dir, 'pr:2025Q1', true, entry);
    expect(m.items['pr:2025Q1']).toBeUndefined();
  });
});

describe('CLI', () => {
  it('lets the agent add an item and re-renders _manifest.md', () => {
    writeFileSync(join(dir, 'deck.pdf'), 'x');
    execFileSync('node', [CLI, 'add', dir, '--id', 'agent:deck-q1', '--category', 'Investor Decks',
      '--label', 'Q1 25 deck', '--status', 'found', '--url', 'https://ir.example.com/q1.pdf', '--file', 'deck.pdf']);
    const m = JSON.parse(readFileSync(join(dir, '_manifest.json'), 'utf8'));
    expect(m.items['agent:deck-q1']).toMatchObject({ by: 'agent', files: ['deck.pdf'] });
    expect(readFileSync(join(dir, '_manifest.md'), 'utf8')).toContain('Q1 25 deck');
  });
  it('refuses to overwrite a found script-produced item', () => {
    const m = loadManifest(dir);
    setItem(m, '10-K:2025', { category: '10-Ks', label: 'X', status: 'found', files: [], by: 'script' });
    saveManifest(dir, m);
    expect(() => execFileSync('node', [CLI, 'add', dir, '--id', '10-K:2025', '--category', '10-Ks',
      '--label', 'X', '--status', 'missing'], { stdio: 'pipe' })).toThrow();
  });
  // The IR agent closes script gaps (e.g. a press release only on the IR site)
  // by registering the same id the script left missing.
  it('lets the agent fill a missing script entry', () => {
    const m = loadManifest(dir);
    setItem(m, 'pr:2024Q1', { category: 'Press Releases', label: 'Q1 24 X press release', status: 'missing', by: 'script' });
    saveManifest(dir, m);
    writeFileSync(join(dir, 'pr.pdf'), 'x');
    execFileSync('node', [CLI, 'add', dir, '--id', 'pr:2024Q1', '--category', 'Press Releases',
      '--label', 'Q1 24 X press release', '--status', 'found', '--file', 'pr.pdf'], { stdio: 'pipe' });
    expect(loadManifest(dir).items['pr:2024Q1']).toMatchObject({ status: 'found', by: 'agent', files: ['pr.pdf'] });
  });
  it('refuses a found item whose file does not exist (fail loud)', () => {
    expect(() => execFileSync('node', [CLI, 'add', dir, '--id', 'agent:x', '--category', 'Investor Events',
      '--label', 'X', '--status', 'found', '--file', 'nope.pdf'], { stdio: 'pipe' })).toThrow();
  });
  it('dies with a clear error when the directory does not exist', () => {
    const bad = join(dir, 'nope');
    for (const args of [['render', bad], ['add', bad, '--id', 'a', '--category', 'c', '--label', 'l', '--status', 'missing']]) {
      let err;
      try { execFileSync('node', [CLI, ...args], { stdio: 'pipe' }); } catch (e) { err = e; }
      expect(err).toBeDefined();
      expect(String(err.stderr)).toContain('no such directory');
      expect(String(err.stderr)).not.toContain('    at ');
    }
  });
});
