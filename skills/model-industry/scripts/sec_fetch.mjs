// Filing list + fiscal-year end dates for one company; optionally its annual 10-Ks as Markdown.
// usage: node sec_fetch.mjs TICKER OUT.json [--tenk N --md-dir DIR]
// Reuses /collect-documents's SEC helpers (User-Agent, throttle) and its EDGAR HTML -> Markdown converter.
import { writeFileSync, existsSync, mkdirSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const G = join(dirname(fileURLToPath(import.meta.url)), '..', '..', 'collect-documents', 'scripts');
const { resolveCik, fetchSubmissions, fetchFiscalTags, filingUrl } = await import(join(G, 'sec.mjs'));
const { secFetch } = await import(join(G, 'http.mjs'));
const { cleanEdgarHtml, convertToMarkdown } = await import(join(G, 'convert.mjs'));

const [ticker, out, ...rest] = process.argv.slice(2);
const opt = (k) => { const i = rest.indexOf(k); return i >= 0 ? rest[i + 1] : null; };
const tenk = Number(opt('--tenk') || 0);
const mdDir = opt('--md-dir');

const co = await resolveCik(ticker);
if (!co) { console.error(`no SEC CIK for ${ticker}`); process.exit(2); }
const since = `${new Date().getFullYear() - 13}-01-01`;
const sub = await fetchSubmissions(co.cik, since);
const tags = await fetchFiscalTags(co.cik);
const annual = ['10-K', '20-F', '40-F'];
const seen = new Set();
const filings = sub.filings
  .filter((f) => annual.includes(f.form) && f.reportDate && !seen.has(f.reportDate) && seen.add(f.reportDate))
  .map((f) => ({ fy: tags.get(f.accn)?.fy ?? null, form: f.form, reportDate: f.reportDate,
                 filingDate: f.filingDate, accn: f.accn, url: filingUrl(co.cik, f) }));
const md = [];
if (tenk && mdDir) {
  mkdirSync(mdDir, { recursive: true });
  for (const f of filings.slice(0, tenk)) {
    const fy = f.fy ?? Number(f.reportDate.slice(0, 4));
    const path = join(mdDir, `${ticker.toUpperCase()} ${fy} ${f.form}.md`);
    if (!existsSync(path)) {
      const html = await (await secFetch(f.url)).text();
      writeFileSync(path, `<!-- source: ${f.url} -->\n\n${convertToMarkdown(cleanEdgarHtml(html))}\n`);
    }
    md.push(path);
  }
}
writeFileSync(out, JSON.stringify({ ticker: ticker.toUpperCase(), cik: co.cik, name: sub.name,
  fiscalYearEnd: sub.fiscalYearEnd, filings, md }, null, 1));
console.log(JSON.stringify({ ticker, filings: filings.length, md: md.length }));
