import { describe, it, expect } from 'vitest';
import { parseRequests, runPeerDocs, MAX_REQUESTS } from '../scripts/peer_docs.mjs';

// Agents write doc_requests.txt by hand; the main agent runs one command and hands back exact paths.
const REQ = `# peer documents
DXCM calls 2026Q3 | CGM share and price
DXCM 10-Q 2026Q3 | US vs international split

BSX calls 2026Q3 | EP share
ABT calls 2026Q3 | should be refused
`;

describe('parseRequests', () => {
  it('reads ticker / kinds / quarters / why, skipping blanks and comments', () => {
    const { lines } = parseRequests(REQ, 'ABT');
    expect(lines[0]).toEqual({ ticker: 'DXCM', kinds: ['calls'], quarters: '2026Q3', why: 'CGM share and price' });
    expect(lines).toHaveLength(3);
  });
  it("refuses the subject's own ticker: its documents are already collected", () => {
    const { skipped } = parseRequests(REQ, 'abt');
    expect(skipped).toEqual([{ line: 'ABT calls 2026Q3 | should be refused', reason: "subject's own documents are already collected" }]);
  });
  it(`caps at ${MAX_REQUESTS} requests and lists the overflow`, () => {
    const many = Array.from({ length: MAX_REQUESTS + 2 }, (_, i) => `P${i} calls 2026Q3 | x`).join('\n');
    const { lines, skipped } = parseRequests(many, 'ABT');
    expect(lines).toHaveLength(MAX_REQUESTS);
    expect(skipped.map((s) => s.reason)).toEqual(['over the cap', 'over the cap']);
  });
  it('flags a malformed line instead of guessing', () => {
    const { lines, skipped } = parseRequests('DXCM the Q3 call please', 'ABT');
    expect(lines).toEqual([]);
    expect(skipped[0].reason).toMatch(/TICKER kinds quarters \| why/);
  });
});

describe('runPeerDocs', () => {
  it('runs one targeted gather per ticker with the union of kinds and quarters, and returns absolute md paths', async () => {
    const calls = [];
    const gather = async (ticker, only, quarters) => {
      calls.push([ticker, only, quarters]);
      return ticker === 'DXCM'
        ? ['DXCM → /r/DXCM', 'local 2026 Q3 DXCM call → DXCM/Earnings Calls/_md/2026 Q3 DXCM call.md',
          'found DXCM 2026 Q3 10-Q → DXCM/10-Qs/_md/DXCM 2026 Q3 10-Q.md']
        : ['BSX → /r/BSX', 'deferred 2026 Q3 BSX call →  : Alpha Vantage daily limit reached'];
    };
    const out = await runPeerDocs({ text: REQ, subject: 'ABT', researchDir: '/r', gather });
    expect(calls).toEqual([['DXCM', 'calls,10-Q', '2026Q3'], ['BSX', 'calls', '2026Q3']]);
    expect(out.docs).toEqual([
      { ticker: 'DXCM', label: '2026 Q3 DXCM call', status: 'local', md: '/r/DXCM/Earnings Calls/_md/2026 Q3 DXCM call.md', reason: '', why: 'CGM share and price; US vs international split' },
      { ticker: 'DXCM', label: 'DXCM 2026 Q3 10-Q', status: 'found', md: '/r/DXCM/10-Qs/_md/DXCM 2026 Q3 10-Q.md', reason: '', why: 'CGM share and price; US vs international split' },
      { ticker: 'BSX', label: '2026 Q3 BSX call', status: 'deferred', md: '', reason: 'Alpha Vantage daily limit reached', why: 'EP share' },
    ]);
    expect(out.skipped).toHaveLength(1);
  });
  it('keeps lastN and explicit quarters for one ticker as separate runs (gather takes one --quarters)', async () => {
    const calls = [];
    const gather = async (t, o, q) => { calls.push([t, o, q]); return [`${t} → /r/${t}`]; };
    await runPeerDocs({ text: 'DXCM calls last2 | a\nDXCM 10-K 2025Q4 | b', subject: 'ABT', researchDir: '/r', gather });
    expect(calls).toEqual([['DXCM', 'calls', 'last2'], ['DXCM', '10-K', '2025Q4']]);
  });
  it('records a gather failure for that ticker and carries on with the rest', async () => {
    const gather = async (t) => { if (t === 'DXCM') throw new Error('unknown ticker'); return [`${t} → /r/${t}`]; };
    const out = await runPeerDocs({ text: 'DXCM calls 2026Q3 | a\nBSX calls 2026Q3 | b', subject: 'ABT', researchDir: '/r', gather });
    expect(out.docs).toEqual([{ ticker: 'DXCM', label: 'calls 2026Q3', status: 'missing', md: '', reason: 'unknown ticker', why: 'a' }]);
  });
});
