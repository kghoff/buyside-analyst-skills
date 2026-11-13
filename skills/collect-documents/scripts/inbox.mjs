// Reports that sit behind the user's own logins or that an agent found on the web are
// filed here, not fetched by gather.mjs. The user puts the PDF in
// the category folder; Claude reads its first page and decides firm, date, type and
// title (a judgment call); this script renames and registers it, so every report
// ends up named and indexed the same way.
// CLI (used by SKILL.md step 4):
//   node inbox.mjs pending <dir> sellside              JSON: unregistered PDFs with first-page text
//   node inbox.mjs register <dir> sellside <plan.json> rename to "<date> <firm> <type> - <title>.pdf", file in its tier, register
//   node inbox.mjs tidy <dir> sellside                 move registered reports still at the folder root into their tier

import { existsSync, mkdirSync, readFileSync, readdirSync, renameSync } from 'node:fs';
import { basename, join } from 'node:path';
import { execFileSync } from 'node:child_process';
import { pathToFileURL } from 'node:url';
import { loadManifest, saveManifest, setItem, safeName } from './manifest.mjs';

// Sell-side types are the ones in the tier list below, plus the two forms retail platforms hand out,
// plus the outside pieces that land here from the web (articles, letters, short reports, news).
export const KINDS = {
  sellside: {
    category: 'Sellside Research', prefix: 'sell',
    types: ['initiation', 'deep dive', 'industry', 'preview', 'flash note', 'earnings recap', 'rating change',
      'event takeaways', 'survey', 'company report', 'quant rating', 'article', 'investor letter', 'short report', 'news'],
  },
};
const kindOf = (k) => { if (!KINDS[k]) throw new Error(`kind must be ${Object.keys(KINDS).join(' or ')}`); return KINDS[k]; };

// Not every outside source carries the same weight, so each report is filed in a tier folder.
// Tiers 1-2 follow the source ranking in the FIRM_TIERS list below; 3-4 are the web pieces below them.
export const TIERS = {
  1: '1 Broker Research',       // bulge bracket, mid-size and independent brokers, industry specialists
  2: '2 Independent Research',  // rating shops and the quant ratings retail platforms hand out
  3: '3 Independent Analysis',  // Seeking Alpha, Substack, newsletters, investor letters, short sellers, student funds
  4: '4 News and Trade Press',
};
const FIRM_TIERS = {
  1: ['JPM', 'J.P. Morgan', 'Goldman Sachs', 'Morgan Stanley', 'BofA', 'Citi', 'Barclays', 'UBS', 'Deutsche Bank',
    'Wells Fargo', 'Evercore ISI', 'Bernstein', 'Jefferies', 'Wolfe Research', 'RBC', 'BMO', 'TD Cowen', 'Mizuho',
    'Raymond James', 'Stifel', 'Piper Sandler', 'William Blair', 'Baird', 'KeyBanc', 'Truist', 'Oppenheimer',
    'Guggenheim', 'Needham', 'Cantor Fitzgerald', 'Canaccord', 'BTIG', 'Leerink', 'MoffettNathanson', 'New Street',
    'Vertical Research', 'Melius', 'Redburn'],
  2: ['Morningstar', 'CFRA', 'Argus', 'Value Line', 'Schwab', 'LSEG StarMine', 'SmartConsensus', 'Market Edge'],
};
// A plan entry's own tier wins; otherwise the firm's tier from FIRM_TIERS; firms not on that list need one.
export function tierOf({ firm, tier }) {
  if (tier !== undefined) return TIERS[tier] ? Number(tier) : null;
  const f = (firm || '').toLowerCase();
  return Number(Object.keys(FIRM_TIERS).find((t) => FIRM_TIERS[t].some((x) => x.toLowerCase() === f))) || null;
}

const registered = (m, category) => new Set(Object.values(m.items).filter((e) => e.category === category)
  .flatMap((e) => e.files || []).map((f) => f.split('/').pop()));

// The user drops PDFs at the folder root; one dropped straight into a tier folder is picked up too.
// `file` is the path inside the category folder.
export function pendingReports(dir, m, kind = 'sellside') {
  const folder = join(dir, kindOf(kind).category);
  if (!existsSync(folder)) return [];
  const done = registered(m, kindOf(kind).category);
  const pdfs = (sub) => (existsSync(join(folder, sub)) ? readdirSync(join(folder, sub)) : [])
    .filter((f) => /\.pdf$/i.test(f) && !done.has(f)).map((f) => (sub ? `${sub}/${f}` : f));
  return ['', ...Object.values(TIERS)].flatMap(pdfs).sort().map((file) => {
    const pdf = join(folder, file);
    const info = execFileSync('pdfinfo', [pdf], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] });
    const text = execFileSync('pdftotext', ['-l', '1', pdf, '-'], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] });
    return {
      file,
      pages: Number(/^Pages:\s+(\d+)/m.exec(info)?.[1] || 0),
      pdfTitle: /^Title:\s+(.*)$/m.exec(info)?.[1]?.trim() || '',
      firstPage: text.split('\n').map((l) => l.trim()).filter(Boolean).slice(0, 40).join('\n'),
    };
  });
}

export function reportName({ date, firm, type, title }) {
  const t = (title || '').replace(/\s+/g, ' ').trim().slice(0, 90).trim();
  return safeName(`${date} ${firm} ${type}${t ? ` - ${t}` : ''}`).replace(/[?*"<>|]/g, '') + '.pdf';
}

const slug = (s) => s.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');

// Validates the whole plan before renaming anything, so a bad entry never leaves the folder half filed.
export function register(dir, m, plan, kind = 'sellside') {
  const { category: CATEGORY, prefix, types } = kindOf(kind);
  const folder = join(dir, CATEGORY);
  const pending = new Set(pendingReports(dir, m, kind).map((p) => p.file));
  const taken = new Set();
  const rows = plan.map((r) => {
    if (!pending.has(r.file)) throw new Error(`${r.file}: not a pending report in ${CATEGORY}/`);
    if (!/^\d{4}-\d{2}-\d{2}$/.test(r.date || '')) throw new Error(`${r.file}: date must be YYYY-MM-DD (the report's own date)`);
    if (!types.includes(r.type)) throw new Error(`${r.file}: type must be one of ${types.join(', ')}`);
    if (!r.firm) throw new Error(`${r.file}: firm is required`);
    const tier = tierOf(r);
    if (!tier) throw new Error(`${r.file}: tier (1-4) is required for ${r.firm}, which is not ranked in FIRM_TIERS (inbox.mjs)`);
    const name = reportName(r);
    const to = `${TIERS[tier]}/${name}`;
    if (to !== r.file && (existsSync(join(folder, to)) || taken.has(to.toLowerCase()))) throw new Error(`${r.file}: ${to} already exists`);
    taken.add(to.toLowerCase());
    return { ...r, tier, name, to, id: `${prefix}:${r.date}:${slug(r.firm)}:${slug(r.title || r.type)}`.slice(0, 120) };
  });
  for (const r of rows) {
    if (m.items[r.id]) throw new Error(`${r.file}: id ${r.id} already registered`);
  }
  for (const r of rows) {
    mkdirSync(join(folder, TIERS[r.tier]), { recursive: true });
    if (r.to !== r.file) renameSync(join(folder, r.file), join(folder, r.to));
    setItem(m, r.id, {
      category: CATEGORY, label: r.name.replace(/\.pdf$/i, ''), status: 'found', files: [`${CATEGORY}/${r.to}`],
      url: r.url || `file:${basename(r.file)}`, reason: '', by: r.by || 'user', firm: r.firm, type: r.type, date: r.date,
      tier: r.tier, note: `added by ${r.by || 'user'} (original file name: ${basename(r.file)})`,
    });
  }
  saveManifest(dir, m);
  return rows.map((r) => ({ id: r.id, file: r.to }));
}

// Reports filed before tiers existed sit at the folder root with their Markdown in `_md/`.
// Moves each into its tier folder (PDF and Markdown) and records the tier. Checks every entry first.
export function tidy(dir, m, kind = 'sellside') {
  const { category: CATEGORY } = kindOf(kind);
  const moves = Object.entries(m.items)
    .filter(([, e]) => e.category === CATEGORY && (e.files || []).some((f) => f.split('/').length === 2 && /\.pdf$/i.test(f)))
    .map(([id, e]) => {
      const tier = tierOf({ firm: e.firm, tier: e.tier });
      if (!tier) throw new Error(`${e.label}: no firm tier for ${e.firm}; set "tier" (1-4) on ${id} in _manifest.json`);
      const files = e.files.map((f) => f.replace(`${CATEGORY}/`, `${CATEGORY}/${TIERS[tier]}/`));
      return { id, e, tier, files };
    });
  for (const { e, tier, files } of moves) {
    e.files.forEach((from, i) => {
      if (!existsSync(join(dir, from))) return;
      mkdirSync(join(dir, files[i], '..'), { recursive: true });
      renameSync(join(dir, from), join(dir, files[i]));
    });
    e.files = files;
    e.tier = tier;
  }
  saveManifest(dir, m);
  return moves.map(({ id, files }) => ({ id, files }));
}

function cli() {
  const [cmd, dir, kind, planPath] = process.argv.slice(2);
  const die = (msg) => { process.stderr.write(`inbox: ${msg}\n`); process.exit(1); };
  const usage = 'usage: inbox.mjs pending|register|tidy <dir> sellside [plan.json]';
  if (!dir || !existsSync(dir) || !KINDS[kind]) die(usage);
  try {
    if (cmd === 'pending') console.log(JSON.stringify(pendingReports(dir, loadManifest(dir), kind), null, 2));
    else if (cmd === 'tidy') console.log(JSON.stringify(tidy(dir, loadManifest(dir), kind), null, 2));
    else if (cmd === 'register' && planPath) console.log(JSON.stringify(register(dir, loadManifest(dir), JSON.parse(readFileSync(planPath, 'utf8')), kind), null, 2));
    else die(usage);
  } catch (e) {
    die(e.message);
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) cli();
