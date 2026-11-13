import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { mkdtempSync, mkdirSync, writeFileSync, rmSync, readFileSync, existsSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { loadManifest, saveManifest, setItem } from '../scripts/manifest.mjs';
import { pendingDecks, numberTokens, unconfirmed, assemble, finish, workDir, mdPath , missingWords, furnitureLines } from '../scripts/slides.mjs';

let dir;
beforeEach(() => { dir = mkdtempSync(join(tmpdir(), 'gather-slides-')); });
afterEach(() => { rmSync(dir, { recursive: true, force: true }); });

function addDeck(m, id, category, files) {
  mkdirSync(join(dir, category, '_md'), { recursive: true });
  for (const f of files) writeFileSync(join(dir, f), 'x');
  setItem(m, id, { category, label: id, status: 'found', files, by: 'agent' });
}

describe('pendingDecks (only slide PDFs that still lack a Markdown copy get converted)', () => {
  it('picks deck and event PDFs without Markdown, skips ones that have it and other categories', () => {
    const m = loadManifest(dir);
    addDeck(m, 'deck:2025Q1', 'Investor Decks', ['Investor Decks/Q1 25 X deck.pdf']);
    addDeck(m, 'agent:event-a', 'Investor Events', ['Investor Events/2024-06-13 X Investor Day.pdf']);
    addDeck(m, 'ex:1', 'Investor Decks', ['Investor Decks/_md/E.md', 'Investor Decks/E.pdf']);
    addDeck(m, 'pr:2025Q1', 'Press Releases', ['Press Releases/Q1 25 X release.pdf']);
    setItem(m, 'deck:2014Q1', { category: 'Investor Decks', label: 'gap', status: 'missing', files: [] });
    const ids = pendingDecks(dir, m).map((d) => d.id).sort();
    expect(ids).toEqual(['agent:event-a', 'deck:2025Q1']);
  });
  it('puts the Markdown in the category _md folder like every other document', () => {
    expect(mdPath('Investor Events/2024-06-13 X Investor Day.pdf')).toBe('Investor Events/_md/2024-06-13 X Investor Day.md');
  });
});

describe('numberTokens (which numbers are worth checking)', () => {
  it('keeps money, percents and decimals, skips footnote-sized integers', () => {
    expect(numberTokens('$1,114 grew +8% to 59.4 (note 2) on slide 3').map((t) => t.raw)).toEqual(['1,114', '8%', '59.4']);
  });
  it('skips bare years but still checks a $2,024 amount', () => {
    expect(numberTokens('Total Company 2023 – 2025 YTD: $2,024').map((t) => t.raw)).toEqual(['2,024']);
  });
});

describe('unconfirmed (catches numbers Claude wrote that are not on the slide)', () => {
  const source = 'Revenue $921 $1,004\n----- OCR -----\nmargin 61.8% 63.5%';
  it('confirms numbers found in the text layer or OCR, ignoring commas and % signs', () => {
    expect(unconfirmed('| Q1 | $921 | 61.8% |\n| Q2 | $1004 | 63.5% |', source)).toEqual([]);
  });
  it('flags a number that appears in neither, once', () => {
    expect(unconfirmed('59.4% and 59.4% and $921', source).map((t) => t.raw)).toEqual(['59.4%']);
  });
  it('treats 1,114 and 1114.0 as different from 1,141 (digits matter, formatting does not)', () => {
    expect(unconfirmed('1,141', 'total 1114.0').map((t) => t.raw)).toEqual(['1,141']);
  });
});

describe('assemble', () => {
  it('lists unconfirmed numbers under their own slide so the user knows exactly what to check', () => {
    const md = assemble({ title: 'Q1 25 X deck', pdfName: 'Q1 25 X deck.pdf', pages: [
      { n: 1, md: 'Title slide', flags: [] },
      { n: 2, md: '| a | 59.4% |', flags: [{ raw: '59.4%' }] },
    ] });
    expect(md).toContain('# Q1 25 X deck');
    expect(md).toContain('1 could not be confirmed');
    expect(md.indexOf('Unconfirmed numbers')).toBeGreaterThan(md.indexOf('## Slide 2'));
  });
});

describe('finish (writes the Markdown, registers it, cleans up)', () => {
  it('refuses while any slide is unwritten, so a half-done deck is never registered', () => {
    const m = loadManifest(dir);
    addDeck(m, 'deck:2025Q1', 'Investor Decks', ['Investor Decks/Q1 25 X deck.pdf']);
    saveManifest(dir, m);
    const work = workDir(dir, 'deck:2025Q1');
    mkdirSync(work, { recursive: true });
    writeFileSync(join(work, 'page-001.txt'), 'Revenue $921');
    writeFileSync(join(work, 'page-002.txt'), 'margin 61.8%');
    writeFileSync(join(work, 'page-001.md'), 'Revenue $921');
    expect(() => finish(dir, 'deck:2025Q1')).toThrow(/page-002/);

    writeFileSync(join(work, 'page-002.md'), 'Margin 61.8%, then 59.4%');
    const r = finish(dir, 'deck:2025Q1');
    expect(r).toMatchObject({ slides: 2, unconfirmed: 1 });
    const out = readFileSync(join(dir, 'Investor Decks/_md/Q1 25 X deck.md'), 'utf8');
    expect(out).toContain('## Slide 2');
    expect(loadManifest(dir).items['deck:2025Q1'].files).toContain('Investor Decks/_md/Q1 25 X deck.md');
    expect(existsSync(work)).toBe(false);
    expect(pendingDecks(dir, loadManifest(dir))).toEqual([]);
  });
});

describe('missingWords (sell-side pages are prose; catches a paragraph the reader skipped)', () => {
  const src = 'We maintain our BUY rating and raise the target price.\n----- OCR -----\nunrelated ocrnoise words';
  it('full coverage when every text-layer word is in the Markdown, ignoring OCR noise', () => {
    expect(missingWords('We maintain our **BUY** rating and raise the target price.', src).coverage).toBe(1);
  });
  it('drops below the bar when a sentence is missing', () => {
    expect(missingWords('We maintain our BUY rating.', src).coverage).toBeLessThan(0.95);
  });
});

describe('furnitureLines (running headers are skipped on purpose, so they must not count as dropped text)', () => {
  it('finds lines repeated on most pages, ignoring page numbers', () => {
    const pages = ['Robbie Marcus AC\nPage 1\nBody one', 'Robbie Marcus AC\nPage 2\nBody two', 'Robbie Marcus AC\nPage 3\nBody three'];
    const f = furnitureLines(pages);
    expect(f.has('robbie marcus ac')).toBe(true);
    expect(f.has('page')).toBe(true);
    expect(missingWords('Body three', pages[2], f).coverage).toBe(1);
  });
  it('treats nothing as furniture in a one- or two-page report', () => {
    expect(furnitureLines(['a header', 'a header']).size).toBe(0);
  });
});

describe('assemble with blank pages', () => {
  it('leaves out blank pages so a printed web page reads as one document', () => {
    const md = assemble({ title: 'T', pdfName: 't.pdf', unit: 'page', pages: [{ n: 1, md: 'Text', flags: [] }, { n: 2, md: '[Blank page]\n', flags: [] }] });
    expect(md).toContain('## Page 1');
    expect(md).not.toContain('## Page 2');
  });
});

