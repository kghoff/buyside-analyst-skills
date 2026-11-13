// Shared fetch helpers: SEC User-Agent + throttle, and retry with backoff.

import { secContact } from '../../../lib/settings.mjs';

// SEC silently 403s any User-Agent containing "github"; secContact() refuses one and is read at request time.
const SEC_MIN_INTERVAL_MS = 125; // ≤ 8 req/s; SEC's fair-access limit is 10
let lastSecRequest = 0;

const redact = (u) => String(u).replace(/(apikey=)[^&]+/gi, '$1***');

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// Retries network errors, 403/429 and 5xx (SEC throttles with 403/429).
// Other 4xx (e.g. 404) fail immediately.
export async function fetchWithRetry(url, options = {}, { tries = 3, baseDelayMs = 1000 } = {}) {
  let lastErr;
  for (let i = 0; i < tries; i++) {
    if (i > 0) await sleep(baseDelayMs * 2 ** (i - 1));
    let res;
    try {
      res = await fetch(url, options);
    } catch (e) {
      lastErr = e;
      continue;
    }
    if (res.ok) return res;
    lastErr = new Error(`HTTP ${res.status} for ${redact(url)}`);
    if (res.status !== 403 && res.status !== 429 && res.status < 500) throw lastErr;
  }
  throw lastErr;
}

export async function secFetch(url) {
  const wait = lastSecRequest + SEC_MIN_INTERVAL_MS - Date.now();
  if (wait > 0) await sleep(wait);
  lastSecRequest = Date.now();
  // A stalled connection would otherwise hang the whole run.
  return fetchWithRetry(url, { headers: { 'User-Agent': secContact() }, signal: AbortSignal.timeout(120_000) });
}
