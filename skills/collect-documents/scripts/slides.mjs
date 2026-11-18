// Slide decks (earnings decks, investor events) are PDFs whose charts and
// tables are often pictures, so text extraction alone loses the numbers.
// Claude reads each slide image and writes it as Markdown; this script does
// everything around that and checks every number Claude wrote against the
// slide's own text layer + OCR.
// CLI (used by SKILL.md step 4; requires poppler + tesseract from Homebrew):
//   node slides.mjs pending <dir>        JSON list of decks without a Markdown copy
//   node slides.mjs prep <dir> <id>      render slides + text/OCR into <dir>/.slides/<id>/
//   node slides.mjs finish <dir> <id>    check numbers, write <Category>/_md/<name>.md, register it
//   node slides.mjs recheck <dir> <id>   report: redo the dropped-text check after a hand fix

import { existsSync, mkdirSync, readFileSync, readdirSync, rmSync, writeFileSync, realpathSync } from 'node:fs';
import { basename, dirname, join } from 'node:path';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { pathToFileURL } from 'node:url';
import { loadManifest, saveManifest, safeName } from './manifest.mjs';

const run = promisify(execFile);
export const SLIDE_CATEGORIES = ['Investor Decks', 'Investor Events', 'Sellside Research'];
// Sell-side reports are mostly prose, so each page is also checked for dropped
// text, and legal-disclosure pages are written as this one line instead.
export const REPORT_CATEGORIES = ['Sellside Research'];
export const DISCLOSURES = '[Disclosures page: legal text not converted; see the PDF]';
// A page that mixes content with legal text keeps the content and says so with this line.
export const LEGAL_SKIPPED = '[Legal text not converted; see the PDF]';
// Web pages printed to PDF can run to dozens of empty pages; nobody needs to read those.
export const BLANK = '[Blank page]';
const MIN_COVERAGE = 0.95;
const OCR_WORKERS = 4;

// Found deck/event PDFs with no Markdown copy yet (HTML-sourced items already have one).
export function pendingDecks(dir, m) {
  return Object.entries(m.items)
    .filter(([, e]) => SLIDE_CATEGORIES.includes(e.category) && e.status === 'found')
    .filter(([, e]) => !(e.files || []).some((f) => f.endsWith('.md')))
    .map(([id, e]) => ({ id, pdf: (e.files || []).find((f) => f.toLowerCase().endsWith('.pdf')) }))
    .filter((d) => d.pdf && existsSync(join(dir, d.pdf)))
    .map((d) => ({ ...d, md: mdPath(d.pdf), work: workDir(dir, d.id) }));
}

// Markdown sits in `_md/` beside its PDF (for sell-side, inside the report's tier folder).
export const mdPath = (pdf) => join(dirname(pdf), '_md', basename(pdf).replace(/\.pdf$/i, '.md'));
export const workDir = (dir, id) => join(dir, '.slides', safeName(id).replace(/[^\w.-]/g, '_'));
export const pageName = (n) => `page-${String(n).padStart(3, '0')}`;

// Number tokens worth checking: anything with a decimal point, a % sign, or a
// value of 10+. Lone small integers are footnote marks, list numbers, counts;
// bare years (2025) are headings, often drawn as pictures OCR can't read.
export function numberTokens(text) {
  const out = [];
  for (const m of text.matchAll(/\d[\d,]*(?:\.\d+)?%?/g)) {
    const raw = m[0];
    const plain = raw.replace(/[,%]/g, '');
    const v = Number(plain);
    if (Number.isNaN(v)) continue;
    if (!raw.includes('.') && !raw.endsWith('%') && v < 10) continue;
    if (/^(19|20)\d\d$/.test(raw)) continue;
    out.push({ raw, key: String(v) });
  }
  return out;
}

const textLayer = (source) => source.split('----- OCR -----')[0].replace(/-\n\s*/g, '');
const normLine = (l) => l.replace(/\d/g, '').replace(/\s+/g, ' ').trim().toLowerCase();

// Running headers and footers (analyst names, copyright lines) repeat on most
// pages; the readers skip them, so the dropped-text check must too.
export function furnitureLines(sources) {
  if (sources.length < 3) return new Set();
  const count = new Map();
  for (const src of sources) {
    for (const l of new Set(textLayer(src).split('\n').map(normLine).filter(Boolean))) count.set(l, (count.get(l) || 0) + 1);
  }
  const need = Math.max(2, sources.length / 2);
  return new Set([...count].filter(([, n]) => n >= need).map(([l]) => l));
}

// Words of the page's own text layer (OCR and page furniture excluded) that the
// Markdown left out. Only words of 5+ letters count, so stray fragments don't.
export function missingWords(md, source, furniture = new Set()) {
  const words = (t) => (t.toLowerCase().match(/[a-z]{5,}/g) || []);
  const have = new Set(words(md));
  const text = words(textLayer(source).split('\n').filter((l) => !furniture.has(normLine(l))).join('\n'));
  const gone = text.filter((w) => !have.has(w));
  return { total: text.length, missing: gone.length, coverage: text.length ? 1 - gone.length / text.length : 1 };
}

// Numbers in Claude's Markdown that appear nowhere in the slide's text or OCR.
// A flag means "code couldn't confirm it", not "wrong": OCR misreads charts.
export function unconfirmed(md, source) {
  const known = new Set(
    [...source.matchAll(/\d[\d,]*(?:\.\d+)?/g)].map((m) => String(Number(m[0].replace(/,/g, '')))),
  );
  const seen = new Set();
  return numberTokens(md).filter((t) => !known.has(t.key) && !seen.has(t.raw) && seen.add(t.raw));
}

export function assemble({ title, pdfName, pages, unit = 'slide' }) {
  const flagged = pages.reduce((n, p) => n + p.flags.length, 0);
  const thin = pages.filter((p) => p.words && p.words.coverage < MIN_COVERAGE).length;
  const Unit = unit[0].toUpperCase() + unit.slice(1);
  const lines = [
    `# ${title}`,
    '',
    `Converted from \`${pdfName}\` (${pages.length} ${unit}s) by reading each ${unit} image. Every number was checked against the PDF's text layer and OCR: ${flagged ? `${flagged} could not be confirmed and are listed under their ${unit}; check those against the PDF.` : 'all were confirmed.'}`,
    '',
  ];
  if (unit === 'page') lines.splice(3, 0, `Every page's text was checked against the PDF's text layer: ${thin ? `${thin} page(s) may have dropped text and are marked; check those against the PDF.` : 'nothing was dropped.'}`, '');
  for (const p of pages) {
    if (p.md.trim() === BLANK) continue;
    lines.push(`## ${Unit} ${p.n}`, '', p.md.trim(), '');
    if (p.flags.length) lines.push(`> Unconfirmed numbers (not found in this ${unit}'s text or OCR): ${p.flags.map((f) => f.raw).join(', ')}`, '');
    if (p.words && p.words.coverage < MIN_COVERAGE) lines.push(`> Possibly dropped text: ${p.words.missing} of ${p.words.total} words in this page's text layer are not in the Markdown.`, '');
  }
  return lines.join('\n');
}

async function pageCount(pdf) {
  const { stdout } = await run('pdfinfo', [pdf]);
  return Number(/^Pages:\s+(\d+)/m.exec(stdout)?.[1] || 0);
}

async function prepPage(pdf, work, n) {
  const base = join(work, pageName(n));
  if (existsSync(`${base}.txt`)) return;
  await run('pdftoppm', ['-png', '-singlefile', '-scale-to', '1800', '-f', String(n), '-l', String(n), pdf, base]);
  const { stdout: text } = await run('pdftotext', ['-layout', '-f', String(n), '-l', String(n), pdf, '-']);
  // Two OCR passes catch different chart labels: normal reading order, and
  // sparse text (scattered labels) on a sharper 300 dpi grayscale render;
  // grayscale is what lets OCR read numbers on coloured table-row shading.
  const ocr = (args) => run('tesseract', args, { maxBuffer: 1 << 24 }).then((r) => r.stdout, () => '');
  const pass1 = await ocr([`${base}.png`, '-']);
  await run('pdftoppm', ['-png', '-gray', '-singlefile', '-r', '300', '-f', String(n), '-l', String(n), pdf, `${base}-hi`]);
  const pass2 = await ocr([`${base}-hi.png`, '-', '--psm', '11']);
  rmSync(`${base}-hi.png`, { force: true });
  writeFileSync(`${base}.txt`, `${text}\n----- OCR -----\n${pass1}\n----- OCR (sparse) -----\n${pass2}`);
  if (!/[a-z0-9]/i.test(text + pass1 + pass2)) writeFileSync(`${base}.md`, `${BLANK}\n`);
}

export async function prep(dir, id) {
  const deck = pendingDecks(dir, loadManifest(dir)).find((d) => d.id === id);
  if (!deck) throw new Error(`${id} is not a pending deck`);
  const pdf = join(dir, deck.pdf);
  const pages = await pageCount(pdf);
  if (!pages) throw new Error(`could not read page count: ${deck.pdf}`);
  mkdirSync(deck.work, { recursive: true });
  const queue = Array.from({ length: pages }, (_, i) => i + 1);
  await Promise.all(Array.from({ length: OCR_WORKERS }, async () => {
    while (queue.length) await prepPage(pdf, deck.work, queue.shift());
  }));
  const blank = readdirSync(deck.work).filter((f) => /^page-\d+\.md$/.test(f));
  return { ...deck, pages, toRead: Array.from({ length: pages }, (_, i) => i + 1).filter((n) => !blank.includes(`${pageName(n)}.md`)) };
}

const wordCheck = (report, md, source, furniture) =>
  (report && md.trim() !== DISCLOSURES && !md.includes(LEGAL_SKIPPED) ? missingWords(md, source, furniture) : null);

// Re-run the dropped-text check on a finished report against its PDF's text
// layer (after a page was fixed by hand). Number flags are kept as they were.
export async function recheck(dir, id) {
  const m = loadManifest(dir);
  const e = m.items[id];
  const mdFile = (e?.files || []).find((f) => f.endsWith('.md'));
  if (!REPORT_CATEGORIES.includes(e?.category) || !mdFile) throw new Error(`${id} is not a converted report`);
  const pdf = join(dir, e.files.find((f) => f.toLowerCase().endsWith('.pdf')));
  const text = readFileSync(join(dir, mdFile), 'utf8');
  const parts = text.split(/^## Page (\d+)\n/m);
  const pages = [];
  for (let i = 1; i < parts.length; i += 2) {
    const lines = parts[i + 1].trim().split('\n');
    const flagLine = lines.find((l) => l.startsWith('> Unconfirmed numbers'));
    const md = lines.filter((l) => !l.startsWith('> Unconfirmed numbers') && !l.startsWith('> Possibly dropped text')).join('\n').trim();
    const flags = flagLine ? flagLine.split(': ').slice(1).join(': ').split(', ').map((raw) => ({ raw })) : [];
    pages.push({ n: Number(parts[i]), md, flags });
  }
  const sources = [];
  for (const p of pages) sources.push((await run('pdftotext', ['-layout', '-f', String(p.n), '-l', String(p.n), pdf, '-'])).stdout);
  const furniture = furnitureLines(sources);
  pages.forEach((p, i) => { p.words = wordCheck(true, p.md, sources[i], furniture); });
  const title = /^# (.*)$/m.exec(text)[1];
  writeFileSync(join(dir, mdFile), assemble({ title, pdfName: basename(pdf), pages, unit: 'page' }));
  return { id, md: mdFile, thinPages: pages.filter((p) => p.words && p.words.coverage < MIN_COVERAGE).map((p) => p.n) };
}

export function finish(dir, id) {
  const m = loadManifest(dir);
  const deck = pendingDecks(dir, m).find((d) => d.id === id);
  if (!deck) throw new Error(`${id} is not a pending deck`);
  const report = REPORT_CATEGORIES.includes(m.items[id].category);
  const txts = readdirSync(deck.work).filter((f) => /^page-\d+\.txt$/.test(f)).sort();
  const missing = txts.filter((f) => !existsSync(join(deck.work, f.replace('.txt', '.md'))));
  if (!txts.length || missing.length) throw new Error(`slides not written yet: ${missing.join(', ') || '(none prepared)'}`);
  const sources = txts.map((f) => readFileSync(join(deck.work, f), 'utf8'));
  const furniture = report ? furnitureLines(sources) : new Set();
  const pages = txts.map((f, i) => {
    const md = readFileSync(join(deck.work, f.replace('.txt', '.md')), 'utf8');
    return { n: Number(f.match(/\d+/)[0]), md, flags: unconfirmed(md, sources[i]), words: wordCheck(report, md, sources[i], furniture) };
  });
  const pdfName = basename(deck.pdf);
  mkdirSync(join(dir, deck.md, '..'), { recursive: true });
  writeFileSync(join(dir, deck.md), assemble({ title: pdfName.replace(/\.pdf$/i, ''), pdfName, pages, unit: report ? 'page' : 'slide' }));
  const entry = m.items[id];
  entry.files = [...entry.files, deck.md];
  entry.note = [entry.note, `Markdown read from ${report ? 'page' : 'slide'} images`].filter(Boolean).join('; ');
  saveManifest(dir, m);
  rmSync(deck.work, { recursive: true, force: true });
  return { id, md: deck.md, slides: pages.length, unconfirmed: pages.reduce((n, p) => n + p.flags.length, 0), thinPages: pages.filter((p) => p.words && p.words.coverage < MIN_COVERAGE).map((p) => p.n) };
}

async function cli() {
  const [cmd, dir, id] = process.argv.slice(2);
  const die = (msg) => { process.stderr.write(`slides: ${msg}\n`); process.exit(1); };
  if (!dir || !existsSync(dir)) die('usage: slides.mjs pending|prep|finish <dir> [id]');
  try {
    if (cmd === 'pending') console.log(JSON.stringify(pendingDecks(dir, loadManifest(dir)), null, 2));
    else if (cmd === 'prep' && id) console.log(JSON.stringify(await prep(dir, id)));
    else if (cmd === 'finish' && id) console.log(JSON.stringify(finish(dir, id)));
    else if (cmd === 'recheck' && id) console.log(JSON.stringify(await recheck(dir, id)));
    else die('usage: slides.mjs pending|prep|finish <dir> [id]');
  } catch (e) {
    die(e.message);
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(realpathSync(process.argv[1])).href) cli();
