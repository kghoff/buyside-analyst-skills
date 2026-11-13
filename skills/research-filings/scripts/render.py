"""Step 13 - Markdown report -> styled HTML -> PDF with WeasyPrint (pip install weasyprint; on a Mac also brew install pango).

usage: python3 render.py <report.md | sections dir> <out.pdf> --footer "DXCM filings research · Nov 2026" [--preview DIR] [--no-toc]
A sections directory is joined in file-name order first and saved as <out>.md next to the PDF.
Markup: <div class="cover">...</div>; KPI tiles <div class="kpis"><div class="kpi"><div class="v">$4.7B</div>
<div class="l">FY2025 revenue</div></div></div>; callouts '> [!KEY] / [!MODEL] / [!WATCH] / [!Q] / [!NOTE] text';
every h2 starts a page ('## Title {: .nobreak }' keeps it on the current page). Images relative to the markdown are
inlined, so the PDF stands alone.
Contents: unless --no-toc, a "Contents" page (h2 and h3, clickable, dotted leader, page number) follows the
<div class="cover"> block (or opens the document if there is no cover). Page numbers come from CSS target-counter().
Citations: the .md keeps bracket citations ([DXCM 2025 10-K, Item 1 / Products]); at render time each becomes a footnote
at the foot of its page, numbered from 1 in each h2 section. Blue = company document, orange = our own work (text
starting "Calc", "Model" or "price.csv"), purple = an outside view in the street research (first source is a web page, or a sell-side
report / investor letter named '<date> <firm> <type> - <title>'). '[unconfirmed]' is a flag, not a citation, and prints
as a small yellow pill.
--preview DIR writes PNGs of pages 1-3 and every 5th page for a visual check."""
import argparse, base64, glob, html as html_lib, os, re, subprocess, sys

import markdown

LIB_DIRS = ["/opt/homebrew/lib", "/usr/local/lib"]   # Homebrew pango; python.org Python doesn't look there by itself
LABELS = {"key": "Key takeaway", "model": "Modeling implication", "q": "Your question", "watch": "Watch item",
          "note": "Note"}
CSS = """
@page { size: Letter; margin: 0.7in 0.75in 0.75in 0.75in;
  @bottom-left { content: "__FOOTER__"; font: 7pt Inter, Helvetica, sans-serif; color: #8a8984; }
  @bottom-right { content: counter(page); font: 7pt Inter, Helvetica, sans-serif; color: #8a8984; } }
:root { --ink:#0b0b0b; --ink2:#52514e; --rule:#e6e5e1; --accent:#184f95; --accent2:#2a78d6; --tint:#f4f7fc; }
html { font-family: Inter, Helvetica, sans-serif; font-size: 10pt; color: var(--ink); line-height: 1.5;
  -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body { margin: 0; }
h1 { font-size: 24pt; color: var(--accent); margin: 0 0 4pt; }
h2 { font-size: 15pt; color: var(--accent); border-bottom: 2px solid var(--accent); padding-bottom: 3pt;
  margin: 22pt 0 8pt; break-after: avoid; break-before: page; }
h2.nobreak, h2:first-of-type { break-before: auto; }
h3 { font-size: 11.5pt; margin: 14pt 0 4pt; break-after: avoid; }
h4 { font-size: 10pt; color: var(--ink2); margin: 10pt 0 2pt; text-transform: uppercase; letter-spacing: .4pt; break-after: avoid; }
p { margin: 0 0 7pt; } ul, ol { margin: 0 0 8pt; padding-left: 16pt; } ul > li::marker { content: "•  "; font-size: 1.3em; } .toc li::marker { content: none; } li { margin: 0 0 2.5pt; }
table { border-collapse: collapse; width: 100%; margin: 6pt 0 10pt; font-size: 8.4pt; }
thead { display: table-header-group; } tr { break-inside: avoid; }
th { background: var(--accent); color: #fff; text-align: left; padding: 4pt 5pt; font-weight: 600; }
td { padding: 3.5pt 5pt; border-bottom: 1px solid var(--rule); vertical-align: top; }
tr:nth-child(even) td { background: #fafaf8; }
img { max-width: 100%; display: block; margin: 6pt auto 2pt; }
figure { margin: 4pt 0 10pt; break-inside: avoid; } figcaption { font-size: 8pt; color: var(--ink2); }
code { font-size: 8.5pt; background: #f3f2ef; padding: 0 2pt; border-radius: 2pt; }
.callout { border-left: 4px solid var(--accent2); background: var(--tint); padding: 6pt 10pt; margin: 8pt 0 10pt;
  break-inside: avoid; border-radius: 0 3pt 3pt 0; }
.callout .clabel { font-size: 7.5pt; text-transform: uppercase; letter-spacing: .6pt; font-weight: 700; color: var(--accent); margin-bottom: 2pt; }
.callout.model { border-color: #1baf7a; background: #f1faf6; } .callout.model .clabel { color: #0b7a52; }
.callout.watch { border-color: #eb6834; background: #fdf4ef; } .callout.watch .clabel { color: #b4441a; }
.callout.q { border-color: #6250d6; background: #f5f3fd; } .callout.q .clabel { color: #4a3aa7; }
.callout p:last-child { margin-bottom: 0; }
blockquote { margin: 6pt 0 8pt; padding: 2pt 10pt; border-left: 3px solid var(--rule); color: var(--ink2); font-style: italic; }
.cover { height: 9.2in; display: flex; flex-direction: column; justify-content: space-between; break-after: page; }
.cover .band { background: var(--accent); color: #fff; padding: 28pt 26pt; border-radius: 4pt; }
.cover .band h1 { color: #fff; font-size: 30pt; margin: 0; } .cover .band .sub { font-size: 13pt; opacity: .9; margin-top: 6pt; }
.cover .meta { font-size: 9pt; color: var(--ink2); }
.kpis { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8pt; margin: 8pt 0 12pt; }
.kpi { border: 1px solid var(--rule); border-radius: 4pt; padding: 7pt 9pt; }
.kpi .v { font-size: 16pt; font-weight: 700; color: var(--accent); } .kpi .l { font-size: 7.8pt; color: var(--ink2); }
.drivers { border: 2px solid var(--accent); border-radius: 4pt; padding: 8pt 12pt; margin: 8pt 0 12pt; break-inside: avoid; }
a { color: var(--accent2); text-decoration: none; }
.toc { break-after: page; }
.toc .toc-title { font-size: 15pt; font-weight: 700; color: var(--accent); border-bottom: 2px solid var(--accent); padding-bottom: 3pt; margin: 0 0 10pt; }
.toc ul { list-style: none; padding: 0; margin: 0; } .toc li { margin: 0; break-inside: avoid; }
.toc a { display: flex; align-items: baseline; }
.toc .l2 a { font-size: 10pt; font-weight: 600; color: var(--accent); margin-top: 6pt; }
.toc .l3 a { font-size: 8.8pt; color: var(--ink2); padding-left: 14pt; }
.toc .d { flex: 1; border-bottom: 1px dotted #b9b8b3; margin: 0 4pt; min-width: 12pt; }
.toc .n { min-width: 2.2em; text-align: right; font-variant-numeric: tabular-nums; }
.toc .n::after { content: target-counter(attr(data-target url), page); }
h1, h2 { counter-reset: footnote; }   /* sections 09-12 use h1 with h2 sub-sections */
@page { @footnote { border-top: 0.5pt solid #cfcfcf; padding-top: 5pt; margin-top: 10pt; } }
.fn { float: footnote; footnote-policy: line; font-size: 7.2pt; color: #52514e; line-height: 1.3; font-weight: 400; font-style: normal;
  text-transform: none; letter-spacing: 0; text-align: left; }
.fn::footnote-call { content: counter(footnote); vertical-align: super; font-size: 6.3pt; line-height: 0; color: #2a78d6; font-weight: 700; padding-left: 0.5pt; }
.fn.calc::footnote-call { color: #d0611f; }
.fn.ext::footnote-call { color: #6250d6; }
.fn::footnote-marker { content: counter(footnote) ". "; color: #2a78d6; font-weight: 700; }
.fn.calc::footnote-marker { color: #d0611f; }
.fn.ext::footnote-marker { color: #6250d6; }
.fnkeep { break-inside: avoid; } .fnbreak { break-before: page; }
.flag { font-size: 7pt; background: #fff3cd; color: #8a6100; border-radius: 2pt; padding: 0 3pt; font-weight: 600; }
"""


def join_sections(d):
    return "\n\n".join(open(p, encoding="utf-8").read().strip() for p in sorted(glob.glob(os.path.join(d, "*.md")))) + "\n"


def _callouts(html):
    def rep(m):
        kind = m.group(1).lower()
        return f'<div class="callout {kind}"><div class="clabel">{LABELS.get(kind, kind.title())}</div><p>{m.group(2)}</div>'
    return re.sub(r"<blockquote>\s*<p>\[!(\w+)\]\s*(.*?)</blockquote>", rep, html, flags=re.S)


# a citation is bracket text of 3+ characters on one line; '[!KEY]' callouts and '[text](url)' links are not.
# 3+ skips editorial brackets inside quotes ("move[s]"). No upper limit: multi-source citations run to 2,000 characters.
CITE = re.compile(r"\[(?!!)([^\[\]\n]{3,})\](?!\()")
OWN_WORK = re.compile(r"(Calc|Model|price\.csv)\b")
# The street research's outside views: a web page (its first source holds a URL) or a sell-side report / investor letter, which
# /collect-documents names '<date> <firm> <type> - <title>'; no company document label has that shape.
OUTSIDE = re.compile(r".*https?://|\d{4}-\d{2}-\d{2} [^,]*? - ")   # matched on the first source only


def _cite(m):
    text = m.group(1).strip()
    if text.lower() == "unconfirmed":
        return '<span class="flag">unconfirmed</span>'
    first = html_lib.unescape(text).split(";")[0]   # the text is HTML here: '&amp;' must not split a firm name
    kind = "calc" if OWN_WORK.match(text) else "ext" if OUTSIDE.match(first) else "co"
    return f'<span class="fn {kind}">{text}</span>'


def _citations(html):
    """Bracket citations in the text -> footnote spans. Tags (attributes) and <code>/<pre> contents are left alone."""
    out, skip = [], 0
    for part in re.split(r"(<[^>]+>)", html):
        if part.startswith("<"):
            tag = re.match(r"</?(\w+)", part)
            if tag and tag.group(1).lower() in ("code", "pre", "style", "script"):
                skip += -1 if part.startswith("</") else 1
            out.append(part)
        else:
            out.append(part if skip else CITE.sub(_cite, part))
    return "".join(out)


LIST_ITEM = re.compile(r"^(>\s?)*\s{0,3}(?:[-*]|\d+\.)\s+")


def _space_lists(md):
    """Python-markdown needs a blank line before a list; writers often leave it out. Inside a callout a '>' line is used."""
    out, fence, prev = [], False, ""
    for line in md.split("\n"):
        if line.lstrip().startswith("```"):
            fence = not fence
        elif not fence and LIST_ITEM.match(line) and prev.strip() and not LIST_ITEM.match(prev) \
                and not prev.startswith((" ", "\t", "|")) and not line.lstrip().startswith("|"):
            quoted = line.startswith(">")
            if quoted and prev.startswith(">") and prev.strip(" >"):
                out.append(">")
            elif not quoted:
                out.append("")
        out.append(line)
        prev = line
    return "\n".join(out)


def _slug(text, used):
    base = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60] or "section"
    slug, k = base, 2
    while slug in used:
        slug, k = f"{base}-{k}", k + 1
    used.add(slug)
    return slug


def _cover_end(html):
    """Index just past the closing tag of the first <div class="cover"> block, or 0 if there is none."""
    m = re.search(r'<div class="cover"', html)
    if not m:
        return 0
    depth = 0
    for t in re.finditer(r"<div\b|</div>", html[m.start():]):
        depth += 1 if t.group() != "</div>" else -1
        if depth == 0:
            return m.start() + t.end()
    return 0


def _build(md, base_dir, footer, toc=False):
    """(html, entries). entries: [{id, level, title}] for every h2/h3 after the cover, in order."""
    md = re.sub(r"\n\s*\n(?=> ?\[!)", "\n\n<!-- -->\n\n", md)   # python-markdown would merge back-to-back callouts
    md = _space_lists(md)
    body = _citations(_callouts(markdown.markdown(md, extensions=["tables", "attr_list", "sane_lists", "md_in_html"])))

    def img(m):
        p = os.path.join(base_dir, m.group(1))
        if not os.path.exists(p):
            return m.group(0)
        ext = os.path.splitext(p)[1][1:].lower().replace("jpg", "jpeg")
        return f'src="data:image/{ext};base64,{base64.b64encode(open(p, "rb").read()).decode()}"'

    body = re.sub(r'src="([^"]+)"', img, body)
    cut = _cover_end(body)
    head, rest = body[:cut], body[cut:]
    entries, used = [], set(re.findall(r'\bid="([^"]+)"', body))

    def heading(m):
        level, attrs, inner = m.group(1), m.group(2), m.group(3)
        title = re.sub(r"\s+", " ", html_lib.unescape(re.sub(r"<[^>]+>", "", inner))).strip()
        idm = re.search(r'\bid="([^"]+)"', attrs)
        hid = idm.group(1) if idm else _slug(title, used)
        entries.append({"id": hid, "level": int(level), "title": title})
        return m.group(0) if idm else f'<h{level}{attrs} id="{hid}">{inner}</h{level}>'

    rest = re.sub(r"<h([23])([^>]*)>(.*?)</h\1>", heading, rest, flags=re.S)
    if toc and entries:
        items = "".join(
            f'<li class="l{e["level"]}"><a href="#{e["id"]}"><span class="t">{html_lib.escape(e["title"])}</span>'
            f'<span class="d"></span><span class="n" data-target="#{e["id"]}"></span></a></li>' for e in entries)
        head += f'<div class="toc"><div class="toc-title">Contents</div><ul>{items}</ul></div>'
    css = CSS.replace("__FOOTER__", footer.replace("\\", "\\\\").replace('"', '\\"'))
    html = (f"<!doctype html><html><head><meta charset='utf-8'><title>{footer}</title><style>{css}</style></head>"
            f"<body>{head}{rest}</body></html>")
    return html, entries


def to_html(md, base_dir, footer, toc=False):
    return _build(md, base_dir, footer, toc)[0]


def _print_pdf(html, out):
    """WeasyPrint runs in its own process (this file with --weasyprint) so the Homebrew library path can be set before
    pango loads. Its warnings (footnotes it could not place) are passed on to stderr."""
    html_path = os.path.splitext(out)[0] + ".html"
    open(html_path, "w", encoding="utf-8").write(html)
    env = dict(os.environ)
    env["DYLD_FALLBACK_LIBRARY_PATH"] = ":".join(filter(None, [env.get("DYLD_FALLBACK_LIBRARY_PATH"), *LIB_DIRS]))
    try:
        r = subprocess.run([sys.executable, os.path.abspath(__file__), "--weasyprint", html_path, os.path.abspath(out)],
                           env=env, timeout=1800, capture_output=True, text=True)
    finally:
        if os.path.exists(html_path):
            os.remove(html_path)
    if r.returncode or not os.path.exists(out) or os.path.getsize(out) == 0:
        raise SystemExit("WeasyPrint wrote no PDF:\n" + r.stderr[-3000:])
    for line in r.stderr.splitlines():
        if line.startswith("WARNING"):
            print(line, file=sys.stderr)


def _misplaced_notes(doc, root):
    """[(index, call page, note page or None)] for footnotes whose note is not on the page of its call. WeasyPrint
    (68-70) can push a note to the next page to make room, or drop the note of a call on a page's last line."""
    fns = [e for e in root.iter() if (e.get("class") or "").split()[:1] == ["fn"]]
    call, note = {}, {}

    def walk(box, page, area):
        if getattr(box, "footnote", None) is not None:
            call.setdefault(id(box.footnote.element), page)
        elif area and "::" not in (box.element_tag or "") and getattr(box, "element", None) is not None:
            note.setdefault(id(box.element), page)
        for child in getattr(box, "children", None) or []:
            walk(child, page, area or type(box).__name__ == "FootnoteAreaBox")

    for page, p in enumerate(doc.pages, 1):
        walk(p._page_box, page, False)
        if getattr(p._page_box, "footnote_area", None) is not None:
            walk(p._page_box.footnote_area, page, True)
    return [(i, call.get(id(e)), note.get(id(e))) for i, e in enumerate(fns) if note.get(id(e)) != call.get(id(e))]


def _keep_together(html, indexes):
    """Mark the paragraph / list item / table row holding each listed footnote call so it moves to the next page
    whole (fnkeep); a block already marked and still misplaced starts a new page (fnbreak)."""
    starts = [m.start() for m in re.finditer(r'<span class="fn ', html)]
    ends = set()
    for i in indexes:
        block = max((m for m in re.finditer(r"<(p|li|tr|figcaption)\b", html[:starts[i]])), key=lambda m: m.start(), default=None)
        if block:
            li = re.search(r"<li\b(?=[^>]*>\s*$)", html[:block.start()])   # WeasyPrint ignores breaks on a list item's first <p>
            ends.add(li.end() if li else block.end())
    for end in sorted(ends, reverse=True):
        if html.startswith(' class="fnkeep"', end):
            html = html[:end] + ' class="fnbreak"' + html[end + len(' class="fnkeep"'):]
        elif not html.startswith(' class="fnbreak"', end):
            html = html[:end] + ' class="fnkeep"' + html[end:]
    return html


def _weasyprint(html_path, out):
    """Lay out, move any block whose footnote landed on another page (or vanished) to the next page whole, repeat
    up to 5 times, then write the PDF and warn about anything still misplaced."""
    from weasyprint import HTML
    html = open(html_path, encoding="utf-8").read()
    for _ in range(5):
        page = HTML(string=html, base_url=html_path)
        doc = page.render()
        bad = _misplaced_notes(doc, page.etree_element)
        if not bad:
            break
        html = _keep_together(html, [i for i, _, _ in bad])
    doc.write_pdf(out)
    texts = [html_lib.unescape(re.sub(r"\s+", " ", m.group(1))) for m in re.finditer(r'<span class="fn \w+">(.*?)</span>', html, re.S)]
    for i, c, n in bad:
        print(f"WARNING: footnote on page {c} {'printed on page ' + str(n) if n else 'missing'}: {texts[i][:100]}",
              file=sys.stderr)


def render(src, out, footer, preview=None, toc=True):
    if os.path.isdir(src):
        md, base = join_sections(src), os.path.dirname(os.path.abspath(src))
        open(os.path.splitext(out)[0] + ".md", "w", encoding="utf-8").write(md)
    else:
        md, base = open(src, encoding="utf-8").read(), os.path.dirname(os.path.abspath(src))
    html, _ = _build(md, base, footer, toc)
    _print_pdf(html, out)
    if preview:
        os.makedirs(preview, exist_ok=True)
        info = subprocess.run(["pdfinfo", out], capture_output=True, text=True).stdout
        n = int(re.search(r"Pages:\s+(\d+)", info).group(1))
        for p in sorted({1, 2, 3, *range(5, n + 1, 5)} & set(range(1, n + 1))):
            subprocess.run(["pdftoppm", "-r", "60", "-png", "-f", str(p), "-l", str(p), out,
                            os.path.join(preview, f"page-{p:03d}")], check=True)
    return out


if __name__ == "__main__":
    if sys.argv[1:2] == ["--weasyprint"]:
        _weasyprint(*sys.argv[2:4])
        sys.exit()
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("out")
    ap.add_argument("--footer", required=True)
    ap.add_argument("--preview")
    ap.add_argument("--no-toc", action="store_true")
    a = ap.parse_args()
    print("wrote", render(a.src, a.out, a.footer, a.preview, toc=not a.no_toc))
