from pixelchart.parser import parse


def test_bars():
    c = parse("12, 34, 56")
    assert c.kind == "bars" and c.values == [12, 34, 56]


def test_bars_labels():
    c = parse("кофе 3 чай 5 вода 8")
    assert c.kind == "bars" and c.labels == ["кофе", "чай", "вода"]


def test_delta_pct():
    c = parse("зарплата 80к +5%")
    assert c.kind == "delta" and c.values == [80000, 84000] and c.unit == "rub"


def test_delta_down_words():
    c = parse("аренда 45к упала на 10%")
    assert c.kind == "delta" and c.pct == -10 and c.title == "аренда упала"


def test_share():
    assert parse("30 из 100").kind == "share"
    assert parse("37%").part == 37


def test_equiv():
    c = parse("15000 рублей")
    assert c.kind == "equiv" and c.unit == "rub"
