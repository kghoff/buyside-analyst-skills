// EDGAR HTML → Markdown. Copied from an earlier project's
// filing assembler (cleanEdgarHtml, convertToMarkdown).
// CLI (used by the IR agent): node convert.mjs <in.html> <out.md>

import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { dirname } from 'node:path';
import { pathToFileURL } from 'node:url';
import * as cheerio from 'cheerio';
import TurndownService from 'turndown';
import { gfm } from 'turndown-plugin-gfm';

export function cleanEdgarHtml(htmlString) {
  const $ = cheerio.load(htmlString);

  // 1. Remove hidden iXBRL elements (machine-only metadata)
  $('ix\\:hidden, ix\\:header, ix\\:references').remove();

  // 2. Unwrap visible iXBRL elements (keep text content, strip the tag)
  const unwrapSelectors = [
    'ix\\:nonfraction', 'ix\\:nonnumeric', 'ix\\:fraction',
    'ix\\:continuation', 'ix\\:exclude',
  ];
  for (const sel of unwrapSelectors) {
    $(sel).each((_, el) => {
      $(el).replaceWith($(el).contents());
    });
  }

  // 3. Remove non-content elements
  $('script, style, link, meta').remove();

  // 4. Strip style and class attributes from all elements
  $('*').removeAttr('style').removeAttr('class');

  return $('body').html() || $.html();
}

let turndownInstance = null;

function getTurndown() {
  if (!turndownInstance) {
    turndownInstance = new TurndownService({
      headingStyle: 'atx',
      codeBlockStyle: 'fenced',
      bulletListMarker: '-',
      emDelimiter: '*',
    });

    // Custom table rule for complex EDGAR tables; must precede the gfm plugin.
    turndownInstance.addRule('edgarTables', {
      filter: 'table',
      replacement: (_content, node) => tableToMarkdown(node),
    });

    turndownInstance.use(gfm);

    // Unwrap <font> tags (EDGAR uses these heavily for styling)
    turndownInstance.addRule('font', {
      filter: 'font',
      replacement: (content) => content,
    });

    // Remove empty links
    turndownInstance.addRule('emptyLinks', {
      filter: (node) => node.nodeName === 'A' && !node.getAttribute('href'),
      replacement: (content) => content,
    });
  }
  return turndownInstance;
}

function cellText(td) {
  return (td.textContent || '').replace(/ /g, ' ').replace(/\s+/g, ' ').trim();
}

function tableToMarkdown(tableEl) {
  const rows = Array.from(tableEl.querySelectorAll('tr'));
  if (rows.length === 0) return '';

  const mdRows = [];
  for (const row of rows) {
    const cells = row.querySelectorAll('td, th');
    const cellTexts = Array.from(cells).map(cellText);
    if (cellTexts.every((t) => t === '')) continue;
    mdRows.push('| ' + cellTexts.join(' | ') + ' |');
  }

  if (mdRows.length === 0) return '';

  const firstRowCols = mdRows[0].split('|').length - 2;
  const separator = '| ' + Array(firstRowCols).fill('---').join(' | ') + ' |';
  mdRows.splice(1, 0, separator);

  return '\n\n' + mdRows.join('\n') + '\n\n';
}

export function convertToMarkdown(cleanHtml) {
  let md = getTurndown().turndown(cleanHtml);
  md = md.replace(/\n{4,}/g, '\n\n\n');
  md = md.split('\n').map((line) => line.trimEnd()).join('\n');
  return md.trim();
}

function cli() {
  const [input, output] = process.argv.slice(2);
  if (!input || !output) {
    process.stderr.write('usage: convert.mjs <in.html> <out.md>\n');
    process.exit(1);
  }
  try {
    const md = convertToMarkdown(cleanEdgarHtml(readFileSync(input, 'utf8')));
    mkdirSync(dirname(output), { recursive: true });
    writeFileSync(output, `<!-- source: local file -->\n\n${md}\n`);
  } catch (e) {
    process.stderr.write(`convert: ${e.message}\n`);
    process.exit(1);
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) cli();
