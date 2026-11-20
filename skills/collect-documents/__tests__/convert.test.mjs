import { describe, it, expect } from 'vitest';
import { mkdtempSync, writeFileSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { execFileSync } from 'node:child_process';
import { cleanEdgarHtml, convertToMarkdown } from '../scripts/convert.mjs';

describe('EDGAR HTML → Markdown', () => {
  const html = `<html><body>
    <ix:header>hidden machine metadata</ix:header>
    <p style="color:red">Revenue was <ix:nonFraction name="us-gaap:Revenues">1,234</ix:nonFraction> million</p>
    <table><tr><td>Segment</td><td>Q1</td></tr><tr><td>Auto</td><td>100</td></tr></table>
  </body></html>`;
  const md = convertToMarkdown(cleanEdgarHtml(html));

  it('keeps visible iXBRL numbers and drops hidden metadata', () => {
    expect(md).toContain('Revenue was 1,234 million');
    expect(md).not.toContain('hidden machine metadata');
  });
  it('keeps financial tables as Markdown tables (segment data must survive)', () => {
    expect(md).toContain('| Segment | Q1 |');
    expect(md).toContain('| --- | --- |');
    expect(md).toContain('| Auto | 100 |');
  });
  it('survives an empty <table> (old EDGAR 10-Qs have them; one crash loses the whole filing)', () => {
    const out = convertToMarkdown(cleanEdgarHtml(
      '<p>Net sales rose</p><table></table><table><tr><td>Sales</td><td>1,000</td></tr></table>'));
    expect(out).toContain('Net sales rose');
    expect(out).toContain('| Sales | 1,000 |');
  });
});

// The IR agent converts saved HTML pages with this CLI so it never types out
// document text itself.
describe('convert CLI', () => {
  it('writes a source comment plus the converted Markdown', () => {
    const dir = mkdtempSync(join(tmpdir(), 'gather-test-'));
    try {
      writeFileSync(join(dir, 'page.html'), '<html><body><h1>Investor Day</h1><p>Hello <b>all</b></p></body></html>');
      execFileSync('node', [new URL('../scripts/convert.mjs', import.meta.url).pathname, join(dir, 'page.html'), join(dir, 'page.md')]);
      expect(readFileSync(join(dir, 'page.md'), 'utf8')).toBe('<!-- source: local file -->\n\n# Investor Day\n\nHello **all**\n');
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  // Markdown copies go in a category's `_md/` subfolder, which may not exist yet.
  it('creates the output folder when it is missing', () => {
    const dir = mkdtempSync(join(tmpdir(), 'gather-test-'));
    try {
      writeFileSync(join(dir, 'page.html'), '<html><body><p>Hi</p></body></html>');
      const out = join(dir, 'Investor Events', '_md', 'page.md');
      execFileSync('node', [new URL('../scripts/convert.mjs', import.meta.url).pathname, join(dir, 'page.html'), out]);
      expect(readFileSync(out, 'utf8')).toContain('Hi');
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });
});
