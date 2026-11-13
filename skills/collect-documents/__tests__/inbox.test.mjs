import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { mkdtempSync, mkdirSync, writeFileSync, existsSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { pendingReports, register, reportName, tidy, KINDS, TIERS } from '../scripts/inbox.mjs';

const CATEGORY = KINDS.sellside.category;

// Smallest PDF poppler reads: one page with the given text.
function tinyPdf(text) {
  const stream = `BT /F1 12 Tf 72 720 Td (${text}) Tj ET`;
  const objs = [
    '<< /Type /Catalog /Pages 2 0 R >>',
    '<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
    '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>',
    `<< /Length ${stream.length} >>\nstream\n${stream}\nendstream`,
    '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
  ];
  let body = '%PDF-1.4\n';
  const offsets = objs.map((o, i) => { const at = body.length; body += `${i + 1} 0 obj\n${o}\nendobj\n`; return at; });
  const xref = body.length;
  body += `xref\n0 ${objs.length + 1}\n0000000000 65535 f \n${offsets.map((o) => `${String(o).padStart(10, '0')} 00000 n \n`).join('')}`;
  return `${body}trailer\n<< /Size ${objs.length + 1} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`;
}

let dir;
const m = () => ({ items: {} });
beforeEach(() => {
  dir = mkdtempSync(join(tmpdir(), 'sellside-'));
  mkdirSync(join(dir, CATEGORY));
  writeFileSync(join(dir, CATEGORY, 'pdfdownload.pdf'), tinyPdf('ARGUS A6 Report'));
});
afterEach(() => rmSync(dir, { recursive: true, force: true }));

describe('sell-side inbox (the user drops PDFs in; they get filed year-first like everything else)', () => {
  it('lists unregistered PDFs with their first-page text so the firm can be identified', () => {
    const [p] = pendingReports(dir, m());
    expect(p).toMatchObject({ file: 'pdfdownload.pdf', pages: 1 });
    expect(p.firstPage).toContain('ARGUS');
  });

  it('names reports date-first so the folder sorts chronologically', () => {
    expect(reportName({ date: '2026-10-29', firm: 'JPM', type: 'earnings recap', title: 'Overall Good 3Q' }))
      .toBe('2026-10-29 JPM earnings recap - Overall Good 3Q.pdf');
    expect(reportName({ date: '2026-11-04', firm: 'Argus', type: 'quant rating' })).toBe('2026-11-04 Argus quant rating.pdf');
  });

  it('renames, registers and remembers the original name; a registered report is no longer pending', () => {
    const man = m();
    register(dir, man, [{ file: 'pdfdownload.pdf', date: '2026-11-04', firm: 'Argus', type: 'quant rating', title: 'A6' }]);
    expect(existsSync(join(dir, CATEGORY, TIERS[2], '2026-11-04 Argus quant rating - A6.pdf'))).toBe(true);
    const e = Object.values(man.items)[0];
    expect(e.note).toContain('pdfdownload.pdf');
    expect(pendingReports(dir, man)).toEqual([]);
  });

  it('rejects the whole plan on one bad entry, so the folder is never half renamed', () => {
    writeFileSync(join(dir, CATEGORY, 'b.pdf'), tinyPdf('x'));
    expect(() => register(dir, m(), [
      { file: 'pdfdownload.pdf', date: '2026-11-04', firm: 'Argus', type: 'quant rating' },
      { file: 'b.pdf', date: 'Nov 4', firm: 'X', type: 'quant rating' },
    ])).toThrow(/date/);
    expect(existsSync(join(dir, CATEGORY, 'pdfdownload.pdf'))).toBe(true);
  });

  it('only accepts the report types on the firm tier list', () => {
    expect(() => register(dir, m(), [{ file: 'pdfdownload.pdf', date: '2026-11-04', firm: 'Argus', type: 'misc' }])).toThrow(/type/);
  });
});

describe('source tiers (a J.P. Morgan note outweighs a Seeking Alpha piece, which outweighs a news story)', () => {
  it('files a bank note in tier 1 by its ranked firm, and records the tier for the street research', () => {
    const man = m();
    register(dir, man, [{ file: 'pdfdownload.pdf', date: '2026-10-29', firm: 'JPM', type: 'earnings recap', title: 'Good 3Q' }]);
    expect(existsSync(join(dir, CATEGORY, TIERS[1], '2026-10-29 JPM earnings recap - Good 3Q.pdf'))).toBe(true);
    expect(Object.values(man.items)[0].tier).toBe(1);
  });

  it('refuses a source the firm ranking does not list unless the plan gives its tier', () => {
    expect(() => register(dir, m(), [{ file: 'pdfdownload.pdf', date: '2026-11-01', firm: 'Seeking Alpha', type: 'article' }])).toThrow(/tier/);
    const man = m();
    register(dir, man, [{ file: 'pdfdownload.pdf', date: '2026-11-01', firm: 'Seeking Alpha', type: 'article', tier: 3, title: 'X' }]);
    expect(existsSync(join(dir, CATEGORY, TIERS[3], '2026-11-01 Seeking Alpha article - X.pdf'))).toBe(true);
  });

  it('moves reports filed before tiers (PDF and Markdown) into their tier folder', () => {
    const man = m();
    mkdirSync(join(dir, CATEGORY, '_md'));
    writeFileSync(join(dir, CATEGORY, '_md', 'pdfdownload.md'), '# x');
    man.items['sell:x'] = { category: CATEGORY, firm: 'Morningstar', label: 'pdfdownload', status: 'found',
      files: [`${CATEGORY}/pdfdownload.pdf`, `${CATEGORY}/_md/pdfdownload.md`] };
    tidy(dir, man);
    expect(existsSync(join(dir, CATEGORY, TIERS[2], 'pdfdownload.pdf'))).toBe(true);
    expect(existsSync(join(dir, CATEGORY, TIERS[2], '_md', 'pdfdownload.md'))).toBe(true);
    expect(man.items['sell:x'].files[1]).toBe(`${CATEGORY}/${TIERS[2]}/_md/pdfdownload.md`);
  });
});
