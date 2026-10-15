"""Парсинг и форматирование чисел в человеческом русском вводе: 80к, 1,5 млн, 12 000."""
from __future__ import annotations

import re

_SUFFIX = {
    "к": 1_000, "k": 1_000, "тыс": 1_000, "тыс.": 1_000,
    "м": 1_000_000, "млн": 1_000_000, "m": 1_000_000,
    "млрд": 1_000_000_000, "b": 1_000_000_000,
}

# число: 12 | 12.5 | 12,5 | 12 000 | 80к | 1,5млн | +5% | -3%
NUM_RE = re.compile(
    r"(?P<sign>[+\-−–])?\s*"
    r"(?P<int>\d{1,3}(?:[  ]\d{3})+|\d+)"
    r"(?:[.,](?P<frac>\d+))?"
    r"\s*(?P<suf>к|k|тыс\.?|млн|м|m|млрд|b)?"
    r"(?P<pct>\s*%)?",
    re.IGNORECASE,
)


def parse_number(m: re.Match) -> tuple[float, bool]:
    """Возвращает (значение, это_процент)."""
    s = m.group("int").replace(" ", "").replace(" ", "")
    val = float(s)
    if m.group("frac"):
        val += float("0." + m.group("frac"))
    suf = (m.group("suf") or "").lower()
    if suf:
        val *= _SUFFIX.get(suf, 1)
    if m.group("sign") in ("-", "−", "–"):
        val = -val
    return val, bool(m.group("pct"))


def fmt(x: float, max_frac: int = 1) -> str:
    """12345.0 → '12 345'; 4.666 → '4,7'; 0.5 → '0,5'."""
    if abs(x) >= 1000:
        s = f"{round(x):,.0f}".replace(",", " ")
        return s
    if float(x).is_integer():
        return str(int(x))
    s = f"{x:.{max_frac}f}".rstrip("0").rstrip(".")
    return s.replace(".", ",")


def fmt_short(x: float) -> str:
    """Короткая запись для осей: 84000 → '84к', 1 500 000 → '1,5 млн'."""
    ax = abs(x)
    if ax >= 1_000_000_000:
        return fmt(x / 1_000_000_000) + " млрд"
    if ax >= 1_000_000:
        return fmt(x / 1_000_000) + " млн"
    if ax >= 1_000:
        return fmt(x / 1_000) + "к"
    return fmt(x)


def plural(n: float, one: str, few: str, many: str) -> str:
    if not float(n).is_integer():
        return few
    n = abs(int(round(n)))
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many
