// HTML/Markdown → PDF via headless Google Chrome.
// CLI (used by the IR agent): node render.mjs <in.html|in.md> <out.pdf>

import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { stat, readFile, writeFile, mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, basename, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { secContact, loadSettings } from '../../../lib/settings.mjs';

const run = promisify(execFile);

export async function renderHtmlToPdf(htmlPath, pdfPath) {
  // A throwaway profile + mock keychain keeps headless Chrome away from the
  // user's real Chrome profile and macOS keychain (no "Keychain Not Found" prompts).
  const profile = await mkdtemp(join(tmpdir(), 'gather-chrome-'));
  try {
    await run(loadSettings().chrome_path, [
      '--headless=new', '--disable-gpu', '--no-pdf-header-footer',
      `--user-data-dir=${profile}`, '--use-mock-keychain', '--password-store=basic',
      `--user-agent=${secContact()}`, // lets SEC-hosted images in filings load
      '--virtual-time-budget=15000',
      `--print-to-pdf=${resolve(pdfPath)}`,
      pathToFileURL(resolve(htmlPath)).href,
    ], { timeout: 180_000 });
  } finally {
    await rm(profile, { recursive: true, force: true });
  }
  // Chrome can exit 0 without writing; confirm a non-empty file exists.
  if ((await stat(pdfPath)).size === 0) throw new Error('Chrome wrote an empty PDF');
}

// Filings reference images by relative path; point them back at SEC.
export function withBaseHref(html, docUrl) {
  const tag = `<base href="${new URL('.', docUrl).href}">`;
  return /<head[^>]*>/i.test(html) ? html.replace(/<head[^>]*>/i, (m) => `${m}${tag}`) : tag + html;
}

const escapeHtml = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

export function markdownToHtmlDoc(title, md) {
  return `<!doctype html><html><head><meta charset="utf-8"><title>${escapeHtml(title)}</title>
<style>body{font:11pt/1.5 Georgia,serif;margin:2cm}pre{white-space:pre-wrap;font:inherit}</style></head>
<body><pre>${escapeHtml(md)}</pre></body></html>`;
}

async function cli() {
  const [input, output] = process.argv.slice(2);
  if (!input || !output) {
    process.stderr.write('usage: render.mjs <in.html|in.md> <out.pdf>\n');
    process.exit(1);
  }
  let htmlPath = input;
  let tmp;
  if (/\.md$/i.test(input)) {
    tmp = await mkdtemp(join(tmpdir(), 'gather-render-'));
    htmlPath = join(tmp, 'doc.html');
    await writeFile(htmlPath, markdownToHtmlDoc(basename(input, '.md'), await readFile(input, 'utf8')));
  }
  try {
    await renderHtmlToPdf(htmlPath, output);
  } finally {
    if (tmp) await rm(tmp, { recursive: true, force: true });
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  cli().catch((e) => { process.stderr.write(`render: ${e.message}\n`); process.exit(1); });
}
