"""Build the long pitch deck and the core deck (slides 1-10) from pitch_plan.json and the PowerPoint template.

usage: python3 build_deck.py --plan pitch_plan.json --template assets/pitch_template.pptx --values <recalculated copy>
                             --research <research root> --tabs <work>/tabs --out-long <file>.pptx
                             --out-core <file>.pptx [--unverified anchors.json]

- Each slide uses the template layout named after its type; placeholders are found by idx (make_template.py's map).
  Text placeholders get the plan's text with every {key} replaced by its `shown` (fill.py); the builder only sets
  paragraph levels, the template styles them. Area placeholders are frames: their position is read, a native table or
  chart is drawn there and the placeholder is deleted. Placeholders a slide does not use are deleted.
- Model data is read from the recalculated copy by label or header, never by address: SUM's cap table ("Cap table"
  block) and estimates grid ("Internal estimates" block); Px Data's "Date" and "<T> close" columns with Px Events'
  "Full-results release date" column (setup chart); Multiples' "WEEKLY DATA" block ("Week", "P/E", "S&P 500 P/E",
  "Core-peer median P/E"; valuation chart); Valuation's "Reward / risk ladder" block ("Entry", "Reward", "Risk",
  "R/R"; risk_reward ladder and chart). A tab or label that is missing puts a text note in that area and prints a
  "WARNING:" line; the build goes on.
- Pictures: {"png": <file in --tabs>} or {"pdf": <file under --research>, "page": n, "crop": [x0, y0, x1, y1]}, fitted
  inside the placeholder keeping the aspect ratio.
- Speaker notes = the slide's notes plus one "UNVERIFIED: <problem>" line per --unverified item ({"key"|"quote",
  "rule", "problem"}, from anchors.py --json) whose key or quote the slide uses. Never on the slide face.
- The core deck is built a second time from the plan's first ten slides (slides are not copied between files).
- Writes only the two paths given (they must differ); crops go to a temporary folder."""
import argparse
import datetime as dt
import json
import math
import os
import statistics
import sys
import tempfile

from PIL import Image
from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.chart.data import XyChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE
from pptx.enum.chart import XL_LABEL_POSITION
from pptx.enum.chart import XL_LEGEND_POSITION
from pptx.enum.chart import XL_MARKER_STYLE
from pptx.enum.chart import XL_TICK_LABEL_POSITION
from pptx.enum.dml import MSO_LINE_DASH_STYLE
from pptx.enum.text import PP_ALIGN
from pptx.util import Emu
from pptx.util import Inches
from pptx.util import Pt

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))   # run with python3 -I
from common import THEME  # noqa: E402
from common import load  # noqa: E402
from fill import fill  # noqa: E402

FONT = THEME["font"]
SETUP_YEARS = 3          # the set-up chart shows the last three years of daily closes, as weekly closes
WEEKLY_OVER = 400        # downsample a price series longer than this to the last close of each week
WARNED = set()


def warn(msg):
    if msg not in WARNED:
        WARNED.add(msg)
        print("WARNING:", msg)


def rgb(key):
    return RGBColor.from_string(THEME[key])


# ------------------------------------------------------------------ values copy: read by label or header
def num(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def as_date(v):
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, dt.date):
        return v
    n = num(v)
    return dt.date(1899, 12, 30) + dt.timedelta(days=int(n)) if n and n > 1000 else None


def serial(d):
    return (d - dt.date(1899, 12, 30)).days


class Values:
    """The recalculated copy, each tab read once into a grid of rows (0-based lists)."""

    def __init__(self, path):
        import openpyxl
        self.wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        self.grids = {}

    def grid(self, name):
        if name not in self.grids:
            names = {n.lower(): n for n in self.wb.sheetnames}
            real = names.get(name.lower())
            self.grids[name] = ([list(r) for r in self.wb[real].iter_rows(values_only=True)] if real else None)
        return self.grids[name]


def cell(g, r, c):
    return g[r][c] if 0 <= r < len(g) and 0 <= c < len(g[r]) else None


def text_of(v):
    return v.strip() if isinstance(v, str) else ""


def find(g, pred, rows=None):
    """(row, col) of the first cell, row by row, whose text passes pred."""
    for r in rows if rows is not None else range(len(g)):
        for c, v in enumerate(g[r] if r < len(g) else []):
            if pred(text_of(v)):
                return r, c
    return None


def column_after(g, r0, c):
    """Cells of column c below row r0 until the first empty one: [(row, value)]."""
    out, r = [], r0 + 1
    while cell(g, r, c) not in (None, ""):
        out.append((r, cell(g, r, c)))
        r += 1
    return out


# ------------------------------------------------------------------ formats for model values
def show(v, kind):
    n = num(v)
    if n is None:
        return "n/a" if v not in (None, "") else ""
    return {"px": f"${n:,.2f}", "mn": f"{n:,.0f}", "eps": f"{n:,.2f}", "x": f"{n:,.1f}x", "bps": f"{n:+,.0f}",
            "pct": f"{n:.1%}", "spct": f"{n:+.1%}"}[kind]


def sign_colour(v):
    n = num(v)
    return None if n is None or n == 0 else ("good" if n > 0 else "bad")


def text_sign(t):
    """good / bad from a shown string's sign ('+31%' good, '-15%' or '(15%)' bad); None if unsigned."""
    t = t.strip()
    if t[:1] in "-(−–":
        return "bad"
    return "good" if t[:1] == "+" else None


# ------------------------------------------------------------------ drawing helpers
def frame(ph):
    return ph.left, ph.top, ph.width, ph.height


def drop(shape):
    shape._element.getparent().remove(shape._element)


def runs_font(p, size=None, bold=None, colour=None, italic=None):
    for r in p.runs:
        r.font.name = FONT
        if size:
            r.font.size = Pt(size)
        if bold is not None:
            r.font.bold = bold
        if italic is not None:
            r.font.italic = italic
        if colour:
            r.font.color.rgb = rgb(colour)


def note_box(slide, fr, msg):
    """The fallback: a plain grey note where the table, chart or picture would go."""
    tb = slide.shapes.add_textbox(*fr)
    tb.text_frame.word_wrap = True
    tb.text_frame.text = msg
    runs_font(tb.text_frame.paragraphs[0], 11, colour="grey", italic=True)
    return tb


def paras(ph, items):
    """items: [(text, level)] or [(text, level, bold_prefix)] into a text placeholder."""
    tf = ph.text_frame
    tf.text = ""
    for i, it in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.level = it[1]
        if len(it) > 2 and it[2]:
            p.add_run().text = it[2]
            p.runs[0].font.bold = True
        p.add_run().text = it[0]


def table(slide, fr, header, rows, widths=None, size=10, colours=None, row_h=0.27, bold_rows=()):
    """A native table at the frame: navy header, banded rows, Arial. colours: {(r, c): 'good'|'bad'} on body cells."""
    x, y, w, _ = fr
    nr, nc = len(rows) + 1, len(header)
    shp = slide.shapes.add_table(nr, nc, x, y, w, Emu(int(Inches(row_h)) * nr))
    tbl = shp.table
    widths = widths or [1.0 / nc] * nc
    tot = sum(widths)
    for j, f in enumerate(widths):
        tbl.columns[j].width = Emu(int(w * f / tot))
    for i in range(nr):
        tbl.rows[i].height = Emu(int(Inches(row_h)))
        vals = header if i == 0 else rows[i - 1]
        for j in range(nc):
            c = tbl.cell(i, j)
            c.margin_left = c.margin_right = Inches(0.06)
            c.margin_top = c.margin_bottom = Inches(0.02)
            c.text = str(vals[j]) if j < len(vals) and vals[j] is not None else ""
            p = c.text_frame.paragraphs[0]
            p.alignment = PP_ALIGN.LEFT if j == 0 else PP_ALIGN.RIGHT
            c.fill.solid()
            if i == 0:
                c.fill.fore_color.rgb = rgb("navy")
                runs_font(p, size, bold=True, colour=None)
                for r in p.runs:
                    r.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
            else:
                c.fill.fore_color.rgb = rgb("band") if i % 2 == 0 else RGBColor(0xFF, 0xFF, 0xFF)
                col = (colours or {}).get((i - 1, j))
                runs_font(p, size, bold=(i - 1) in bold_rows, colour=col or "text")
    return shp


def style_chart(ch, legend=True):
    ch.font.name = FONT
    ch.font.size = Pt(9)
    ch.has_legend = legend
    if legend:
        ch.legend.position = XL_LEGEND_POSITION.BOTTOM
        ch.legend.include_in_layout = False
    for ax in (ch.category_axis, ch.value_axis):
        ax.format.line.color.rgb = rgb("line")
        ax.has_major_gridlines = ax is ch.value_axis
        if ax.has_major_gridlines:
            ax.major_gridlines.format.line.color.rgb = rgb("strip")


def line_series(s, colour, width=1.75, dash=None):
    s.format.line.color.rgb = rgb(colour)
    s.format.line.width = Pt(width)
    if dash:
        s.format.line.dash_style = dash
    s.smooth = False


def marker_series(s, colour, size=7):
    s.format.line.fill.background()
    s.marker.style = XL_MARKER_STYLE.CIRCLE
    s.marker.size = size
    s.marker.format.fill.solid()
    s.marker.format.fill.fore_color.rgb = rgb(colour)
    s.marker.format.line.color.rgb = rgb(colour)


def date_axis(ch, d0, d1):
    ax = ch.category_axis
    ax.minimum_scale, ax.maximum_scale = serial(d0), serial(d1)
    span = (d1 - d0).days
    ax.major_unit = 365 if span > 4 * 365 else 182 if span > 540 else 91
    ax.tick_labels.number_format = "mmm yy"
    ax.tick_labels.number_format_is_linked = False


# ------------------------------------------------------------------ pictures
def grab(pdf, page, out, dpi=170, crop=None):
    """One PDF page (1-based), optionally cropped to fractions (left, top, right, bottom), saved as PNG.
    (Pattern from research-filings/scripts/slides.py grab(), Nov 2026; PyMuPDF here instead of pdftoppm.)"""
    import fitz
    doc = fitz.open(pdf)
    if not 1 <= page <= doc.page_count:
        raise ValueError(f"page {page} is outside {os.path.basename(pdf)} (1-{doc.page_count})")
    rect = doc[page - 1].rect
    clip = None
    if crop:
        x0, y0, x1, y1 = crop
        if not (0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1):
            raise ValueError(f"crop {crop} must be (left, top, right, bottom) fractions, left < right, top < bottom")
        clip = fitz.Rect(rect.x0 + x0 * rect.width, rect.y0 + y0 * rect.height,
                         rect.x0 + x1 * rect.width, rect.y0 + y1 * rect.height)
    doc[page - 1].get_pixmap(dpi=dpi, clip=clip).save(out)
    return out


def inside(root, rel):
    p = os.path.realpath(os.path.join(root, rel))
    return p if p.startswith(os.path.realpath(root) + os.sep) else None


class Ctx:
    def __init__(self, plan, values, research, tabs, unverified, tmp):
        self.plan, self.v, self.research, self.tabs, self.tmp = plan, values, research, tabs, tmp
        self.n, self.unverified, self.crops = plan["numbers"], unverified, {}
        self.T = plan.get("ticker", "")

    def f(self, t):
        return fill(t, self.n) if isinstance(t, str) else ("" if t is None else str(t))

    def picture(self, img):
        """Local PNG path for a plan image, or (None, why)."""
        if not isinstance(img, dict):
            return None, "no picture given"
        if img.get("png"):
            p = inside(self.tabs, img["png"])
            return (p, None) if p and os.path.isfile(p) else (None, f"tab picture {img['png']} not found in the tabs folder")
        if img.get("pdf"):
            key = json.dumps(img, sort_keys=True)
            if key not in self.crops:
                src = inside(self.research, img["pdf"])
                if not src or not os.path.isfile(src):
                    self.crops[key] = (None, f"{img['pdf']} not found under the research folder")
                else:
                    out = os.path.join(self.tmp, f"crop{len(self.crops)}.png")
                    try:
                        self.crops[key] = (grab(src, int(img.get("page", 1)), out, crop=img.get("crop")), None)
                    except Exception as e:   # a bad page or crop must not stop the deck; the look step sees the note
                        self.crops[key] = (None, f"{img['pdf']} page {img.get('page')}: {e}")
            return self.crops[key]
        return None, "picture needs png or pdf"


def put_picture(ctx, slide, ph, img, where):
    fr = frame(ph)
    path, why = ctx.picture(img)
    drop(ph)
    if not path:
        warn(f"{where}: {why}")
        return note_box(slide, fr, f"Picture missing: {why}")
    x, y, w, h = fr
    iw, ih = Image.open(path).size
    k = min(w / iw, h / ih)
    pw, ph_ = int(iw * k), int(ih * k)
    return slide.shapes.add_picture(path, x + (w - pw) // 2, y + (h - ph_) // 2, pw, ph_)


# ------------------------------------------------------------------ core slides that read the model
CAP_ROWS = (  # (shown label, SUM label, exact?, after this SUM label, format, plan key fallback)
    ("Price", "Price", False, None, "px", "price"), ("Market cap ($M)", "Market cap", False, None, "mn", None),
    ("Enterprise value ($M)", "Enterprise value", False, None, "mn", None),
    ("3M ADV ($M)", "3M ADV ($M)", True, None, "mn", None), ("Buy price", "Buy price", True, None, "px", "buy_price"),
    ("No-brainer price", "No-brainer price", True, None, "px", "nobrainer_price"),
    ("3-year target", "3-year target price", True, None, "px", "target_3y"),
    ("3-year IRR", "IRR", True, "3-year target price", "pct", "irr_3y"),
    ("12-month base target", "12-month target", True, None, "px", None),
    ("12-month base return", "% return", True, "12-month target", "spct", "base_ret"),
    ("12-month risk price", "Risk price", True, None, "px", None),
    ("12-month risk return", "% return", True, "Risk price", "spct", "risk_ret"),
    ("Blended reward / risk", "Blended reward / risk", True, None, "x", None))
GRID_ROWS = (("Revenue", True), ("Street revenue", True), ("Revenue delta", False), ("EPS (", False),
             ("Street EPS", True), ("Expected Delta", False), ("P/E", True), ("Street P/E", True), ("EV/EBITDA", True))


def cap_table(ctx):
    """[(label, shown, colour)] from SUM's cap table column, or None."""
    g = ctx.v.grid("SUM")
    at = g and find(g, lambda t: t.startswith("Cap table"))
    if not at:
        return None
    r0, c = at
    labels = [(r, text_of(cell(g, r, c))) for r in range(r0 + 1, len(g))]
    out = []
    for shown, lab, exact, after, kind, key in CAP_ROWS:
        start = next((r for r, t in labels if t == after), None) if after else r0
        if start is None:
            continue
        hit = next((r for r, t in labels if r > start and (t == lab if exact else t.startswith(lab))), None)
        v = cell(g, hit, c + 1) if hit is not None else None
        if num(v) is None and key in ctx.n:            # an action price write-pitch fills later: the plan's number
            v_shown, col = ctx.n[key]["shown"], text_sign(ctx.n[key]["shown"]) if kind == "spct" else None
        elif hit is None:
            continue
        else:
            v_shown, col = show(v, kind), sign_colour(v) if kind == "spct" else None
        out.append((shown, v_shown, col))
    return out


def grid_kind(lab):
    low = lab.lower()
    if "bps" in low:
        return "bps"
    if "delta" in low:
        return "spct"
    if "p/e" in low or "ev/" in low:
        return "x"
    if "eps" in low:
        return "eps"
    return "pct" if "%" in low or "margin" in low or "yield" in low else "mn"


def estimates_grid(ctx):
    """(header, rows, colours) of SUM's internal-estimates grid, chosen rows only, or None."""
    g = ctx.v.grid("SUM")
    at = g and find(g, lambda t: t.startswith("Internal estimates"))
    if not at:
        return None
    r0, c0 = at
    yc = [c for c in range(c0 + 1, len(g[r0 + 1]) if r0 + 1 < len(g) else 0) if text_of(cell(g, r0 + 1, c))]
    lab = column_after(g, r0 + 1, c0)
    rows, colours = [], {}
    for want, exact in GRID_ROWS:
        hit = next(((r, text_of(t)) for r, t in lab if (text_of(t) == want if exact else text_of(t).startswith(want))),
                   None)
        if not hit:
            continue
        r, t = hit
        kind = grid_kind(t)
        if kind in ("spct", "bps"):
            for j, c in enumerate(yc, 1):
                if sign_colour(cell(g, r, c)):
                    colours[(len(rows), j)] = sign_colour(cell(g, r, c))
        rows.append([t] + [show(cell(g, r, c), kind) for c in yc])
    if not rows:
        return None
    return [text_of(cell(g, r0 + 1, c0)) or "$M except per share"] + [text_of(cell(g, r0 + 1, c)) for c in yc], rows, colours


def price_history(ctx):
    """(dates, closes, release dates) from Px Data and Px Events, or None."""
    g = ctx.v.grid("Px Data")
    hd = g and find(g, lambda t: t == "Date", range(min(15, len(g))))
    if not hd:
        return None
    r0, dc = hd
    heads = [text_of(v) for v in g[r0]]
    want = f"{ctx.T} close"
    cc = heads.index(want) if want in heads else next(
        (j for j, h in enumerate(heads) if h.endswith(" close") and not h.startswith("SPY")), None)
    if cc is None:
        return None
    pts = []
    for row in g[r0 + 1:]:
        d, p = as_date(cell([row], 0, dc)), num(cell([row], 0, cc))
        if d and p is not None:
            pts.append((d, p))
    if not pts:
        return None
    rel = []
    e = ctx.v.grid("Px Events")
    at = e and find(e, lambda t: t == "Full-results release date", range(min(15, len(e))))
    if at:
        rel = [d for d in (as_date(v) for _, v in column_after(e, *at)) if d]
    else:
        warn("Px Events release dates not found; the set-up chart has no release markers")
    return pts, rel


def weekly(pts):
    """Last point of each ISO week."""
    out = {}
    for d, p in pts:
        out[d.isocalendar()[:2]] = (d, p)
    return list(out.values())


def snap(xs, d):
    """Index of the first grid date on or after d (the line's own point), or None past the end."""
    return next((i for i, x in enumerate(xs) if x >= d), None)


def xy_chart(slide, fr, xs, series, yfmt):
    """A scatter-with-lines chart on one shared x grid of dates. series: [(name, ys)] with None for a gap.
    (LibreOffice drops a scatter series whose x values differ from the others', so every series uses xs.)"""
    cd = XyChartData()
    for name, ys in series:
        sr = cd.add_series(name)
        for x, y in zip(xs, ys):
            sr.add_data_point(serial(x), y)
    ch = slide.shapes.add_chart(XL_CHART_TYPE.XY_SCATTER_LINES_NO_MARKERS, *fr, cd).chart
    style_chart(ch)
    date_axis(ch, xs[0], xs[-1])
    ax = ch.value_axis
    ax.tick_labels.number_format, ax.tick_labels.number_format_is_linked = yfmt, False
    lo = min(y for _, ys in series for y in ys if y is not None) * 0.9
    step = 10 ** math.floor(math.log10(lo)) / 2 if lo > 0 else 0
    ax.minimum_scale = math.floor(lo / step) * step if step else None   # a price or P/E axis need not start at 0
    return ch, list(ch.plots[0].series)


def setup_chart(ctx, slide, ph, s):
    fr = frame(ph)
    drop(ph)
    data = price_history(ctx)
    if not data:
        warn("Px Data price history not found (no 'Date' / '<T> close' header); set-up chart left as a note")
        return note_box(slide, fr, "Px Data price history not found")
    pts, rel = data
    pts.sort()
    d0 = pts[-1][0] - dt.timedelta(days=round(365.25 * SETUP_YEARS))
    pts = [x for x in pts if x[0] >= d0]
    line = weekly(pts) if len(pts) > WEEKLY_OVER else pts
    xs, ys = [d for d, _ in line], [p for _, p in line]
    series = [(f"{ctx.T} close", ys)]
    marks = {snap(xs, d) for d in rel if d >= xs[0]} - {None}
    if marks:
        series.append(("Earnings release", [y if i in marks else None for i, y in enumerate(ys)]))
    events = {}
    for ev in s.get("events") or []:
        try:
            d = dt.date.fromisoformat(str(ev.get("date")))
        except (ValueError, AttributeError):
            d = None
        i = snap(xs, d) if d and d >= xs[0] else None
        if i is None:
            warn(f"set-up event {ev!r} is outside the chart's dates; left off")
            continue
        events[i] = ctx.f(ev.get("label", ""))
    if events:
        series.append(("Key move", [y if i in events else None for i, y in enumerate(ys)]))
    ch, ser = xy_chart(slide, fr, xs, series, '"$"#,##0')
    line_series(ser[0], "navy")
    if marks:
        marker_series(ser[1], "amber", 6)
    if events:
        marker_series(ser[-1], "bad", 8)
        for i, lab in events.items():
            dl = ser[-1].points[i].data_label
            dl.text_frame.text = lab
            dl.position = XL_LABEL_POSITION.ABOVE
            runs_font(dl.text_frame.paragraphs[0], 8, colour="text")
    return ch


def pe_history(ctx):
    """(weeks, {header: [value or None]}) for P/E and the S&P / core-peer lines from Multiples' weekly block, or None."""
    g = ctx.v.grid("Multiples")
    at = g and find(g, lambda t: t == "WEEKLY DATA")
    if not at or at[0] + 1 >= len(g):
        return None
    hr = at[0] + 1
    heads = [text_of(v) for v in g[hr]]
    if "Week" not in heads or "P/E" not in heads:
        return None
    wc, weeks, out = heads.index("Week"), [], {}
    rows = []
    for row in g[hr + 1:]:
        d = as_date(cell([row], 0, wc))
        if not d:
            break
        weeks.append(d)
        rows.append(row)
    for h in ("P/E", "S&P 500 P/E", "Core-peer median P/E"):
        if h in heads:
            ys = [num(cell([r], 0, heads.index(h))) for r in rows]
            ys = [y if y is not None and y > 0 else None for y in ys]     # #N/A and negative P/E are gaps
            if any(ys):
                out[h] = ys
    return (weeks, out) if out.get("P/E") else None


def valuation_chart(ctx, slide, ph):
    fr = frame(ph)
    drop(ph)
    data = pe_history(ctx)
    if not data:
        warn("Multiples P/E history not found (no 'WEEKLY DATA' block with 'Week' and 'P/E'); chart left as a note")
        return note_box(slide, fr, "Multiples P/E history not found")
    weeks, cols = data
    med = statistics.median(y for y in cols["P/E"] if y is not None)
    order = [("P/E", f"{ctx.T} P/E", "navy", None), ("median", f"{ctx.T} median {med:.1f}x", "grey", "dash"),
             ("S&P 500 P/E", "S&P 500 P/E", "amber", None), ("Core-peer median P/E", "Core-peer median P/E", "good", None)]
    order = [o for o in order if o[0] == "median" or o[0] in cols]
    series = [(name, [med] * len(weeks) if key == "median" else cols[key]) for key, name, _, _ in order]
    ch, ser = xy_chart(slide, fr, weeks, series, '0"x"')
    for sr, (_, _, colour, dash) in zip(ser, order):
        line_series(sr, colour, 1.25 if dash else 1.75, MSO_LINE_DASH_STYLE.DASH if dash else None)
    return ch



def ladder(ctx):
    """[(step, entry, reward, risk, rr)] from Valuation's reward / risk ladder block, or None."""
    g = ctx.v.grid("Valuation")
    at = g and find(g, lambda t: "reward / risk ladder" in t.lower())
    if not at:
        return None
    r0, c0 = at
    heads = [text_of(v) for v in g[r0]]
    if not all(h in heads for h in ("Entry", "Reward", "Risk", "R/R")):
        return None
    cols = [heads.index(h) for h in ("Entry", "Reward", "Risk", "R/R")]
    out, r = [], r0 + 1
    while num(cell(g, r, c0)) is not None:
        out.append([num(cell(g, r, c0))] + [cell(g, r, c) for c in cols])
        r += 1
    return out or None


def risk_reward(ctx, slide, ph, s):
    cases = s.get("cases") or []
    rows = [[ctx.f(c.get(k, "")) for k in ("name", "eps", "pe", "ret", "prob")] for c in cases]
    colours = {(i, 3): text_sign(r[3]) for i, r in enumerate(rows) if text_sign(r[3])}
    table(slide, frame(ph[12]), ["Case", "EPS", "P/E", "12-mo return", "Probability"], rows, [1.3, 1, 1, 1.3, 1.2],
          colours=colours)
    drop(ph[12])
    lad = ladder(ctx)
    fr13, fr14 = frame(ph[13]), frame(ph[14])
    drop(ph[13]), drop(ph[14])
    if not lad:
        warn("Valuation reward / risk ladder not found; ladder and chart left as notes")
        note_box(slide, fr13, "Valuation R/R ladder not found")
        note_box(slide, fr14, "Valuation R/R ladder not found")
    else:
        body, cl = [], {}
        for i, (st, e, up, down, rr) in enumerate(lad):
            body.append(["today" if st == 0 else f"{st:+.0%}", show(e, "px"), show(up, "spct"), show(down, "pct"),
                         show(rr, "x")])
            cl[(i, 2)], cl[(i, 3)] = "good", "bad"
        today = [i for i, x in enumerate(lad) if x[0] == 0]
        table(slide, fr13, ["Entry vs today", "Entry", "Reward", "Risk", "R/R"], body, [1.3, 1, 1, 1, 0.9], size=8,
              colours=cl, row_h=0.2, bold_rows=today)
        cd = CategoryChartData()
        cd.categories = [show(x[1], "px") for x in lad]
        cd.add_series("Reward", [num(x[2]) for x in lad])
        cd.add_series("Risk", [-num(x[3]) if num(x[3]) is not None else None for x in lad])
        ch = slide.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, *fr14, cd).chart
        style_chart(ch)
        ch.value_axis.tick_labels.number_format = "0%"
        ch.value_axis.tick_labels.number_format_is_linked = False
        ch.category_axis.tick_labels.font.size = Pt(8)
        ch.category_axis.tick_label_position = XL_TICK_LABEL_POSITION.LOW
        for sr, colour in zip(ch.plots[0].series, ("good", "bad")):
            sr.format.fill.solid()
            sr.format.fill.fore_color.rgb = rgb(colour)
            sr.invert_if_negative = False
        ch.plots[0].gap_width = 60
    lines = []
    if s.get("lead"):
        lines.append((ctx.f(s["lead"]), 0))
    if s.get("irr"):
        lines.append((ctx.f(s["irr"]), 0, "3-year IRR at today's price: "))
    r3 = s.get("three_rs") or {}
    if r3:
        lines.append((f"roll-forward {ctx.f(r3.get('roll'))}, revisions {ctx.f(r3.get('revisions'))}, "
                      f"re-rating {ctx.f(r3.get('rerating'))}", 0, "The three R's: "))
    if lines:
        paras(ph[15], lines)
    else:
        drop(ph[15])
    sh = s.get("short")
    if isinstance(sh, dict) and any(sh.values()):
        names = (("type", "Short type: "), ("crowding", "Crowding: "), ("borrow", "Borrow: "),
                 ("var_size", "VaR size: "), ("takeout", "Takeout risk: "))
        paras(ph[16], [(ctx.f(sh[k]), 0, lab) for k, lab in names if sh.get(k)])
    else:
        drop(ph[16])


# ------------------------------------------------------------------ one slide
def bullets(ctx, items):
    return [(ctx.f(b), 0) for b in items or []]


def text_or_drop(ph, items):
    paras(ph, items) if items else drop(ph)


def plan_table(ctx, slide, ph, t, where, size=10):
    """A plan table ({header, rows}); columns whose header says delta / vs / variance get sign colours."""
    hd = [ctx.f(h) for h in t.get("header", [])]
    rows = [[ctx.f(c) for c in r] for r in t.get("rows", [])]
    if not hd:
        warn(f"{where}: the plan gives no table")
        note_box(slide, frame(ph), "No table in the plan")
        return drop(ph)
    signed = [j for j, h in enumerate(hd) if any(w in h.lower() for w in ("delta", " vs", "variance", "diff"))]
    colours = {(i, j): text_sign(r[j]) for i, r in enumerate(rows) for j in signed if j < len(r) and text_sign(r[j])}
    widths = [2.2] + [1] * (len(hd) - 1) if hd else None
    table(slide, frame(ph), hd, rows, widths, size=size, colours=colours, row_h=0.3)
    drop(ph)


def fill_slide(ctx, slide, s, i):
    t = s["type"]
    ph = {p.placeholder_format.idx: p for p in slide.placeholders}
    used = {0, 10, 11}
    if slide.shapes.title is not None:
        slide.shapes.title.text = ctx.f(s.get("title", ""))
    if 10 in ph:
        ph[10].text_frame.text = ctx.f(s.get("takeaway", ""))
    if 11 in ph:
        ph[11].text_frame.text = "Source: " + ctx.f(s.get("source", "")) if s.get("source") else ""
    body = {k: v for k, v in ph.items() if k >= 12}
    used |= set(body)
    where = f"slide {i} ({t})"
    if t == "title":
        put_picture(ctx, slide, body[12], s["image"], where) if s.get("image") else drop(body[12])
    elif t == "summary":
        cap = cap_table(ctx)
        if cap:
            table(slide, frame(body[12]), ["Cap table", ""], [[a, b] for a, b, _ in cap], [2.4, 1.6], size=10,
                  colours={(k, 1): c for k, (_, _, c) in enumerate(cap) if c}, row_h=0.26)
        else:
            warn("SUM cap table not found (no 'Cap table' block)")
            note_box(slide, frame(body[12]), "SUM cap table not found")
        grid = estimates_grid(ctx)
        if grid:
            hd, rows, cl = grid
            table(slide, frame(body[13]), hd, rows, [2.6] + [1] * (len(hd) - 1), size=9, colours=cl, row_h=0.26)
        else:
            warn("SUM internal-estimates grid not found (no 'Internal estimates' block)")
            note_box(slide, frame(body[13]), "SUM estimates grid not found")
        drop(body[12]), drop(body[13])
        text_or_drop(body[14], bullets(ctx, s.get("bullets")))
    elif t == "setup":
        paras(body[12], bullets(ctx, s.get("bullets")))
        setup_chart(ctx, slide, body[13], s)
    elif t == "thesis":
        for k, pt in zip((12, 13, 14), s.get("points", [])):
            paras(body[k], [(ctx.f(pt.get("head")), 0), (ctx.f(pt.get("body")), 1)])
    elif t == "risks":
        for k, rk in zip((12, 13), s.get("risks", [])):
            p = rk.get("prob")
            paras(body[k], [(ctx.f(rk.get("head")), 0)]
                  + ([(f"{p:.0%}", 1, "Our estimate: ")] if isinstance(p, (int, float)) else [])
                  + [(ctx.f(rk.get("if_hits")), 2, "If it hits: "), (ctx.f(rk.get("mitigant")), 2, "Mitigant: ")])
        text_or_drop(body[14], [(ctx.f(w), 0, "Tripwire: ") for w in s.get("tripwires") or []])
    elif t == "why_now":
        paras(body[12], bullets(ctx, s.get("bullets")))
        if s.get("bucket"):
            paras(body[13], [("Alpha bucket", 0), (ctx.f(s["bucket"]), 0)])
            runs_font(body[13].text_frame.paragraphs[0], bold=True, colour="navy")
        else:
            warn(f"{where}: no alpha bucket in the plan")
            drop(body[13])
    elif t == "valuation":
        paras(body[12], bullets(ctx, s.get("bullets")))
        valuation_chart(ctx, slide, body[13])
    elif t == "different":
        plan_table(ctx, slide, body[12], s.get("table") or {}, where)
        text_or_drop(body[13], bullets(ctx, s.get("bullets")))
    elif t == "risk_reward":
        risk_reward(ctx, slide, body, s)
    elif t == "catalysts":
        paras(body[12], bullets(ctx, s.get("bullets")))
        text_or_drop(body[13], [(ctx.f(w), 0, "Tripwire: ") for w in s.get("tripwires") or []])
    elif t == "text_chart":
        paras(body[12], bullets(ctx, s.get("bullets")))
        put_picture(ctx, slide, body[13], s.get("image"), where)
    elif t == "table":
        plan_table(ctx, slide, body[12], s.get("table") or {}, where)
    elif t == "quote":
        qs = {q["id"]: q for q in ctx.plan.get("quotes", [])}
        items = []
        for qid in s.get("quotes", []):
            q = qs.get(qid)
            if q:
                items.append(("“" + q["text"] + "”  (" + os.path.splitext(os.path.basename(q["file"]))[0]
                              + ")", 0))
        text_or_drop(body[12], items)
        text_or_drop(body[13], bullets(ctx, s.get("bullets")))
    elif t == "two_column":
        for k, side in ((12, "left"), (13, "right")):
            col = s.get(side) or {}
            paras(body[k], [(ctx.f(col.get("head", "")), 0)] + [(ctx.f(b), 1) for b in col.get("bullets", [])])
    elif t == "image":
        put_picture(ctx, slide, body[12], s.get("image"), where)
        text_or_drop(body[13], [(ctx.f(s["caption"]), 0)] if s.get("caption") else [])
    elif t == "checklist":
        rows = [[ctx.f(it.get("q")), ctx.f(it.get("a"))] for it in s.get("items", [])]
        fr = frame(body[12])
        table(slide, fr, ["Question", "Answer"], rows, [10.3, fr[2] / 914400 - 10.3], size=11, row_h=0.32)
        drop(body[12])
    for p in list(slide.placeholders):                    # anything still empty: leave no "Click to add" box
        if p.placeholder_format.idx not in used or (p.has_text_frame and not p.text_frame.text.strip()
                                                     and p.placeholder_format.idx >= 10):
            drop(p)
    slide.notes_slide.notes_text_frame.text = notes(ctx, s)


def notes(ctx, s):
    out = [ctx.f(s.get("notes", ""))]
    blob = json.dumps(s)
    for u in ctx.unverified:
        if (u.get("key") and "{" + u["key"] + "}" in blob) or (u.get("quote") and u["quote"] in s.get("quotes", [])):
            out.append(f"UNVERIFIED: {u.get('problem', '')}")
    return "\n".join(x for x in out if x)


# ------------------------------------------------------------------ the decks
def build(ctx, template, slides, out):
    prs = Presentation(template)
    layouts = {l.name: l for l in prs.slide_layouts}
    for i, s in enumerate(slides, 1):
        if s["type"] not in layouts:
            raise SystemExit(f"the template has no layout named {s['type']!r} (slide {i})")
        fill_slide(ctx, prs.slides.add_slide(layouts[s["type"]]), s, i)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    prs.save(out)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    for a in ("plan", "template", "values", "research", "tabs", "out-long", "out-core"):
        ap.add_argument(f"--{a}", required=True)
    ap.add_argument("--unverified")
    a = ap.parse_args(argv)
    if os.path.realpath(a.out_long) == os.path.realpath(a.out_core):
        raise SystemExit("--out-long and --out-core must be different files")
    plan = load(a.plan)
    unv = load(a.unverified) if a.unverified else []
    with tempfile.TemporaryDirectory() as tmp:
        ctx = Ctx(plan, Values(a.values), a.research, a.tabs, unv, tmp)
        print("wrote", build(ctx, a.template, plan["slides"], a.out_long))
        print("wrote", build(ctx, a.template, plan["slides"][:10], a.out_core))


if __name__ == "__main__":
    main()
