#!/usr/bin/env node
// Turns an agent's doc_requests.txt into targeted fetches (gather.mjs --only/--quarters) and writes peer_docs.json:
// [{ticker, label, status, md, reason, why}], md absolute so the agent can Read it. Local documents are not refetched.
// Usage: node peer_docs.mjs --requests <doc_requests.txt> --subject <TICKER> [--out <peer_docs.json>]
// Request lines: 'TICKER kinds quarters | why', e.g. 'DXCM calls 2026Q3 | CGM share' (kinds: calls, 10-Q, 10-K,
// releases, comma-separated; quarters: 2026Q3[,2026Q2] or last2).
import { readFileSync, writeFileSync } from 'node:fs';
import { execFile } from 'node:child_process';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseArgs } from 'node:util';
import { KINDS } from './only.mjs';

export const MAX_REQUESTS = 6;
const LINE = /^([A-Za-z][A-Za-z0-9.\-]*)\s+([A-Za-z0-9,\-]+)\s+(last\d+|\d{4}Q[1-4](?:,\d{4}Q[1-4])*)\s*\|\s*(.+)$/;

export function parseRequests(text, subject) {
  const lines = [], skipped = [];
  for (const raw of String(text).split('\n')) {
    const line = raw.trim();
    if (!line || line.startsWith('#')) continue;
    const m = line.match(LINE);
    const kinds = m ? m[2].split(',') : [];
    if (!m || kinds.some((k) => !KINDS.includes(k))) {
      skipped.push({ line, reason: `not 'TICKER kinds quarters | why' (kinds: ${KINDS.join(', ')}; quarters: 2026Q3 or last2)` });
    } else if (m[1].toUpperCase() === String(subject).toUpperCase()) {
      skipped.push({ line, reason: "subject's own documents are already collected" });
    } else if (lines.length >= MAX_REQUESTS) {
      skipped.push({ line, reason: 'over the cap' });
    } else {
      lines.push({ ticker: m[1].toUpperCase(), kinds, quarters: m[3], why: m[4].trim() });
    }
  }
  return { lines, skipped };
}

// One run per ticker: explicit quarters merge; a lastN spec runs on its own (gather takes one --quarters).
function plan(lines) {
  const runs = new Map();
  for (const l of lines) {
    const key = l.quarters.startsWith('last') ? `${l.ticker} ${l.quarters}` : `${l.ticker} explicit`;
    const r = runs.get(key) || { ticker: l.ticker, kinds: new Set(), quarters: new Set(), why: [] };
    l.kinds.forEach((k) => r.kinds.add(k));
    l.quarters.split(',').forEach((q) => r.quarters.add(q));
    if (!r.why.includes(l.why)) r.why.push(l.why);
    runs.set(key, r);
  }
  return [...runs.values()].map((r) => ({
    ticker: r.ticker, only: KINDS.filter((k) => r.kinds.has(k)).join(','), quarters: [...r.quarters].join(','), why: r.why.join('; '),
  }));
}

// gather's status lines: '<status> <label> → <md path relative to research_dir>[ : reason]'
const STATUS = /^(found|local|missing|deferred|skipped) (.+?) → (.*?)(?: : (.*))?$/;

export async function runPeerDocs({ text, subject, researchDir, gather }) {
  const { lines, skipped } = parseRequests(text, subject);
  const docs = [];
  for (const r of plan(lines)) {
    let out;
    try {
      out = await gather(r.ticker, r.only, r.quarters);
    } catch (e) {
      docs.push({ ticker: r.ticker, label: `${r.only} ${r.quarters}`, status: 'missing', md: '', reason: e.message, why: r.why });
      continue;
    }
    for (const l of out) {
      const m = l.match(STATUS);
      if (!m) continue;
      const rel = m[3].trim();
      docs.push({ ticker: r.ticker, label: m[2], status: m[1], md: rel ? join(researchDir, rel) : '', reason: m[4] || '', why: r.why });
    }
  }
  return { docs, skipped };
}

function gatherCli(ticker, only, quarters) {
  const script = join(dirname(fileURLToPath(import.meta.url)), 'gather.mjs');
  return new Promise((res, rej) => execFile(process.execPath, [script, ticker, '--only', only, '--quarters', quarters],
    { timeout: 600_000, maxBuffer: 16 * 1024 * 1024 },
    (err, stdout, stderr) => (err ? rej(new Error((stderr || err.message).trim())) : res(stdout.split('\n')))));
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const { values } = parseArgs({ options: { requests: { type: 'string' }, subject: { type: 'string' }, out: { type: 'string' } } });
  if (!values.requests || !values.subject) {
    process.stderr.write('usage: node peer_docs.mjs --requests <doc_requests.txt> --subject <TICKER> [--out <peer_docs.json>]\n');
    process.exit(1);
  }
  const { researchDir } = await import('../../../lib/settings.mjs');
  const result = await runPeerDocs({
    text: readFileSync(values.requests, 'utf8'), subject: values.subject, researchDir: researchDir(), gather: gatherCli,
  });
  const out = values.out || join(dirname(values.requests), 'peer_docs.json');
  writeFileSync(out, JSON.stringify(result.docs, null, 1));
  for (const d of result.docs) console.log(`${d.status} ${d.label}${d.md ? ` → ${d.md}` : ''}${d.reason ? ` : ${d.reason}` : ''}`);
  for (const s of result.skipped) console.log(`skipped "${s.line}": ${s.reason}`);
  console.log(`wrote ${out}`);
}
