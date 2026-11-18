#!/usr/bin/env node
// Renames an existing /collect-documents folder from the old quarter-first labels
// ("Q1 24 DXCM release ...", "DXCM Q1 24 10-Q") to year-first ones
// ("2024 Q1 DXCM release ...", "DXCM 2024 Q1 10-Q"), so files sort by date.
// Renames files on disk and rewrites the manifest's labels and file paths.
// Safe to rerun: year-first names are left alone.
// Usage: node relabel.mjs <dir> [--dry-run]

import { existsSync, readdirSync, renameSync, realpathSync } from 'node:fs';
import { join, dirname, basename } from 'node:path';
import { parseArgs } from 'node:util';
import { pathToFileURL } from 'node:url';
import { loadManifest, saveManifest } from './manifest.mjs';

// "Q1 24" -> "2024 Q1". Not "Q1 10-Q" (already year-first: "2024 Q1 10-Q").
const OLD = /(?<!\d{4} )\bQ([1-4]) (\d{2})(?![\d-])/g;
export const yearFirst = (s) => s.replace(OLD, (_m, q, yy) => `20${yy} Q${q}`);
const renamed = (p) => join(dirname(p), yearFirst(basename(p)));

function walk(dir, out = []) {
  for (const e of readdirSync(dir, { withFileTypes: true })) {
    if (e.name.startsWith('.')) continue;
    const p = join(dir, e.name);
    if (e.isDirectory()) walk(p, out);
    else out.push(p);
  }
  return out;
}

export function relabel(dir, { dryRun = false } = {}) {
  const moves = walk(dir).map((p) => [p, renamed(p)]).filter(([a, b]) => a !== b);
  const clash = moves.filter(([, b]) => existsSync(b)).map(([, b]) => b);
  if (clash.length) throw new Error(`relabel: target already exists: ${clash.join(', ')}`);
  const m = loadManifest(dir);
  let labels = 0;
  for (const e of Object.values(m.items)) {
    const label = e.label && yearFirst(e.label);
    if (label !== e.label) { e.label = label; labels++; }
    if (e.files) e.files = e.files.map(renamed);
  }
  if (!dryRun) {
    for (const [a, b] of moves) renameSync(a, b);
    if (labels || moves.length) saveManifest(dir, m);
  }
  return { files: moves.length, labels };
}

if (import.meta.url === pathToFileURL(realpathSync(process.argv[1])).href) {
  const { positionals, values } = parseArgs({ allowPositionals: true, options: { 'dry-run': { type: 'boolean' } } });
  const dir = positionals[0];
  if (!dir || !existsSync(join(dir, '_manifest.json'))) {
    process.stderr.write('usage: relabel.mjs <gather folder with _manifest.json> [--dry-run]\n');
    process.exit(1);
  }
  const r = relabel(dir, { dryRun: values['dry-run'] });
  console.log(`${values['dry-run'] ? 'would rename' : 'renamed'} ${r.files} files, ${r.labels} manifest labels`);
}
