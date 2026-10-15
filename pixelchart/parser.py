"""Разбор свободного текста в спецификацию карточки.

Поддерживаемые формы ввода (см. README):
  «12, 34, 56»                       → bars
  «кофе 3 чай 5 вода 8»              → bars с подписями
  «зарплата 80к +5%» / «80к рост 5%» → delta (было/стало)
  «было 80 стало 84»                 → delta
  «30 из 100» / «37%»                → share (вафельный график)
  «15000 рублей» / «3 часа»          → equiv (абсурдные эквиваленты)
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from .numbers import NUM_RE, parse_number

DATA = Path(__file__).resolve().parent.parent / "data" / "equivalents.json"
with DATA.open(encoding="utf-8") as f:
    EQUIV = json.load(f)["units"]

_ALIAS_TO_UNIT: dict[str, str] = {}
for _u, _spec in EQUIV.items():
    for _a in _spec["aliases"]:
        _ALIAS_TO_UNIT[_a.lower()] = _u

_MONEY_WORDS = ("зарплат", "аренд", "цен", "стоимост", "бюджет", "доход", "расход", "налог", "штраф", "кредит", "ипотек", "выручк", "прибыл", "скидк", "чек", "трат", "копил", "сбереж")
_UP_WORDS = ("рост", "выросл", "вырос", "плюс", "подорож", "повыс", "больше", "увелич", "прибав")
_DOWN_WORDS = ("упал", "упад", "падени", "снизил", "сниж", "минус", "подешев", "меньше", "уменьш", "скидк")


@dataclass
class Chart:
    kind: str                       # bars | delta | share | equiv | number
    title: str = ""
    labels: list[str] = field(default_factory=list)
    values: list[float] = field(default_factory=list)
    unit: str | None = None         # ключ из equivalents.json
    pct: float | None = None        # для delta: процент изменения
    part: float | None = None       # для share
    total: float | None = None


class ParseError(ValueError):
    pass


def _clean(text: str) -> str:
    text = text.strip()
    text = re.sub(r"\s+", " ", text)
    return text


def _tokens(text: str) -> list[tuple[str, object]]:
    """Разбивает строку на токены ('num', (value, is_pct)) и ('word', str)."""
    out: list[tuple[str, object]] = []
    pos = 0
    for m in NUM_RE.finditer(text):
        # число внутри слова (например «тикток2») не считаем
        start = m.start("sign") if m.group("sign") else m.start("int")
        if start > 0 and text[start - 1].isalpha():
            continue
        before = text[pos:start]
        for w in re.findall(r"[^\s,;:/]+", before):
            out.append(("word", w))
        out.append(("num", parse_number(m)))
        pos = m.end()
    for w in re.findall(r"[^\s,;:/]+", text[pos:]):
        out.append(("word", w))
    return out


def _unit_of(words: list[str]) -> str | None:
    for w in words:
        key = w.lower().strip(".,!?")
        if key in _ALIAS_TO_UNIT:
            return _ALIAS_TO_UNIT[key]
    if _has(words, _MONEY_WORDS):
        return "rub"
    return None


_TAIL_STOP = {"на", "в", "до", "с", "за", "по", "к", "от", "и", "а"}


def _strip_tail(title: str) -> str:
    ws = title.split()
    while ws and ws[-1].lower() in _TAIL_STOP:
        ws.pop()
    return " ".join(ws)


def _has(words: list[str], stems: tuple[str, ...]) -> bool:
    joined = " ".join(w.lower() for w in words)
    return any(s in joined for s in stems)


def parse(raw: str) -> Chart:
    text = _clean(raw)
    if not text:
        raise ParseError("empty")
    low = text.lower()

    # --- share: «30 из 100», «3 из 10 зумеров»
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:из|/)\s*(\d+(?:[.,]\d+)?)", low)
    if m:
        part = float(m.group(1).replace(",", "."))
        total = float(m.group(2).replace(",", "."))
        if total > 0 and part <= total:
            title = (text[: m.start()] + text[m.end():]).strip(" ,.-—")
            return Chart(kind="share", title=title, part=part, total=total)

    toks = _tokens(text)
    nums = [t[1] for t in toks if t[0] == "num"]
    words = [t[1] for t in toks if t[0] == "word"]
    if not nums:
        raise ParseError("no numbers")

    plain = [v for v, p in nums if not p]
    pcts = [v for v, p in nums if p]

    # --- share: одиночный процент «37%»
    if len(nums) == 1 and nums[0][1]:
        v = nums[0][0]
        if 0 <= v <= 100:
            return Chart(kind="share", title=" ".join(words), part=v, total=100)

    # --- delta: число + процент
    if len(plain) == 1 and len(pcts) == 1:
        base = plain[0]
        pct = pcts[0]
        # знак берём из текста, если процент без знака
        if not re.search(r"[+\-−–]\s*\d+(?:[.,]\d+)?\s*%", text) and _has(words, _DOWN_WORDS):
            pct = -abs(pct)
        new = base * (1 + pct / 100)
        title = _strip_tail(" ".join(w for w in words if w.lower().strip(".,") not in _ALIAS_TO_UNIT))
        return Chart(kind="delta", title=title, values=[base, new], pct=pct, unit=_unit_of(words))

    # --- delta: «было 80 стало 84» / «80 → 84»
    if len(plain) == 2 and not pcts and (
        _has(words, ("было", "стало", "вместо")) or "→" in text or "->" in text or _has(words, _UP_WORDS + _DOWN_WORDS)
    ):
        a, b = plain
        pct = (b - a) / a * 100 if a else 0
        title = " ".join(w for w in words if w.lower() not in ("было", "стало", "вместо", "->", "→") and w.lower().strip(".,") not in _ALIAS_TO_UNIT)
        return Chart(kind="delta", title=title, values=[a, b], pct=pct, unit=_unit_of(words))

    # --- equiv: одно число с известной единицей
    if len(plain) == 1 and not pcts:
        unit = _unit_of(words)
        v = plain[0]
        title = " ".join(w for w in words if w.lower().strip(".,") not in _ALIAS_TO_UNIT)
        if unit:
            return Chart(kind="equiv", title=title, values=[v], unit=unit)
        return Chart(kind="number", title=title, values=[v])

    # --- bars: несколько чисел, подписи из слов рядом
    values: list[float] = []
    labels: list[str] = []
    title_words: list[str] = []
    pending: list[str] = []
    # Схема A: слово(а) число слово(а) число…  Схема B: число слово(а) число слово(а)…
    first_num_idx = next(i for i, t in enumerate(toks) if t[0] == "num")
    scheme_b = first_num_idx == 0 and any(t[0] == "word" for t in toks[1:])
    if scheme_b:
        cur_val: float | None = None
        for kind, val in toks:
            if kind == "num":
                if cur_val is not None:
                    values.append(cur_val)
                    labels.append(" ".join(pending) or "")
                    pending = []
                cur_val = val[0]
            else:
                pending.append(val)
        if cur_val is not None:
            values.append(cur_val)
            labels.append(" ".join(pending))
    else:
        for kind, val in toks:
            if kind == "num":
                values.append(val[0])
                labels.append(" ".join(pending))
                pending = []
            else:
                pending.append(val)
        title_words = pending  # хвост после последнего числа → в заголовок

    # Если подпись есть только у первого столбика — это заголовок, а не подпись
    nonempty = [l for l in labels if l]
    if len(nonempty) <= 1 and len(values) > 1:
        title_words = nonempty + title_words
        labels = [""] * len(values)
    # единица измерения из подписей не нужна как label
    unit = _unit_of(words)
    labels = [l for l in labels]
    if len(values) > 12:
        values, labels = values[:12], labels[:12]
    return Chart(kind="bars", title=" ".join(title_words).strip(), labels=labels, values=values, unit=unit)
