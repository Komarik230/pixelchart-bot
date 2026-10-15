"""Человеческий вывод к карточке: одна строка на картинку и подпись под фото."""
from __future__ import annotations

from .numbers import fmt, plural
from .parser import EQUIV, Chart

LETTERS = "ABCDEFGHIJKL"


def unit_label(unit: str | None) -> str:
    return EQUIV[unit]["label"] if unit else ""


def equivalents(value: float, unit: str, n: int = 3) -> list[str]:
    """Подбирает n самых «читаемых» эквивалентов: количество от 1 до 999."""
    items = EQUIV[unit]["items"]
    scored = []
    for it in items:
        q = value / it["value"]
        if q < 0.5:
            continue
        # предпочитаем числа от 2 до 300
        score = abs(q - 20) if q <= 300 else 1000 + q
        scored.append((score, q, it))
    scored.sort(key=lambda s: s[0])
    out = []
    for _, q, it in scored[:n]:
        qr = round(q) if q >= 10 else round(q, 1)
        if float(qr).is_integer():
            qr = int(qr)
        word = plural(qr, *it["forms"])
        out.append(f"{fmt(qr)} {word}")
    return out


def insight(c: Chart) -> str:
    """Строка-вывод, которая печатается внизу карточки (коротко, до ~40 символов)."""
    if c.kind == "bars":
        vals = c.values
        labels = [l or LETTERS[i] for i, l in enumerate(c.labels)]
        imax = max(range(len(vals)), key=lambda i: vals[i])
        imin = min(range(len(vals)), key=lambda i: vals[i])
        if vals[imin] > 0 and imax != imin:
            r = vals[imax] / vals[imin]
            if r >= 1.15:
                return f"{labels[imax]} больше {labels[imin]} в {fmt(r)} {plural(r, 'раз', 'раза', 'раз')}"
        total = sum(v for v in vals if v > 0)
        if total > 0 and len(vals) > 2:
            share = vals[imax] / total * 100
            return f"{labels[imax]}: {fmt(share, 0)}% от суммы"
        return f"сумма: {fmt(sum(vals))}"

    if c.kind == "delta":
        a, b = c.values
        diff = b - a
        sign = "+" if diff >= 0 else "-"
        ul = unit_label(c.unit)
        line = f"{sign}{fmt(abs(diff))}{(' ' + ul) if ul else ''}"
        if c.unit:
            eq = equivalents(abs(diff), c.unit, 1)
            if eq:
                line += f" = {eq[0]}"
        return line

    if c.kind == "share":
        pct = c.part / c.total * 100
        if pct > 0:
            every = c.total / c.part
            if 2 <= every <= 20 and abs(every - round(every)) < 0.15:
                return f"это каждый {int(round(every))}-й"
            return f"это {fmt(pct, 0)}%"
        return "0%"

    return ""


def caption(c: Chart, handle: str) -> str:
    """Подпись под фото в Telegram."""
    head = c.title.strip() or {
        "bars": "сравнение", "delta": "было / стало", "share": "доля", "equiv": "сколько это", "number": "число",
    }[c.kind]
    line = insight(c)
    if c.kind == "equiv":
        line = "\n".join("= " + e for e in equivalents(c.values[0], c.unit, 3))
    body = f"{head}\n{line}" if line else head
    return f"{body}\n\nграфик из {handle}"
