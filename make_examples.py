"""python make_examples.py — перерисовать примеры карточек в examples/."""
from pathlib import Path
from pixelchart.parser import parse
from pixelchart.render import render

EXAMPLES = {
    "bars": "12, 34, 56",
    "bars_labels": "тикток 6 сон 5 учёба 2",
    "delta": "зарплата 80к +5%",
    "delta_down": "цена билета было 120 стало 90",
    "share": "30 из 100 зумеров не пьют кофе",
    "equiv": "15000 рублей",
}
out = Path("examples"); out.mkdir(exist_ok=True)
for name, text in EXAMPLES.items():
    render(parse(text), "@punkt_infografiki").save(out / f"{name}.png")
    print(name, "<-", text)
