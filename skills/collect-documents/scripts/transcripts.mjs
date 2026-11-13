// Alpha Vantage earnings call transcripts with multi-key failover.

import { fetchWithRetry } from './http.mjs';
import { loadSettings, settingsPath } from '../../../lib/settings.mjs';

const AV_BASE = 'https://www.alphavantage.co/query';

export function loadAvKeys() {
  return (loadSettings().alpha_vantage_keys || []).filter(Boolean);
}

export const NO_TRANSCRIPT = 'Alpha Vantage has no transcript for this quarter';

// An older quarter AV already said it has no transcript for won't gain one;
// skip it (it stays a reported gap). The 2 newest quarters are retried since
// AV posts transcripts with a lag.
export function isKnownMiss(entry, windowIndex) {
  return windowIndex >= 2 && entry?.status === 'missing' && entry.reason === NO_TRANSCRIPT;
}

const THROTTLE_RE = /per minute|per second|sparingly|spreading out/i;
const DAILY_RE = /per day|daily|rate limit/i;
const MIN_SPACING_MS = 1200;
const MAX_THROTTLE_RETRIES = 2;

// Returns fetchTranscript(symbol, 'YYYYQn') → { status: 'found', data } |
// { status: 'missing' | 'deferred', reason }. AV reports limits as HTTP 200
// with a Note/Information field. Burst throttles wait and retry the same key;
// a spent daily quota moves to the next key and never goes back; any other
// message (premium endpoint, invalid key) is reported without burning keys.
export function createTranscriptFetcher(
  keys,
  fetchImpl = fetchWithRetry,
  { sleep = (ms) => new Promise((r) => setTimeout(r, ms)), throttleWaitMs = 60_000 } = {},
) {
  let k = 0;
  let lastLimitMsg = '';
  let lastCall = 0;
  const scrub = (msg) => keys.reduce((m, key) => m.split(key).join('***'), String(msg));

  async function callAv(url) {
    const wait = lastCall + MIN_SPACING_MS - Date.now();
    if (wait > 0) await sleep(Math.min(wait, MIN_SPACING_MS));
    lastCall = Date.now();
    try {
      return await (await fetchImpl(url)).json();
    } catch (e) {
      if (e instanceof SyntaxError) throw new Error('Alpha Vantage returned a non-JSON response');
      throw new Error(scrub(e?.message ?? e));
    }
  }

  return async function fetchTranscript(symbol, quarter) {
    if (keys.length === 0) return { status: 'deferred', reason: `no Alpha Vantage keys in ${settingsPath()} (alpha_vantage_keys)` };
    let throttleRetries = 0;
    while (k < keys.length) {
      const url = `${AV_BASE}?function=EARNINGS_CALL_TRANSCRIPT&symbol=${encodeURIComponent(symbol)}&quarter=${quarter}&apikey=${keys[k]}`;
      const data = await callAv(url);
      const msg = data?.Note || data?.Information;
      if (msg) {
        const text = String(msg);
        if (THROTTLE_RE.test(text)) {
          if (throttleRetries < MAX_THROTTLE_RETRIES) {
            throttleRetries++;
            await sleep(throttleWaitMs);
            continue;
          }
        } else if (!DAILY_RE.test(text)) {
          return { status: 'missing', reason: `Alpha Vantage: ${text.slice(0, 150)}` };
        }
        lastLimitMsg = text.slice(0, 120);
        k++;
        throttleRetries = 0;
        continue;
      }
      if (data?.['Error Message']) {
        return { status: 'missing', reason: `Alpha Vantage error: ${String(data['Error Message']).slice(0, 150)}` };
      }
      if (!Array.isArray(data?.transcript) || data.transcript.length === 0) {
        return { status: 'missing', reason: NO_TRANSCRIPT };
      }
      if (data.quarter && data.quarter !== quarter) {
        return { status: 'missing', reason: `Alpha Vantage returned ${data.quarter} for ${quarter}` };
      }
      return { status: 'found', data };
    }
    return { status: 'deferred', reason: `Alpha Vantage limit reached on all keys (${lastLimitMsg}); rerun later` };
  };
}

// Adapted from an earlier project's transcript formatter.
export function formatTranscript(data) {
  const lines = ['# Earnings Call Transcript', `**${data.symbol || ''}**: ${data.quarter || ''}`, ''];
  const participants = new Map();
  for (const seg of data.transcript) {
    if (seg.speaker && seg.title && !participants.has(seg.speaker)) participants.set(seg.speaker, seg.title);
  }
  if (participants.size > 0) {
    lines.push('## Participants', '');
    for (const [name, title] of participants) lines.push(`- **${name}** — ${title}`);
    lines.push('', '---', '');
  }
  for (const seg of data.transcript) {
    lines.push(`**${seg.speaker || 'Unknown'}** *(${seg.title || ''})*:`, '', seg.content || '', '');
  }
  return lines.join('\n');
}
