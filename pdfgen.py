"""The downloadable PDF of a trip plan.

Cover & overview · estimated budget (with the "not accurate" caption and sources) · must-visit · day-by-day itinerary with
photos and map links · food · shopping · tips · packing checklist · hotels · notes page.

`build_pdf()` is pure (no network): pass in the photos and hotels you want drawn. `make_pdf()` fetches them first.
"""
import io
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout, as_completed
from datetime import date
from pathlib import Path
from urllib.parse import quote, quote_plus, urlparse
from xml.sax.saxutils import escape

import requests
from PIL import Image
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import (BaseDocTemplate, CondPageBreak, Flowable, Frame, HRFlowable, KeepTogether, PageTemplate, Paragraph,
                                Spacer, Table, TableStyle)
from reportlab.lib.utils import ImageReader

import budget
import maps
import packing
from util import inr

FONT_DIR = Path(__file__).with_name("assets") / "fonts"
INK, TEXT, MUTED, DIM = "#0c2745", "#16324f", "#4f6b88", "#7a92ad"
BLUE, BLUE_D, SKY, LINE, SOFT = "#2f7fef", "#1f66d8", "#eaf4ff", "#d3e3f5", "#f6faff"
AMBER, AMBER_BG, AMBER_INK = "#ffb25b", "#fff3e4", "#6a3f00"
PART_COLORS = {"stay": "#2f7fef", "food": "#19b6a6", "local": "#ffb25b", "entry": "#7fb0ee", "buffer": "#aebdd1"}
PART_LABELS = (("stay", "Stay"), ("food", "Food"), ("local", "Local transport"), ("entry", "Entry & activities"), ("buffer", "Buffer (10%)"))
ALLOWED_IMAGE_HOSTS = ("googleusercontent.com", "ggpht.com", "wikimedia.org", "wikipedia.org")
IMAGE_BUDGET_SECONDS = 18

_ready = False
_covered = set()
_symbols = set()


def _fonts():
    """Register the bundled fonts once (Poppins for text, a few DejaVu symbols)."""
    global _ready, _covered, _symbols
    if _ready:
        return
    for name, file in (("Poppins", "Poppins-Regular.ttf"), ("Poppins-Medium", "Poppins-Medium.ttf"), ("Poppins-Bold", "Poppins-Bold.ttf"),
                       ("Poppins-Italic", "Poppins-Italic.ttf"), ("Symbols", "DejaVuSans-symbols.ttf")):
        pdfmetrics.registerFont(TTFont(name, str(FONT_DIR / file)))
    pdfmetrics.registerFontFamily("Poppins", normal="Poppins", bold="Poppins-Bold", italic="Poppins-Italic", boldItalic="Poppins-Bold")
    _covered = set(pdfmetrics.getFont("Poppins").face.charToGlyph)
    _symbols = set(pdfmetrics.getFont("Symbols").face.charToGlyph)
    _ready = True


# ---------------------------------------------------------------- text
def _clean(s):
    """Plain text the fonts can draw: unsupported characters are dropped (or reduced to a base letter)."""
    _fonts()
    out = []
    for ch in unicodedata.normalize("NFC", str(s if s is not None else "")):
        cp = ord(ch)
        if ch in "\r\n\t":
            out.append(" ")
        elif cp in _covered or cp in _symbols:
            out.append(ch)
        else:
            base = unicodedata.normalize("NFKD", ch)[:1]
            if base and ord(base) in _covered and base.isprintable():
                out.append(base)
    return " ".join("".join(out).split())


def _x(s):
    """Paragraph-safe markup: escaped, with symbols switched to the symbol font."""
    out = []
    for ch in _clean(s):
        e = escape(ch)
        out.append(f'<font name="Symbols">{e}</font>' if ord(ch) not in _covered and ord(ch) in _symbols else e)
    return "".join(out)


def _width(text, font, size):
    return stringWidth(_clean(text), font, size)


def _style(name, **kw):
    base = dict(fontName="Poppins", fontSize=9.2, leading=13.6, textColor=colors.HexColor(TEXT))
    base.update(kw)
    return ParagraphStyle(name, **base)


def _styles():
    return {
        "body": _style("body"),
        "small": _style("small", fontSize=8.2, leading=11.6, textColor=colors.HexColor(MUTED)),
        "tiny": _style("tiny", fontSize=7.2, leading=10, textColor=colors.HexColor(DIM)),
        "title": _style("title", fontName="Poppins-Bold", fontSize=31, leading=34, textColor=colors.HexColor(INK)),
        "sub": _style("sub", fontSize=11, leading=15.5, textColor=colors.HexColor(MUTED)),
        "eyebrow": _style("eyebrow", fontName="Poppins-Bold", fontSize=7.6, leading=10, textColor=colors.HexColor(BLUE_D)),
        "h1": _style("h1", fontName="Poppins-Bold", fontSize=16, leading=20, textColor=colors.HexColor(INK)),
        "h3": _style("h3", fontName="Poppins-Bold", fontSize=11.4, leading=14.6, textColor=colors.HexColor(INK)),
        "meta": _style("meta", fontName="Poppins-Medium", fontSize=8.2, leading=11.4, textColor=colors.HexColor(MUTED)),
        "link": _style("link", fontName="Poppins-Medium", fontSize=8, leading=11),
        "caption": _style("caption", fontSize=8.6, leading=12.6, textColor=colors.HexColor(AMBER_INK)),
        "item": _style("item", fontSize=8.8, leading=12.4, leftIndent=13, firstLineIndent=-13),
    }


def _link(url, text, color=BLUE_D):
    return f'<a href="{escape(url, {chr(34): "&quot;"})}" color="{color}">{_x(text)}</a>'


def maps_url(*parts):
    return "https://www.google.com/maps/search/?api=1&query=" + quote_plus(", ".join(p for p in parts if p))


# ---------------------------------------------------------------- drawn building blocks
class Chips(Flowable):
    """Rounded pills that wrap onto several lines."""

    def __init__(self, items, size=7.8, pad=6.5, gap=4.5, height=15.5, bg=SKY, fg=BLUE_D, accent=None):
        super().__init__()
        self.items, self.size, self.pad, self.gap, self.h, self.bg, self.fg, self.accent = [_clean(i) for i in items if _clean(i)], size, pad, gap, height, bg, fg, accent

    def wrap(self, aw, ah):
        self.lines, row, used = [], [], 0
        for t in self.items:
            w = _width(t, "Poppins-Medium", self.size) + 2 * self.pad
            if row and used + self.gap + w > aw:
                self.lines.append(row); row, used = [], 0
            row.append((t, w)); used += w + (self.gap if len(row) > 1 else 0)
        if row:
            self.lines.append(row)
        self.width = aw
        self.height = max(len(self.lines), 1) * self.h + max(len(self.lines) - 1, 0) * self.gap
        return aw, self.height

    def draw(self):
        c, y = self.canv, self.height - self.h
        for row in self.lines:
            x = 0
            for i, (t, w) in enumerate(row):
                hot = self.accent is not None and t == self.accent
                c.setFillColor(colors.HexColor(BLUE_D if hot else self.bg)); c.roundRect(x, y, w, self.h, self.h / 2, stroke=0, fill=1)
                c.setFillColor(colors.white if hot else colors.HexColor(self.fg)); c.setFont("Poppins-Medium", self.size)
                c.drawString(x + self.pad, y + (self.h - self.size) / 2 + 1.6, t)
                x += w + self.gap
            y -= self.h + self.gap


class Stats(Flowable):
    """A row of big-number boxes (label on top, value underneath)."""

    def __init__(self, items, accent_first=True, gap=6, height=44):
        super().__init__()
        self.items, self.accent_first, self.gap, self.h = [(_clean(a), _clean(b)) for a, b in items], accent_first, gap, height

    def wrap(self, aw, ah):
        self.width = aw
        return aw, self.h

    def draw(self):
        c, n = self.canv, len(self.items)
        w = (self.width - self.gap * (n - 1)) / n
        for i, (label, value) in enumerate(self.items):
            x, hot = i * (w + self.gap), (self.accent_first and i == 0)
            c.setFillColor(colors.HexColor(BLUE_D if hot else SKY)); c.roundRect(x, 0, w, self.h, 9, stroke=0, fill=1)
            c.setFillColor(colors.HexColor("#cfe3ff" if hot else MUTED)); c.setFont("Poppins-Medium", 6.8)
            c.drawString(x + 9, self.h - 14, label.upper())
            size = 15.5
            while _width(value, "Poppins-Bold", size) > w - 18 and size > 8:
                size -= 0.5
            c.setFillColor(colors.white if hot else colors.HexColor(INK)); c.setFont("Poppins-Bold", size)
            c.drawString(x + 9, 10, value)


class StackedBar(Flowable):
    """The budget split as one coloured bar."""

    def __init__(self, parts, height=9):
        super().__init__()
        self.parts, self.h = [(k, v) for k, v in parts if v > 0], height

    def wrap(self, aw, ah):
        self.width = aw
        return aw, self.h

    def draw(self):
        c, total = self.canv, sum(v for _, v in self.parts) or 1
        usable, x = self.width - 1.5 * (len(self.parts) - 1), 0
        for k, v in self.parts:
            w = max(usable * v / total, 3)
            c.setFillColor(colors.HexColor(PART_COLORS[k])); c.roundRect(x, 0, w, self.h, self.h / 2, stroke=0, fill=1)
            x += w + 1.5


class Photo(Flowable):
    """A JPEG with rounded corners."""

    def __init__(self, data, width, height, radius=7):
        super().__init__()
        self.data, self.width, self.height, self.r = data, width, height, radius

    def wrap(self, aw, ah):
        return self.width, self.height

    def draw(self):
        c = self.canv
        c.saveState()
        p = c.beginPath(); p.roundRect(0, 0, self.width, self.height, self.r); c.clipPath(p, stroke=0)
        c.drawImage(ImageReader(io.BytesIO(self.data)), 0, 0, self.width, self.height)
        c.restoreState()


class DayBanner(Flowable):
    def __init__(self, day, title, count, total):
        super().__init__()
        self.day, self.title, self.count, self.total = f"DAY {int(day):02d}", _clean(title), f"{count} stop{'s' if count != 1 else ''} · {inr(total)}", total

    def wrap(self, aw, ah):
        self.width = aw
        return aw, 30

    def draw(self):
        c = self.canv
        c.setFillColor(colors.HexColor(SKY)); c.roundRect(0, 0, self.width, 30, 10, stroke=0, fill=1)
        pw = _width(self.day, "Poppins-Bold", 8.4) + 18
        c.setFillColor(colors.HexColor(BLUE_D)); c.roundRect(5, 5, pw, 20, 10, stroke=0, fill=1)
        c.setFillColor(colors.white); c.setFont("Poppins-Bold", 8.4); c.drawString(14, 11.2, self.day)
        right = _width(self.count, "Poppins-Medium", 8.2)
        room = self.width - pw - right - 40
        size, t = 12, self.title
        while _width(t, "Poppins-Bold", size) > room and len(t) > 4:
            t = t[:-2].rstrip() + "…"
        c.setFillColor(colors.HexColor(INK)); c.setFont("Poppins-Bold", size); c.drawString(pw + 16, 10.6, t)
        c.setFillColor(colors.HexColor(MUTED)); c.setFont("Poppins-Medium", 8.2); c.drawRightString(self.width - 12, 11, self.count)


class NoteLines(Flowable):
    def __init__(self, n=14, gap=21):
        super().__init__()
        self.n, self.gap = n, gap

    def wrap(self, aw, ah):
        self.width = aw
        return aw, self.n * self.gap

    def draw(self):
        c = self.canv
        c.setStrokeColor(colors.HexColor(LINE)); c.setLineWidth(0.7)
        for i in range(self.n):
            c.line(0, i * self.gap + 2, self.width, i * self.gap + 2)


class _NumberedCanvas(rl_canvas.Canvas):
    """Draws the footer once the total page count is known (“Page 2 of 6”)."""

    meta = {}

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self._pages = []

    def showPage(self):
        self._pages.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._pages)
        for state in self._pages:
            self.__dict__.update(state)
            self._footer(total)
            super().showPage()
        super().save()

    def _footer(self, total):
        w, m = A4[0], 16 * mm
        self.setStrokeColor(colors.HexColor(LINE)); self.setLineWidth(0.6); self.line(m, 15 * mm, w - m, 15 * mm)
        self.setFillColor(colors.HexColor(BLUE_D)); self.setFont("Poppins-Bold", 7.2); self.drawString(m, 10.6 * mm, "NARADA YATRA")
        self.setFillColor(colors.HexColor(MUTED)); self.setFont("Poppins", 7.2)
        self.drawString(m + _width("NARADA YATRA", "Poppins-Bold", 7.2) + 6, 10.6 * mm, self.meta.get("line", ""))
        self.drawRightString(w - m, 10.6 * mm, f"Page {self._pageNumber} of {total}")
        self.setFillColor(colors.HexColor(DIM)); self.setFont("Poppins-Italic", 6.6)
        self.drawString(m, 6.6 * mm, "Budget figures are estimates, not exact — they can change according to the traveler.")


# ---------------------------------------------------------------- images
def _host_ok(url):
    p = urlparse(url or "")
    return p.scheme == "https" and bool(p.hostname) and any(p.hostname == h or p.hostname.endswith("." + h) for h in ALLOWED_IMAGE_HOSTS)


def _download(url, limit=4_000_000):
    if not _host_ok(url):
        return None
    try:
        r = requests.get(url, timeout=(3, 7), stream=True, headers={"User-Agent": "narada-yatra/1.0"})
        if not r.ok or not str(r.headers.get("Content-Type", "")).startswith("image/"):
            return None
        data = b""
        for chunk in r.iter_content(65536):
            data += chunk
            if len(data) > limit:
                return None
        return data
    except requests.RequestException:
        return None


def prepare_image(data, ratio, width_px, quality=72):
    """Crop to `ratio` (width/height), shrink and re-compress so the PDF stays small. None if unreadable."""
    try:
        im = Image.open(io.BytesIO(data)).convert("RGB")
        w, h = im.size
        if w < 20 or h < 20:
            return None
        th = int(w / ratio)
        if th <= h:
            top = (h - th) // 2
            im = im.crop((0, top, w, top + th))
        else:
            tw = int(h * ratio)
            left = (w - tw) // 2
            im = im.crop((left, 0, left + tw, h))
        if im.width > width_px:
            im = im.resize((width_px, max(int(im.height * width_px / im.width), 1)), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=quality, optimize=True)
        return buf.getvalue()
    except Exception:
        return None


def _photo_url(query, name):
    cached = maps.cached_photos(query, name, 5)            # the galleries may already have fetched it
    if cached:
        return cached[0]["url"]
    try:
        url = maps.find_photo(query)
    except maps.MapsError:
        url = None
    return url or maps.wiki_photo(name)


def _fetch_one(query, name, ratio, width_px):
    data = _download(_photo_url(query, name))
    return prepare_image(data, ratio, width_px) if data else None


def gather_images(plan, deadline=IMAGE_BUDGET_SECONDS):
    """One cover photo and one photo per stop. Anything slow or missing is simply left out."""
    place = plan["place"]
    jobs = {"hero": (f"{place}, India", place, 3.4, 1300)}
    for di, d in enumerate(plan["days"]):
        for si, s in enumerate(d["stops"]):
            jobs[(di, si)] = (f"{s['name']}, {place}, India", s["name"], 4 / 3, 380)
    out, ex = {}, ThreadPoolExecutor(max_workers=6)
    futs = {ex.submit(_fetch_one, *args): key for key, args in jobs.items()}
    try:
        for f in as_completed(futs, timeout=deadline):
            try:
                out[futs[f]] = f.result()
            except Exception:
                out[futs[f]] = None
    except FuturesTimeout:
        pass
    finally:
        ex.shutdown(wait=False, cancel_futures=True)
    return out


# ---------------------------------------------------------------- the document
def _section(S, eyebrow, title, W):
    return [CondPageBreak(60 * mm), Spacer(1, 13), Paragraph(_x(eyebrow.upper()), S["eyebrow"]), Spacer(1, 1.5), Paragraph(_x(title), S["h1"]),
            HRFlowable(width="100%", thickness=0.7, color=colors.HexColor(LINE), spaceBefore=4, spaceAfter=7)]


def _box(flowables, W, bg=SOFT, border=LINE, pad=9, radius=9):
    t = Table([[flowables]], colWidths=[W])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.toColor(bg)), ("BOX", (0, 0), (-1, -1), 0.7, colors.toColor(border)),
                           ("ROUNDEDCORNERS", [radius] * 4), ("LEFTPADDING", (0, 0), (-1, -1), pad), ("RIGHTPADDING", (0, 0), (-1, -1), pad),
                           ("TOPPADDING", (0, 0), (-1, -1), pad - 1), ("BOTTOMPADDING", (0, 0), (-1, -1), pad - 1)]))
    return t


def _stop_card(S, stop, place, photo, W):
    meta = f'<font color="{BLUE_D}"><b>{_x(stop["time"] or "Any time")}</b></font>'
    if stop["durationHrs"]:
        meta += f" · about {_x(stop['durationHrs'])} h"
    info = [Paragraph(meta, S["meta"]), Spacer(1, 1.5), Paragraph(_x(stop["name"]), S["h3"])]
    if stop["note"]:
        info += [Spacer(1, 2), Paragraph(_x(stop["note"]), S["small"])]
    chips = []
    if stop["travel"] and stop["travel"] != "-":
        chips.append(f"{stop['travel']} · {stop['distanceKm']} km" if stop["distanceKm"] else stop["travel"])
    chips += ["Entry " + (inr(stop["entryFee"]) if stop["entryFee"] else "free"), "Transport " + inr(stop["transportCost"]), "Meals " + inr(stop["mealCost"])]
    info += [Spacer(1, 4), Chips(chips, bg="#e3eefb", fg=TEXT), Spacer(1, 4),
             Paragraph(_link(maps_url(stop["name"], place, "India"), "Open in Google Maps ↗"), S["link"])]
    if photo:
        pw = 33 * mm
        cell = Table([[Photo(photo, pw, pw * 3 / 4), info]], colWidths=[pw + 8, W - pw - 8 - 18])
        cell.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                                  ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
        return KeepTogether([_box([cell], W, bg="white", pad=9), Spacer(1, 6)])
    return KeepTogether([_box(info, W, bg="white", pad=9), Spacer(1, 6)])


def _two_col(cards, W, gap=8):
    cw = (W - gap) / 2                                           # width of one card
    rows = [[cards[i], cards[i + 1] if i + 1 < len(cards) else ""] for i in range(0, len(cards), 2)]
    t = Table(rows, colWidths=[cw + gap, cw], hAlign="LEFT")
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (0, -1), gap),
                           ("RIGHTPADDING", (1, 0), (1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 7)]))
    return t


def build_pdf(plan, *, days, travelers=2, style="comfort", packed=(), images=None, hotels=None, today=None):
    """Return the PDF as bytes. `images` = {"hero": jpeg, (day_idx, stop_idx): jpeg}; `hotels` = maps.find_hotels() result."""
    _fonts()
    images, hotels, packed = images or {}, hotels or [], set(packed or ())
    S, today = _styles(), today or date.today()
    place, state = _clean(plan["place"]), _clean(plan["state"])
    n = max(1, min(int(travelers), 10))
    style = style if style in budget.TIERS else "comfort"
    model = budget.client_model(plan, days, plan["place"], plan["state"])
    est = budget.compute(model, n, style)
    stops_total = sum(len(d["stops"]) for d in plan["days"])
    buf = io.BytesIO()
    margin = 16 * mm
    doc = BaseDocTemplate(buf, pagesize=A4, leftMargin=margin, rightMargin=margin, topMargin=14 * mm, bottomMargin=21 * mm,
                          title=f"{place} — {days}-day trip plan", author="NARADA YATRA", subject="Trip plan", creator="NARADA YATRA")
    W = doc.width
    doc.addPageTemplates([PageTemplate(id="p", frames=[Frame(doc.leftMargin, doc.bottomMargin, W, doc.height, id="f", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)])])
    story = []

    # ---- cover
    story += [Paragraph('<font name="Poppins-Bold" color="%s">NARADA YATRA</font> <font color="%s">· Travel planner for India</font>' % (BLUE_D, MUTED), S["meta"]), Spacer(1, 7)]
    if images.get("hero"):
        story += [Photo(images["hero"], W, W / 3.4, radius=12), Spacer(1, 11)]
    story += [Paragraph(f'<font color="{BLUE_D}"><b>{_x(state.upper())}</b></font>', S["eyebrow"]), Spacer(1, 2), Paragraph(_x(place), S["title"]), Spacer(1, 5)]
    story += [Chips([f"{days} day{'s' if days != 1 else ''}", f"{n} traveler{'s' if n != 1 else ''}", f"{budget.TIER_LABELS[style]} style"]
                    + ([f"Best time: {plan['bestSeason']}"] if plan["bestSeason"] else []), height=17, size=8.2), Spacer(1, 9)]
    story += [Stats([("Estimated per person", inr(est["per_person"])), (f"For {n} traveler{'s' if n != 1 else ''}", inr(est["group"])),
                     ("Per person per day", inr(est["per_day"])), ("Stops planned", str(stops_total))]), Spacer(1, 10)]
    if plan["overview"]:
        story += [Paragraph(_x(plan["overview"]), _style("lead", fontSize=10, leading=15.2)), Spacer(1, 4)]
    story += [Paragraph(f'Created {today:%d %B %Y}. Everything below works offline — tap the blue links for maps and sources when you have a connection.', S["tiny"])]

    # ---- budget
    story += _section(S, "Estimated budget", f"What {place} may cost per person", W)
    story += [StackedBar([(k, est["parts"][k]) for k, _ in PART_LABELS]), Spacer(1, 8)]
    rows = [[Paragraph(f'<font name="Symbols" color="{PART_COLORS[k]}">●</font>&nbsp; {_x(label)}', S["body"]), Paragraph(f"<b>{_x(inr(est['parts'][k]))}</b>", S["body"]),
             Paragraph(f'{round(est["parts"][k] * 100 / est["total"]) if est["total"] else 0}%', S["small"])] for k, label in PART_LABELS]
    rows.append([Paragraph("<b>Estimated per person</b>", S["body"]), Paragraph(f'<font color="{BLUE_D}"><b>{_x(inr(est["per_person"]))}</b></font>', S["body"]),
                 Paragraph(f'range {_x(inr(est["low"]))} – {_x(inr(est["high"]))}', S["tiny"])])
    bt = Table(rows, colWidths=[W * 0.52, W * 0.2, W * 0.28])
    bt.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -2), 0.5, colors.HexColor(LINE)), ("LINEABOVE", (0, -1), (-1, -1), 0.9, colors.HexColor(BLUE)),
                            ("TOPPADDING", (0, 0), (-1, -1), 3.2), ("BOTTOMPADDING", (0, 0), (-1, -1), 3.2), ("LEFTPADDING", (0, 0), (-1, -1), 2), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    story += [bt, Spacer(1, 8)]
    story += [_box([Paragraph(f"<b>The budget per person is not accurate.</b> It is only an estimate and can change according to the traveler — the season, "
                              f"how you travel, where you stay and what you buy. Getting to and from {_x(place)} is not included.", S["caption"])], W, bg=AMBER_BG, border=AMBER), Spacer(1, 8)]
    r = model["rates"][style]
    story += [Paragraph(f"<b>How it was worked out.</b> {model['nights']} night{'s' if model['nights'] != 1 else ''} in a room of about {_x(inr(r['stay']))} a night, shared by 2 travelers "
                        f"(a solo traveler pays for a whole room); food of about {_x(inr(r['food']))} per person per day; cabs and autos split between up to 4 travelers; "
                        f"ticket prices at Indian-citizen rates; and a 10% buffer. Rates for {_x(model['label'])} at the {budget.TIER_LABELS[style].lower()} level.", S["small"]), Spacer(1, 5)]
    src = "; ".join(_link(s["url"], f"{s['title']} ({s['site']})") for s in budget.sources_for(model["profile"]))
    story += [Paragraph(f"<b>Checked against:</b> {src}", S["tiny"]), Spacer(1, 2),
              Paragraph("<b>Compare:</b> " + _link("https://www.google.com/search?q=" + quote_plus(f"{plan['place']} trip budget per person travel blog"), f"search Google for {plan['place']} budgets"), S["tiny"])]

    # ---- must visit
    if plan["mustVisit"]:
        story += _section(S, "Don't miss", "Must-visit highlights", W)
        story += [_two_col([Paragraph(f'<font name="Symbols" color="{BLUE_D}">★</font>&nbsp; {_x(m)}', S["item"]) for m in plan["mustVisit"]], W)]

    # ---- itinerary
    story += _section(S, "Itinerary", "Day by day, stop by stop", W)
    story += [Paragraph("Stops are ordered by distance to save travel time. Costs are per person; transport is for one traveler on a typical cab, auto or bus.", S["small"]), Spacer(1, 7)]
    for di, d in enumerate(plan["days"]):
        story += [CondPageBreak(55 * mm), DayBanner(d["day"], d["title"], len(d["stops"]), d["total"]), Spacer(1, 7)]
        for si, s in enumerate(d["stops"]):
            story.append(_stop_card(S, s, plan["place"], images.get((di, si)), W))
        story.append(Spacer(1, 4))

    # ---- food & shopping
    if plan["foods"]:
        story += _section(S, f"Taste of {place}", "Famous local food", W)
        cards = []
        for i, f in enumerate(plan["foods"], 1):
            body = [Paragraph(f'<font color="{BLUE_D}"><b>{i:02d}</b></font> &nbsp;<b>{_x(f["name"])}</b>', S["h3"])]
            if f["where"]:
                body += [Spacer(1, 1), Paragraph(_link(maps_url(f["where"], plan["place"], "India"), f"Try at: {f['where']} ↗"), S["link"])]
            if f["description"]:
                body += [Spacer(1, 2), Paragraph(_x(f["description"]), S["small"])]
            cards.append(_box(body, (W - 8) / 2, bg="white", pad=8))
        story.append(_two_col(cards, W))
    if plan["shopping"]:
        story += _section(S, "Bring something home", "Where to shop", W)
        cards = []
        for i, sh in enumerate(plan["shopping"], 1):
            body = [Paragraph(f'<font color="{BLUE_D}"><b>{i:02d}</b></font> &nbsp;<b>{_x(sh["area"])}</b>', S["h3"])]
            if sh["buy"]:
                body += [Spacer(1, 2), Paragraph(f"<b>Buy:</b> {_x(sh['buy'])}", S["small"])]
            if sh["tip"]:
                body += [Spacer(1, 1), Paragraph(_x(sh["tip"]), S["small"])]
            body += [Spacer(1, 3), Paragraph(_link(maps_url(sh["area"], plan["place"], "India"), "Open in Google Maps ↗"), S["link"])]
            cards.append(_box(body, (W - 8) / 2, bg="white", pad=8))
        story.append(_two_col(cards, W))

    # ---- tips
    if plan["tips"]:
        story += _section(S, "Good to know", "Travel tips", W)
        story += [Paragraph(f'<font name="Symbols" color="{BLUE_D}">●</font>&nbsp; {_x(t)}', S["item"]) for t in plan["tips"]]

    # ---- packing
    groups = packing.build(plan["place"], days, plan["bestSeason"])
    story += _section(S, "Be ready", "Packing checklist", W)
    done = sum(1 for g in groups for it in g["items"] if it["id"] in packed)
    total = sum(len(g["items"]) for g in groups)
    story += [Paragraph(f"Tailored to {_x(place)}" + (f" and its best season ({_x(plan['bestSeason'])})" if plan["bestSeason"] else "") + f". {done} of {total} items packed when this PDF was made.", S["small"]), Spacer(1, 6)]
    cells = []
    for g in groups:
        col = [Paragraph(f'<font color="{BLUE_D}"><b>{_x(g["title"].upper())}</b></font>', S["eyebrow"]), Spacer(1, 3)]
        for it in g["items"]:
            ok = it["id"] in packed
            glyph = f'<font name="Symbols" color="{BLUE_D if ok else DIM}">{"☑" if ok else "☐"}</font>'
            note = f' <font color="{DIM}" size="7">— {_x(it["note"])}</font>' if it["note"] else ""
            col.append(Paragraph(f'{glyph}&nbsp; {_x(it["label"])}{note}', S["item"]))
        cells.append(col)
    pw = (W - 12) / 2
    grid = Table([[cells[i], cells[i + 1] if i + 1 < len(cells) else ""] for i in range(0, len(cells), 2)], colWidths=[pw + 12, pw])
    grid.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (0, -1), 12),
                              ("RIGHTPADDING", (1, 0), (1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 8), ("TOPPADDING", (0, 0), (-1, -1), 0)]))
    story.append(grid)

    # ---- hotels
    if hotels:
        story += _section(S, "Where to stay", "Nearby hotels", W)
        head = [Paragraph(f"<b>{h}</b>", S["tiny"]) for h in ("Hotel", "Rating", "Price per night", "Map")]
        rows = [head]
        for h in hotels[:6]:
            price = (f"{inr(h['priceFrom'])}" + (f" – {inr(h['priceTo'])}" if h.get("priceTo") else "+")) if h.get("priceFrom") else (budget_label(h.get("priceLevel")) or "See Google Maps")
            rate = f"{h['rating']} ({h['reviews']:,})" if h.get("rating") else "—"
            link = _link(h["mapsUrl"], "Open ↗") if str(h.get("mapsUrl", "")).startswith("https://") else ""
            rows.append([Paragraph(f"<b>{_x(h['name'])}</b><br/><font color='{DIM}' size='7'>{_x(h.get('address', ''))}</font>", S["small"]),
                         Paragraph(f'<font name="Symbols" color="{AMBER}">★</font> {_x(rate)}', S["small"]), Paragraph(_x(price), S["small"]), Paragraph(link, S["link"])])
        ht = Table(rows, colWidths=[W * 0.46, W * 0.17, W * 0.24, W * 0.13], repeatRows=1)
        ht.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.5, colors.HexColor(LINE)), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 4),
                                ("BOTTOMPADDING", (0, 0), (-1, -1), 4), ("LEFTPADDING", (0, 0), (-1, -1), 2), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(SKY))]))
        story += [ht, Spacer(1, 3), Paragraph("Ratings and prices come from Google Maps when this PDF was made and may have changed.", S["tiny"])]

    # ---- notes
    story += _section(S, "Your notes", "Trip notes", W) + [NoteLines(22, 22), Spacer(1, 10),
                       Paragraph("Have a wonderful trip! Plan another journey any time at NARADA YATRA.", S["small"])]

    line = f"{place} · {days}-day plan · {n} traveler{'s' if n != 1 else ''}"

    class Canvas(_NumberedCanvas):
        meta = {"line": line}

    doc.build(story, canvasmaker=Canvas)
    return buf.getvalue()


def budget_label(level):
    return maps.PRICE_LABELS.get(level or "", "") if level else ""


def make_pdf(plan, *, days, travelers=2, style="comfort", packed=(), photos=True):
    """Fetch the photos and hotels (best effort), then build the PDF."""
    images = gather_images(plan) if photos else {}
    try:
        hotels = maps.find_hotels(plan["place"])
    except Exception:
        hotels = []
    return build_pdf(plan, days=days, travelers=travelers, style=style, packed=packed, images=images, hotels=hotels)
