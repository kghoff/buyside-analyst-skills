import { describe, it, expect } from 'vitest';
import {
  rowsFromColumns, parseFiscalTags, selectFilings, selectProxies, parseExhibitIndex, classifyExhibit, filingUrl,
} from '../scripts/sec.mjs';

// A December-year-end company filing on a normal cadence, 2013–2025.
function decemberCompany() {
  const f = [];
  let n = 0;
  const add = (form, reportDate, filingDate, items = '') =>
    f.push({ accn: `0000000000-00-${String(++n).padStart(6, '0')}`, form, reportDate, filingDate, primaryDocument: 'doc.htm', items });
  for (let y = 2013; y <= 2025; y++) {
    add('10-Q', `${y}-03-31`, `${y}-05-05`);
    add('10-Q', `${y}-06-30`, `${y}-08-05`);
    add('10-Q', `${y}-09-30`, `${y}-11-05`);
    add('10-K', `${y}-12-31`, `${y + 1}-02-10`);
    add('8-K', '', `${y}-04-25`, '2.02,9.01');
    add('8-K', '', `${y}-07-25`, '2.02,9.01');
    add('8-K', '', `${y}-10-25`, '2.02,9.01');
    add('8-K', '', `${y + 1}-01-28`, '2.02,9.01');
  }
  add('10-K/A', '2024-12-31', '2025-04-30');
  add('8-K', '', '2024-06-13', '7.01,9.01');
  add('8-K', '', '2020-06-13', '7.01,9.01');
  return f;
}

describe('selectFilings', () => {
  const sel = selectFilings({ filings: decemberCompany(), fiscalTags: new Map(), fiscalYearEnd: '1231' });

  it('takes exactly the 10 most recent 10-Ks (10 years of annuals)', () => {
    expect(sel.tenKs.map((f) => f.fy)).toEqual([2025, 2024, 2023, 2022, 2021, 2020, 2019, 2018, 2017, 2016]);
  });
  it('takes 10-Qs for the same 10 fiscal years as the 10-Ks (model-historicals builds 10 years of quarters)', () => {
    // Q4 lives in the 10-K, so 10 years of quarters = Q1-Q3 10-Qs for every 10-K year.
    expect(sel.tenQs).toHaveLength(30);
    for (const k of sel.tenKs) {
      expect(sel.tenQs.filter((q) => q.fy === k.fy).map((q) => q.fq).sort()).toEqual([1, 2, 3]);
    }
    expect(Math.min(...sel.tenQs.map((f) => f.fy))).toBe(2016);
    expect(sel.window[0]).toEqual({ fy: 2025, fq: 4 });
    expect(sel.window[11]).toEqual({ fy: 2023, fq: 1 });
  });
  it('takes earnings releases for the same fiscal years as the 10-Ks, not just the 12-quarter window', () => {
    // /model-kpis needs every year's reconciliations and /model-price-history every quarter's release date
    // (house default); transcripts and decks still use the 12-quarter window.
    expect(sel.releaseWindow).toHaveLength(40);
    expect(sel.releaseWindow.at(-1)).toEqual({ fy: 2016, fq: 1 });
    expect(new Set(sel.releases.map((r) => r.fy))).toEqual(new Set(sel.tenKs.map((k) => k.fy)));
    expect(sel.releases.find((r) => r.filingDate === '2026-01-28')).toMatchObject({ fy: 2025, fq: 4 });
    expect(sel.window).toHaveLength(12);
  });
  it('skips amendments instead of letting them replace the original', () => {
    expect(sel.skipped.map((f) => f.form)).toEqual(['10-K/A']);
    expect(sel.tenKs.find((f) => f.fy === 2024).form).toBe('10-K');
  });
  it('keeps Reg FD 8-Ks from the last 3 years only', () => {
    expect(sel.regFd.map((f) => f.filingDate)).toEqual(['2024-06-13']);
  });
});

describe('selectFilings when earnings are out but the 10-Q is not', () => {
  const filings = [
    ...decemberCompany(),
    { accn: 'new', form: '8-K', reportDate: '', filingDate: '2026-04-24', primaryDocument: 'd.htm', items: '2.02,9.01' },
  ];
  const sel = selectFilings({ filings, fiscalTags: new Map(), fiscalYearEnd: '1231' });
  it('anchors the window on the newest release quarter', () => {
    expect(sel.window[0]).toEqual({ fy: 2026, fq: 1 });
    expect(sel.window[11]).toEqual({ fy: 2023, fq: 2 });
    expect(sel.releases.find((r) => r.accn === 'new')).toMatchObject({ fy: 2026, fq: 1 });
  });
  it("keeps the current year's 10-Qs alongside the 10 years of 10-K quarters", () => {
    const withQ1 = selectFilings({
      filings: [...filings, { accn: 'q1', form: '10-Q', reportDate: '2026-03-31', filingDate: '2026-05-05', primaryDocument: 'q.htm', items: '' }],
      fiscalTags: new Map(), fiscalYearEnd: '1231',
    });
    expect(withQ1.tenQs).toHaveLength(31);
    expect(withQ1.tenQs[0]).toMatchObject({ fy: 2026, fq: 1 });
  });
});

describe('selectFilings dedupe and transition reports', () => {
  const mk = (accn, form, reportDate, filingDate) => ({ accn, form, reportDate, filingDate, primaryDocument: 'd.htm', items: '' });
  it('keeps two 10-Ks with distinct period ends even if XBRL fy tags collide', () => {
    const filings = [mk('k1', '10-K', '2024-12-31', '2025-02-10'), mk('k2', '10-K', '2023-12-31', '2024-02-10')];
    const fiscalTags = new Map([['k1', { fy: 2024, fq: 4 }], ['k2', { fy: 2024, fq: 4 }]]);
    const sel = selectFilings({ filings, fiscalTags, fiscalYearEnd: '1231' });
    expect(sel.tenKs.map((f) => f.accn)).toEqual(['k1', 'k2']);
  });
  it('reports transition filings within the 10-year span, not older amendments', () => {
    const filings = [
      mk('k1', '10-K', '2024-12-31', '2025-02-10'), mk('k2', '10-K', '2015-12-31', '2016-02-10'),
      mk('t1', '10-KT', '2021-12-31', '2022-03-01'), mk('a1', '10-K/A', '2009-12-31', '2010-03-01'),
    ];
    const sel = selectFilings({ filings, fiscalTags: new Map(), fiscalYearEnd: '1231' });
    expect(sel.skipped.map((f) => f.accn)).toEqual(['t1']);
  });
});

describe('selectFilings with a non-December year end', () => {
  const filings = [
    { accn: 'a1', form: '10-Q', reportDate: '2024-12-28', filingDate: '2025-01-31', primaryDocument: 'q.htm', items: '' },
    { accn: 'a2', form: '10-K', reportDate: '2024-09-28', filingDate: '2024-11-01', primaryDocument: 'k.htm', items: '' },
  ];
  it('falls back to period-end math when XBRL tags are absent (Apple)', () => {
    const sel = selectFilings({ filings, fiscalTags: new Map(), fiscalYearEnd: '0928' });
    expect(sel.tenQs[0]).toMatchObject({ fy: 2025, fq: 1 });
    expect(sel.tenKs[0]).toMatchObject({ fy: 2024, fq: 4 });
  });
  it("prefers the company's own XBRL fiscal tags (retailer naming)", () => {
    const sel = selectFilings({ filings, fiscalTags: new Map([['a1', { fy: 2024, fq: 1 }]]), fiscalYearEnd: '0928' });
    expect(sel.tenQs[0]).toMatchObject({ fy: 2024, fq: 1 });
  });
});

describe('parsers', () => {
  it('flattens EDGAR column arrays into rows', () => {
    const rows = rowsFromColumns({
      accessionNumber: ['x'], form: ['8-K'], filingDate: ['2025-01-01'], reportDate: [''], primaryDocument: ['d.htm'], items: ['2.02'],
    });
    expect(rows).toEqual([{ accn: 'x', form: '8-K', filingDate: '2025-01-01', reportDate: '', primaryDocument: 'd.htm', items: '2.02' }]);
  });
  it('reads fy/fp per accession from the dei concept, first entry wins', () => {
    const tags = parseFiscalTags({ units: { shares: [
      { accn: 'a', fy: 2025, fp: 'Q1' }, { accn: 'a', fy: 2025, fp: 'Q1' },
      { accn: 'b', fy: 2024, fp: 'FY' }, { accn: 'c', fy: 2024, fp: 'H1' },
    ] } });
    expect([...tags]).toEqual([['a', { fy: 2025, fq: 1 }], ['b', { fy: 2024, fq: 4 }]]);
  });
  it('lists EX-99 exhibits from a filing index page with absolute URLs', () => {
    const html = `<table class="tableFile" summary="Document Format Files">
      <tr><th>Seq</th><th>Description</th><th>Document</th><th>Type</th><th>Size</th></tr>
      <tr><td>1</td><td>8-K</td><td><a href="/ix?doc=/Archives/edgar/data/1/000/k.htm">k.htm</a></td><td>8-K</td><td>1</td></tr>
      <tr><td>2</td><td>PRESS RELEASE</td><td><a href="/Archives/edgar/data/1/000/ex991.htm">ex991.htm</a></td><td>EX-99.1</td><td>1</td></tr>
      <tr><td>3</td><td>INVESTOR PRESENTATION</td><td><a href="/Archives/edgar/data/1/000/ex992.pdf">ex992.pdf</a></td><td>EX-99.2</td><td>1</td></tr>
    </table>`;
    expect(parseExhibitIndex(html)).toEqual([
      { type: 'EX-99.1', description: 'PRESS RELEASE', url: 'https://www.sec.gov/Archives/edgar/data/1/000/ex991.htm' },
      { type: 'EX-99.2', description: 'INVESTOR PRESENTATION', url: 'https://www.sec.gov/Archives/edgar/data/1/000/ex992.pdf' },
    ]);
  });
  it('separates press releases from decks', () => {
    expect(classifyExhibit({ type: 'EX-99.1', description: 'Press release', url: 'https://x/ex991.htm' })).toBe('release');
    expect(classifyExhibit({ type: 'EX-99.2', description: 'Investor Presentation', url: 'https://x/ex992.htm' })).toBe('deck');
    expect(classifyExhibit({ type: 'EX-99.2', description: '', url: 'https://x/slides.pdf' })).toBe('deck');
  });
  it('builds an Archives URL without dashes or CIK padding', () => {
    expect(filingUrl('0001318605', { accn: '0001628280-25-000001', primaryDocument: 'k.htm' }))
      .toBe('https://www.sec.gov/Archives/edgar/data/1318605/000162828025000001/k.htm');
  });
});

describe('selectProxies', () => {
  const k = (fy, filingDate) => ({ fy, filingDate });
  const p = (filingDate) => ({ form: 'DEF 14A', filingDate });
  const tenKs = [k(2025, '2026-02-10'), k(2024, '2025-02-10'), k(2023, '2024-02-10')];

  it('pairs each 10-K with the annual proxy that follows it, so the pay tables match that fiscal year', () => {
    const r = selectProxies([p('2025-04-01'), p('2024-04-02'), { form: 'DEFA14A', filingDate: '2025-04-03' }], tenKs);
    expect(r.map((x) => x.proxy?.filingDate)).toEqual([undefined, '2025-04-01', '2024-04-02']);
  });

  it('skips a later special-meeting proxy in the same year (annual proxies only)', () => {
    const r = selectProxies([p('2025-04-01'), p('2025-10-15')], tenKs);
    expect(r[1].proxy.filingDate).toBe('2025-04-01');
    expect(r[0].proxy).toBeNull();
  });

  it('accepts a proxy filed shortly before its 10-K', () => {
    expect(selectProxies([p('2025-02-01')], tenKs)[1].proxy.filingDate).toBe('2025-02-01');
  });
});
