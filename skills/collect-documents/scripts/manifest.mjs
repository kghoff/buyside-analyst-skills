// _manifest.json is the source of truth for what /collect-documents has collected;
// _manifest.md is a human-readable rendering of it.
// CLI (used by the IR agent):
//   node manifest.mjs add <dir> --id ID --category CAT --label LABEL --status STATUS
//        [--url URL] [--file REL_PATH ...] [--reason TEXT] [--note TEXT]
//   node manifest.mjs render <dir>

import { existsSync, readFileSync, writeFileSync, renameSync } from 'node:fs';
import { join } from 'node:path';
import { parseArgs } from 'node:util';
import { pathToFileURL } from 'node:url';

export const STATUSES = ['found', 'missing', 'deferred', 'skipped'];

export function loadManifest(dir) {
  const path = join(dir, '_manifest.json');
  if (!existsSync(path)) return { items: {} };
  let m;
  try {
    m = JSON.parse(readFileSync(path, 'utf8'));
  } catch (e) {
    // Never treat a damaged manifest as empty: the next save would wipe it.
    throw new Error(`corrupt manifest: ${path} (${e.message})`);
  }
  m.items ||= {};
  return m;
}

export function setItem(m, id, entry) {
  m.items[id] = { files: [], ...entry, fetched_at: new Date().toISOString() };
}

export function isDone(dir, entry) {
  return entry?.status === 'found' && (entry.files || []).every((f) => existsSync(join(dir, f)));
}

// Items worth showing a person. Found 8-K index entries are bookkeeping, but a
// failed one means its exhibits were never seen, so it shows as a gap.
export function visibleItems(m) {
  return Object.values(m.items)
    .filter((e) => e.category !== '_index' || e.status !== 'found')
    .map((e) => (e.category === '_index' ? { ...e, category: '8-K exhibits' } : e));
}

export const safeName = (s) => s.replace(/[/:\\]/g, '-');

// Reserve one file name per id. Reruns keep the names already in the manifest;
// a name another id holds gets ` (suffix)`, then ` 2`, ` 3`... until free.
// Keys are case-folded because macOS file names ignore case.
export function createClaimer(items) {
  const key = (category, label) => `${category}/${safeName(label).toLowerCase()}`;
  const owners = new Map(Object.entries(items || {}).map(([id, e]) => [key(e.category, e.label), id]));
  const free = (category, label, id) => [undefined, id].includes(owners.get(key(category, label)));
  return function claim(category, label, id, suffix) {
    let final = free(category, label, id) ? label : `${label} (${suffix})`;
    for (let n = 2; !free(category, final, id); n++) final = `${label} (${suffix}) ${n}`;
    owners.set(key(category, final), id);
    return final;
  };
}

// Placeholder gap for a window quarter the SEC has no document for. The IR
// agent may fill it (same id); a later run that finds the document removes it.
export function syncPlaceholder(m, dir, id, covered, entry) {
  const cur = m.items[id];
  if (covered) {
    if (cur?.by === 'script') delete m.items[id];
    return;
  }
  if (!isDone(dir, cur)) setItem(m, id, { ...entry, status: 'missing', files: [], by: 'script' });
}

const cell = (s) => String(s ?? '').replace(/\|/g, '/').replace(/\n/g, ' ');

export function renderMarkdown(m) {
  const items = visibleItems(m);
  const count = (s) => items.filter((e) => e.status === s).length;
  const lines = [
    `# ${m.ticker} research folder`,
    '',
    `${m.company || ''} · CIK ${m.cik || '?'} · updated ${(m.updated_at || '').slice(0, 10)}`,
    '',
    `**Found ${count('found')}** · Missing ${count('missing')} · Deferred ${count('deferred')} · Skipped ${count('skipped')}`,
    '',
  ];
  const gaps = items.filter((e) => e.status !== 'found');
  if (gaps.length) {
    lines.push('## Gaps', '', '| Category | Item | Status | Reason |', '| --- | --- | --- | --- |');
    for (const e of gaps) lines.push(`| ${cell(e.category)} | ${cell(e.label)} | ${e.status} | ${cell(e.reason)} |`);
    lines.push('');
  }
  for (const cat of [...new Set(items.map((e) => e.category))]) {
    lines.push(`## ${cat}`, '', '| Item | Status | Source | Notes |', '| --- | --- | --- | --- |');
    for (const e of items.filter((x) => x.category === cat).sort((a, b) => a.label.localeCompare(b.label))) {
      lines.push(`| ${cell(e.label)} | ${e.status} | ${cell(e.url)} | ${cell(e.reason || e.note)} |`);
    }
    lines.push('');
  }
  return lines.join('\n');
}

export function saveManifest(dir, m) {
  m.updated_at = new Date().toISOString();
  // Write then rename, so a crash mid-save can't leave half a manifest.
  const path = join(dir, '_manifest.json');
  writeFileSync(`${path}.tmp`, JSON.stringify(m, null, 2));
  renameSync(`${path}.tmp`, path);
  writeFileSync(join(dir, '_manifest.md'), renderMarkdown(m));
}

function cli() {
  const { positionals, values } = parseArgs({
    allowPositionals: true,
    options: {
      id: { type: 'string' }, category: { type: 'string' }, label: { type: 'string' },
      status: { type: 'string' }, url: { type: 'string' }, file: { type: 'string', multiple: true },
      reason: { type: 'string' }, note: { type: 'string' },
    },
  });
  const [cmd, dir] = positionals;
  const die = (msg) => { process.stderr.write(`manifest: ${msg}\n`); process.exit(1); };
  if (!dir || !['add', 'render'].includes(cmd)) die('usage: manifest.mjs add|render <dir> [...]');
  if (!existsSync(dir)) die(`no such directory: ${dir}`);
  let m;
  try {
    m = loadManifest(dir);
  } catch (e) {
    die(e.message);
  }
  if (cmd === 'add') {
    const { id, category, label, status } = values;
    if (!id || !category || !label || !status) die('add needs --id, --category, --label and --status');
    if (!STATUSES.includes(status)) die(`status must be one of ${STATUSES.join(', ')}`);
    // The agent may fill script gaps (pr:*, deck:*), never replace a found script item.
    if (m.items[id]?.by === 'script' && m.items[id].status === 'found') die(`refusing to overwrite found script item ${id}`);
    const files = values.file || [];
    const absent = files.filter((f) => !existsSync(join(dir, f)));
    if (status === 'found' && (files.length === 0 || absent.length)) die(`found item needs existing files; missing: ${absent.join(', ') || '(none given)'}`);
    setItem(m, id, { category, label, status, url: values.url || '', files, reason: values.reason, note: values.note, by: 'agent' });
  }
  saveManifest(dir, m);
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) cli();
