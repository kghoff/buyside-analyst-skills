import { describe, it, expect } from 'vitest';
import { createTranscriptFetcher, formatTranscript, isKnownMiss, NO_TRANSCRIPT } from '../scripts/transcripts.mjs';

const reply = (obj) => ({ json: async () => obj });
const transcript = { symbol: 'X', quarter: '2025Q1', transcript: [{ speaker: 'Jane', title: 'CEO', content: 'Hello' }] };

describe('createTranscriptFetcher', () => {
  it('moves to key 2 when key 1 is out of calls, and stays there', async () => {
    const calls = [];
    const fake = async (url) => {
      calls.push(url);
      const quarter = new URL(url).searchParams.get('quarter');
      return url.includes('apikey=K1') ? reply({ Information: 'daily rate limit reached' }) : reply({ ...transcript, quarter });
    };
    const fetchT = createTranscriptFetcher(['K1', 'K2'], fake);
    expect((await fetchT('X', '2025Q1')).status).toBe('found');
    expect((await fetchT('X', '2025Q2')).status).toBe('found');
    expect(calls.filter((u) => u.includes('apikey=K1'))).toHaveLength(1);
  });

  it('defers remaining quarters without spending calls once every key is exhausted', async () => {
    let calls = 0;
    const fake = async () => { calls++; return reply({ Note: 'our standard API rate limit is 25 requests per day' }); };
    const fetchT = createTranscriptFetcher(['K1', 'K2'], fake);
    expect(await fetchT('X', '2025Q1')).toMatchObject({ status: 'deferred' });
    expect(await fetchT('X', '2025Q2')).toMatchObject({ status: 'deferred' });
    expect(calls).toBe(2);
  });

  it('marks an empty transcript as missing, not deferred', async () => {
    const fetchT = createTranscriptFetcher(['K1'], async () => reply({ symbol: 'X', transcript: [] }));
    expect(await fetchT('X', '2025Q1')).toEqual({ status: 'missing', reason: 'Alpha Vantage has no transcript for this quarter' });
  });

  // AV keys on calendar quarters for some symbols; a transcript for the wrong
  // quarter must not be saved under this quarter's name.
  it('marks a transcript for a different quarter as missing', async () => {
    const fetchT = createTranscriptFetcher(['K1'], async () => reply({ ...transcript, quarter: '2024Q4' }));
    expect(await fetchT('X', '2025Q1')).toEqual({ status: 'missing', reason: 'Alpha Vantage returned 2024Q4 for 2025Q1' });
  });

  it('defers with a clear reason when no keys are configured', async () => {
    const fetchT = createTranscriptFetcher([], async () => { throw new Error('should not be called'); });
    expect((await fetchT('X', '2025Q1')).reason).toMatch(/alpha_vantage_keys/);
  });

  it('never leaks an API key in a thrown error', async () => {
    const fake = async () => { throw new Error('HTTP 500 for https://www.alphavantage.co/query?function=X&apikey=SECRETKEY'); };
    const fetchT = createTranscriptFetcher(['SECRETKEY'], fake, { sleep: async () => {} });
    const err = await fetchT('X', '2025Q1').catch((e) => e);
    expect(err).toBeInstanceOf(Error);
    expect(err.message).not.toContain('SECRETKEY');
  });

  it('turns a non-JSON body into a clear error', async () => {
    const fake = async () => ({ json: async () => { throw new SyntaxError('Unexpected token <'); } });
    const fetchT = createTranscriptFetcher(['K1'], fake, { sleep: async () => {} });
    await expect(fetchT('X', '2025Q1')).rejects.toThrow(/non-JSON/);
  });

  it('waits and retries the same key on a per-minute throttle', async () => {
    const urls = [];
    const sleeps = [];
    let n = 0;
    const fake = async (url) => {
      urls.push(url);
      return n++ === 0 ? reply({ Note: 'Our standard API call frequency is 5 calls per minute and 500 calls per day.' }) : reply(transcript);
    };
    const fetchT = createTranscriptFetcher(['K1', 'K2'], fake, { sleep: async (ms) => { sleeps.push(ms); }, throttleWaitMs: 5 });
    expect((await fetchT('X', '2025Q1')).status).toBe('found');
    expect(sleeps.filter((ms) => ms === 5)).toHaveLength(1);
    expect(urls.every((u) => u.includes('apikey=K1'))).toBe(true);
  });

  it('returns missing without advancing the key for non-limit messages', async () => {
    const urls = [];
    const fake = async (url) => {
      urls.push(url);
      return reply({ Information: 'Thank you for using Alpha Vantage! This is a premium endpoint...' });
    };
    const fetchT = createTranscriptFetcher(['K1', 'K2'], fake, { sleep: async () => {} });
    const r = await fetchT('X', '2025Q1');
    expect(r.status).toBe('missing');
    expect(r.reason.startsWith('Alpha Vantage: ')).toBe(true);
    await fetchT('X', '2025Q2');
    expect(urls.every((u) => u.includes('apikey=K1'))).toBe(true);
  });

  it('spaces AV calls at least 1200ms apart', async () => {
    const sleeps = [];
    const fetchT = createTranscriptFetcher(['K1'], async () => reply(transcript), { sleep: async (ms) => { sleeps.push(ms); } });
    await fetchT('X', '2025Q1');
    await fetchT('X', '2025Q2');
    expect(sleeps.length).toBeGreaterThan(0);
    expect(sleeps.every((ms) => ms <= 1200)).toBe(true);
  });
});

describe('formatTranscript', () => {
  it('renders speakers and a participant list', () => {
    const md = formatTranscript(transcript);
    expect(md).toContain('- **Jane** — CEO');
    expect(md).toContain('**Jane** *(CEO)*:');
    expect(md).toContain('Hello');
  });
});

describe('isKnownMiss (no AV calls re-spent on permanent misses)', () => {
  const miss = { status: 'missing', reason: NO_TRANSCRIPT };
  it('skips an old quarter AV already said it has no transcript for', () => {
    expect(isKnownMiss(miss, 2)).toBe(true);
    expect(isKnownMiss(miss, 11)).toBe(true);
  });
  it('retries the 2 newest quarters, whose transcripts may not be posted yet', () => {
    expect(isKnownMiss(miss, 0)).toBe(false);
    expect(isKnownMiss(miss, 1)).toBe(false);
  });
  it('retries other misses and deferrals', () => {
    expect(isKnownMiss({ status: 'missing', reason: 'Alpha Vantage error: x' }, 5)).toBe(false);
    expect(isKnownMiss({ status: 'deferred', reason: NO_TRANSCRIPT }, 5)).toBe(false);
    expect(isKnownMiss(undefined, 5)).toBe(false);
  });
});
