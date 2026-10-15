"""Рисует пиксельную карточку из Chart. Pillow, без нейросетей.

Базовый холст 240×300 «пикселей», потом увеличивается в SCALE раз без сглаживания,
поэтому всё получается честно-пиксельным. Шрифт Press Start 2P (OFL), размер 8 —
это ровно 8×8 на символ, сетка не ломается.
"""
from __future__ import annotations

import io
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .insights import LETTERS, equivalents, insight, unit_label
from .numbers import fmt, fmt_short
from .parser import Chart

ROOT = Path(__file__).resolve().parent.parent
FONT_PATH = ROOT / "assets" / "fonts" / "PressStart2P-Regular.ttf"

W, H, SCALE = 240, 300, 4
M = 12  # поля

# ─── Палитра: меняй под канал ───────────────────────────────────────────────
PALETTE = {
    "text": "#ffffff",
    "muted": "#9aa0cf",
    "grid": "#3a3f6a",
    "axis": "#5a5f8a",
    "footer": "#11142e",
    "accent": "#ffd166",   # основной цвет столбиков
    "accent2": "#4ad6ff",  # выделенный столбик / «стало»
    "up": "#7ee787",
    "down": "#ff5c8a",
    "cell_off": "#2a2f5a",
}
THEMES = {  # фон по типу карточки
    "bars": "#1b1f4a",
    "delta": "#2d1b4e",
    "share": "#0f2a2e",
    "equiv": "#3a1f2e",
    "number": "#1b1f4a",
}
STARS = [(14, 6), (62, 3), (121, 9), (190, 5), (226, 22), (6, 48), (232, 70), (4, 110), (234, 150)]

_fonts: dict[int, ImageFont.FreeTypeFont] = {}


def font(size: int = 8) -> ImageFont.FreeTypeFont:
    if size not in _fonts:
        _fonts[size] = ImageFont.truetype(str(FONT_PATH), size)
    return _fonts[size]


def _wrap(text: str, max_chars: int, max_lines: int = 2) -> list[str]:
    words = text.split()
    lines: list[str] = []
    cur = ""
    for w in words:
        cand = (cur + " " + w).strip()
        if len(cand) <= max_chars:
            cur = cand
        else:
            if cur:
                lines.append(cur)
            cur = w[:max_chars]
        if len(lines) == max_lines:
            break
    if cur and len(lines) < max_lines:
        lines.append(cur)
    return lines or [""]


def _text(d: ImageDraw.ImageDraw, xy, s: str, size: int = 8, fill: str = "text", anchor: str = "la"):
    d.text(xy, s, font=font(size), fill=PALETTE.get(fill, fill), anchor=anchor)


def _dotted(d: ImageDraw.ImageDraw, x0: int, x1: int, y: int, color: str):
    for x in range(x0, x1, 4):
        d.point((x, y), PALETTE[color])


def _frame(c: Chart, handle: str):
    im = Image.new("RGB", (W, H), THEMES.get(c.kind, THEMES["bars"]))
    d = ImageDraw.Draw(im)
    for x, y in STARS:
        d.point((x, y), "#fff3a8")
    # заголовок
    y = M
    title = c.title.strip()
    if title:
        for line in _wrap(title, (W - 2 * M) // 8, 2):
            _text(d, (M, y), line, 8, "text")
            y += 12
    else:
        y += 4
    # подвал
    d.rectangle((0, H - 16, W, H), fill=PALETTE["footer"])
    _text(d, (M, H - 12), handle, 8, "muted")
    return im, d, y


def _insight(d: ImageDraw.ImageDraw, c: Chart):
    line = insight(c)
    if not line:
        return
    lines = _wrap(line, (W - 2 * M) // 8, 2)
    y = H - 16 - 12 - 12 * len(lines)
    for ln in lines:
        _text(d, (M, y), ln, 8, "accent")
        y += 12


# ─── bars ────────────────────────────────────────────────────────────────────
def _bars(c: Chart, d: ImageDraw.ImageDraw, top: int):
    n = len(c.values)
    labels = [l or LETTERS[i] for i, l in enumerate(c.labels)]
    x0, x1 = M, W - M
    label_lines = 2 if any(len(l) > 0 for l in labels) else 1
    y_axis = H - 16 - 12 - 24 - 8 - 12 * label_lines   # над строкой вывода
    y_top = top + 14
    gap = 6 if n <= 6 else 3
    bw = (x1 - x0 - gap * (n - 1)) // n
    mx = max(max(c.values), 1e-9)
    mn = min(c.values)
    base = 0 if mn >= 0 else mn
    span = mx - base if mx > base else 1
    # сетка
    for i in range(1, 4):
        _dotted(d, x0, x1, y_axis - i * (y_axis - y_top) // 4, "grid")
    d.line((x0, y_axis, x1, y_axis), fill=PALETTE["axis"])
    imax = max(range(n), key=lambda i: c.values[i])
    for i, v in enumerate(c.values):
        x = x0 + i * (bw + gap)
        h = int((y_axis - y_top - 10) * (v - base) / span)
        color = "accent2" if i == imax and n > 1 else "accent"
        if v < 0:
            color = "down"
        if h > 0:
            d.rectangle((x, y_axis - h, x + bw - 1, y_axis - 1), fill=PALETTE[color])
            d.rectangle((x, y_axis - h, x + bw - 1, y_axis - h + 1), fill=PALETTE["text"])
        # значение над столбиком
        s = fmt_short(v)
        maxc = max(1, bw // 8)
        if len(s) > maxc and n > 4:
            s = s[:maxc]
        _text(d, (x + bw // 2, y_axis - h - 10), s, 8, "text", anchor="ma")
        # подпись под осью
        lab = labels[i]
        for j, ln in enumerate(_wrap(lab, maxc, label_lines)):
            _text(d, (x + bw // 2, y_axis + 4 + j * 12), ln, 8, "muted", anchor="ma")


# ─── delta ───────────────────────────────────────────────────────────────────
def _delta(c: Chart, d: ImageDraw.ImageDraw, top: int):
    a, b = c.values
    pct = c.pct or 0
    up = b >= a
    col = "up" if up else "down"
    sign = "+" if up else "-"
    ul = unit_label(c.unit)
    _text(d, (W - M, top + 2), f"{sign}{fmt(abs(pct))}%", 16, col, anchor="ra")
    if ul:
        _text(d, (W - M, top + 22), ul, 8, "muted", anchor="ra")
    y_axis = H - 16 - 12 - 24 - 8 - 12
    y_top = top + 34
    x0, x1 = M, W - M
    bw = 72
    xs = [x0 + 12, x1 - 12 - bw]
    mx = max(a, b, 1e-9)
    for i in range(1, 4):
        _dotted(d, x0, x1, y_axis - i * (y_axis - y_top) // 4, "grid")
    d.line((x0, y_axis, x1, y_axis), fill=PALETTE["axis"])
    for i, (v, lab) in enumerate(((a, "было"), (b, "стало"))):
        x = xs[i]
        h = int((y_axis - y_top - 10) * max(v, 0) / mx)
        color = "accent" if i == 0 else col
        if h > 0:
            d.rectangle((x, y_axis - h, x + bw - 1, y_axis - 1), fill=PALETTE[color])
            d.rectangle((x, y_axis - h, x + bw - 1, y_axis - h + 1), fill=PALETTE["text"])
        _text(d, (x + bw // 2, y_axis - h - 10), fmt_short(v), 8, "text", anchor="ma")
        _text(d, (x + bw // 2, y_axis + 4), lab, 8, "muted", anchor="ma")
    # стрелка между столбиками
    _text(d, (W // 2, (y_top + y_axis) // 2), "->", 8, col, anchor="mm")


# ─── share (waffle) ──────────────────────────────────────────────────────────
def _share(c: Chart, d: ImageDraw.ImageDraw, top: int):
    pct = c.part / c.total * 100
    _text(d, (W // 2, top + 4), f"{fmt(pct, 0)}%", 16, "accent2", anchor="ma")
    _text(d, (W // 2, top + 24), f"{fmt(c.part)} из {fmt(c.total)}", 8, "muted", anchor="ma")
    cell, gap = 16, 2
    gw = 10 * cell + 9 * gap
    gx = (W - gw) // 2
    gy = top + 40
    filled = int(round(pct))
    k = 0
    for r in range(10):
        for col in range(10):
            x = gx + col * (cell + gap)
            y = gy + r * (cell + gap)
            on = k < filled
            d.rectangle((x, y, x + cell - 1, y + cell - 1), fill=PALETTE["accent2" if on else "cell_off"])
            if on:
                d.rectangle((x, y, x + cell - 1, y + 1), fill=PALETTE["text"])
            k += 1


# ─── equiv ───────────────────────────────────────────────────────────────────
def _equiv(c: Chart, d: ImageDraw.ImageDraw, top: int):
    v = c.values[0]
    ul = unit_label(c.unit)
    _text(d, (M, top + 4), f"{fmt(v)} {ul}".strip(), 16, "accent")
    eq = equivalents(v, c.unit, 3)
    y = top + 32
    colors = ["accent2", "up", "down"]
    for i, line in enumerate(eq):
        d.rectangle((M, y, M + 7, y + 7), fill=PALETTE[colors[i % 3]])
        for ln in _wrap("= " + line, (W - 2 * M - 12) // 8, 2):
            _text(d, (M + 12, y), ln, 8, "text")
            y += 12
        y += 4
    # «пересчёт в штуках»: сетка квадратиков по первому эквиваленту
    if eq:
        q = int(eq[0].split()[0].replace(" ", "").replace(",", ".").split(".")[0] or 0)
        q = max(1, min(q, 120))
        cell, gap, per_row = 10, 2, 18
        gx, gy = M, y + 6
        for i in range(q):
            x = gx + (i % per_row) * (cell + gap)
            yy = gy + (i // per_row) * (cell + gap)
            if yy + cell > H - 16 - 12 - 24 - 6:
                break
            d.rectangle((x, yy, x + cell - 1, yy + cell - 1), fill=PALETTE["accent2"])
            d.rectangle((x, yy, x + cell - 1, yy + 1), fill=PALETTE["text"])


def _number(c: Chart, d: ImageDraw.ImageDraw, top: int):
    _text(d, (W // 2, top + 40), fmt(c.values[0]), 16, "accent", anchor="ma")
    _text(d, (W // 2, top + 64), "напиши единицу: ₽, ч, км, кг", 8, "muted", anchor="ma")


RENDERERS = {"bars": _bars, "delta": _delta, "share": _share, "equiv": _equiv, "number": _number}


def render(c: Chart, handle: str = "@channel") -> Image.Image:
    im, d, top = _frame(c, handle)
    RENDERERS[c.kind](c, d, top)
    _insight(d, c)
    return im.resize((W * SCALE, H * SCALE), Image.NEAREST)


def render_png(c: Chart, handle: str = "@channel") -> bytes:
    buf = io.BytesIO()
    render(c, handle).save(buf, "PNG", optimize=True)
    return buf.getvalue()
