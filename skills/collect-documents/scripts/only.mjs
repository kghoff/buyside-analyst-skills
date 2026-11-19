// Targeted fetch (gather.mjs --only / --quarters): pure helpers that cut selectFilings' output down to the documents
// another skill asked for, so a peer folder never gets half a full run. See SKILL.md "Targeted fetch".
import { quarterKey } from './fiscal.mjs';
import { isDone } from './manifest.mjs';

export const KINDS = ['calls', '10-Q', '10-K', 'releases'];

export function parseOnly(text) {
  const kinds = new Set(String(text || '').split(',').map((s) => s.trim()).filter(Boolean));
  const bad = [...kinds].filter((k) => !KINDS.includes(k));
  if (bad.length || kinds.size === 0) throw new Error(`--only: unknown kind "${bad.join(', ')}"; use ${KINDS.join(', ')}`);
  return kinds;
}

// Fiscal quarters as the manifest keys them ('2026Q3'), or 'lastN' counted back from the company's own window.
export function parseQuarters(text, sel) {
  const t = String(text || 'last2').trim();
  const last = t.match(/^last(\d+)$/);
  if (last) return sel.window.slice(0, Number(last[1])).map(quarterKey);
  const out = t.split(',').map((s) => s.trim());
  const bad = out.filter((s) => !/^\d{4}Q[1-4]$/.test(s));
  if (bad.length) throw new Error(`--quarters: "${bad.join(', ')}" is not a fiscal quarter like 2026Q3 (or use last2)`);
  return out;
}

export function filterSelection(sel, only, quarters) {
  const qs = new Set(quarters);
  const years = new Set(quarters.map((k) => Number(k.slice(0, 4))));
  const inQ = (f) => qs.has(quarterKey(f));
  return {
    ...sel,
    tenKs: only.has('10-K') ? sel.tenKs.filter((f) => years.has(f.fy)) : [],
    tenQs: only.has('10-Q') ? sel.tenQs.filter(inQ) : [],
    releases: only.has('releases') ? sel.releases.filter(inQ) : [],
    releaseWindow: only.has('releases') ? sel.releaseWindow.filter(inQ) : [],
    window: only.has('calls') ? sel.window.filter(inQ) : [],
    proxies: [],
    regFd: [],
    skipped: [],
  };
}

// The manifest ids a filtered selection writes (8-K releases by their index id; their exhibits are its children).
export function requestedIds(sel) {
  return [
    ...sel.tenKs.map((f) => `10-K:${f.reportDate}`),
    ...sel.tenQs.map((f) => `10-Q:${f.reportDate}`),
    ...sel.releases.map((f) => `8k:${f.accn}`),
    ...sel.window.map((q) => `call:${quarterKey(q)}`),
  ];
}

export function localStatus(manifest, dir, ids) {
  return Object.fromEntries(ids.map((id) => [id, isDone(dir, manifest.items[id]) ? 'local' : 'todo']));
}
