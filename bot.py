"""Инлайн-бот «пиксельный график в любом чате».

Работает в двух режимах:
  • инлайн: @бот 12, 34, 56 → карточка вставляется прямо в чат
  • личка: любое сообщение с числами → карточка в ответ

Перед выдачей карточки проверяет подписку на канал (REQUIRE_SUB=1).
Картинки для инлайна кэшируются через отправку в CACHE_CHAT_ID (по умолчанию — ЛС владельца).
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import time
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQuery,
    InlineQueryResultArticle,
    InlineQueryResultCachedPhoto,
    InlineQueryResultsButton,
    InputTextMessageContent,
    Message,
)
from dotenv import load_dotenv

from pixelchart.insights import caption
from pixelchart.parser import ParseError, parse
from pixelchart.render import render_png

load_dotenv()
BOT_TOKEN = os.environ["BOT_TOKEN"]
CHANNEL_ID = os.environ.get("CHANNEL_ID", "@punkt_infografiki")      # @username или -100…
CHANNEL_URL = os.environ.get("CHANNEL_URL", "https://t.me/punkt_infografiki")
HANDLE = os.environ.get("CHANNEL_HANDLE", "@punkt_infografiki")      # подпись на карточке
OWNER_ID = int(os.environ.get("OWNER_ID", "0"))
CACHE_CHAT_ID = int(os.environ.get("CACHE_CHAT_ID", str(OWNER_ID)))
REQUIRE_SUB = os.environ.get("REQUIRE_SUB", "1") == "1"
CACHE_FILE = Path(os.environ.get("CACHE_FILE", "cache.json"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("pixelchart")

bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

HELP = (
    "Я рисую пиксельные графики из чисел. Напиши мне или вызови в любом чате через <code>@{me}</code>:\n\n"
    "• <code>12, 34, 56</code> — столбики\n"
    "• <code>кофе 3 чай 5 вода 8</code> — столбики с подписями\n"
    "• <code>зарплата 80к +5%</code> — было / стало\n"
    "• <code>было 120 стало 90</code> — тоже было / стало\n"
    "• <code>30 из 100</code> или <code>37%</code> — доля\n"
    "• <code>15000 рублей</code>, <code>3 часа</code>, <code>700 км</code> — сколько это в шаурме\n\n"
    "Единицы: ₽, часы, минуты, км, кг, граммы, годы, люди."
)

# ─── кэш file_id для инлайна ────────────────────────────────────────────────
_cache: dict[str, str] = {}
if CACHE_FILE.exists():
    try:
        _cache = json.loads(CACHE_FILE.read_text("utf-8"))
    except Exception:
        _cache = {}


def _save_cache() -> None:
    try:
        CACHE_FILE.write_text(json.dumps(_cache, ensure_ascii=False), "utf-8")
    except Exception as e:  # pragma: no cover
        log.warning("cache save failed: %s", e)


# ─── примитивный лимит: не чаще 1 карточки в 2 секунды на человека ──────────
_last: dict[int, float] = {}


def _rate_ok(uid: int) -> bool:
    now = time.monotonic()
    if now - _last.get(uid, 0) < 2:
        return False
    _last[uid] = now
    return True


# ─── подписка ───────────────────────────────────────────────────────────────
async def is_subscribed(user_id: int) -> bool:
    if not REQUIRE_SUB:
        return True
    try:
        m = await bot.get_chat_member(CHANNEL_ID, user_id)
        return m.status in ("member", "administrator", "creator")
    except Exception as e:
        log.warning("get_chat_member failed: %s", e)
        return True  # если бот не админ канала — не блокируем людей


def sub_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Подписаться на канал", url=CHANNEL_URL)],
        [InlineKeyboardButton(text="Я подписалась ✓", callback_data="check_sub")],
    ])


async def share_keyboard() -> InlineKeyboardMarkup:
    me = await bot.me()
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Сделать свой график", switch_inline_query_current_chat="")],
        [InlineKeyboardButton(text=HANDLE, url=CHANNEL_URL)],
    ])


# ─── рендер + кэш ───────────────────────────────────────────────────────────
def _key(text: str) -> str:
    return hashlib.sha1(text.strip().lower().encode()).hexdigest()[:16]


async def render_cached(text: str) -> tuple[str, str] | None:
    """Возвращает (file_id, caption) или None, если разобрать не удалось."""
    try:
        chart = parse(text)
    except ParseError:
        return None
    cap = caption(chart, HANDLE)
    k = _key(text)
    if k in _cache:
        return _cache[k], cap
    png = await asyncio.to_thread(render_png, chart, HANDLE)
    if not CACHE_CHAT_ID:
        raise RuntimeError("CACHE_CHAT_ID / OWNER_ID не задан — инлайн-режим не может кэшировать картинки")
    msg = await bot.send_photo(CACHE_CHAT_ID, BufferedInputFile(png, "chart.png"), caption=f"inline: {text[:200]}")
    file_id = msg.photo[-1].file_id
    _cache[k] = file_id
    _save_cache()
    return file_id, cap


# ─── handlers ───────────────────────────────────────────────────────────────
@dp.message(CommandStart())
async def start(m: Message):
    me = await bot.me()
    if not await is_subscribed(m.from_user.id):
        await m.answer(
            f"Привет! Чтобы пользоваться ботом, подпишись на канал {HANDLE} — там про инфографику и то, как графики врут.",
            reply_markup=sub_keyboard(),
        )
        return
    await m.answer(HELP.format(me=me.username))


@dp.message(Command("help"))
async def help_cmd(m: Message):
    me = await bot.me()
    await m.answer(HELP.format(me=me.username))


@dp.message(Command("id"))
async def id_cmd(m: Message):
    await m.answer(f"chat_id: <code>{m.chat.id}</code>\nuser_id: <code>{m.from_user.id}</code>")


@dp.callback_query(F.data == "check_sub")
async def check_sub(cq: CallbackQuery):
    if await is_subscribed(cq.from_user.id):
        me = await bot.me()
        await cq.message.edit_text("Ура, спасибо! " + HELP.format(me=me.username))
    else:
        await cq.answer("Пока не вижу подписки 🙈 Подпишись и нажми ещё раз", show_alert=True)


@dp.message(F.chat.type == "private", F.text)
async def private_text(m: Message):
    if not _rate_ok(m.from_user.id):
        return
    if not await is_subscribed(m.from_user.id):
        await m.answer(f"Сначала подпишись на {HANDLE}, это бесплатно 🙏", reply_markup=sub_keyboard())
        return
    try:
        chart = parse(m.text)
    except ParseError:
        await m.answer("Не нашла чисел. Напиши, например, <code>кофе 3 чай 5</code> или <code>80к +5%</code>")
        return
    png = await asyncio.to_thread(render_png, chart, HANDLE)
    await m.answer_photo(BufferedInputFile(png, "chart.png"), caption=caption(chart, HANDLE), reply_markup=await share_keyboard())


@dp.inline_query()
async def inline(q: InlineQuery):
    text = q.query.strip()
    me = await bot.me()
    if not text:
        await q.answer(
            [InlineQueryResultArticle(
                id="help", title="Напиши числа: 12, 34, 56 или кофе 3 чай 5",
                description="Также: 80к +5% · 30 из 100 · 15000 рублей",
                input_message_content=InputTextMessageContent(message_text=HELP.format(me=me.username)),
            )],
            cache_time=60, is_personal=True,
        )
        return
    if not await is_subscribed(q.from_user.id):
        await q.answer(
            [], cache_time=5, is_personal=True,
            button=InlineQueryResultsButton(text=f"Подпишись на {HANDLE}, чтобы рисовать графики", start_parameter="sub"),
        )
        return
    if not _rate_ok(q.from_user.id):
        return
    try:
        res = await render_cached(text)
    except Exception as e:
        log.exception("render failed: %s", e)
        res = None
    if res is None:
        await q.answer(
            [InlineQueryResultArticle(
                id="nonum", title="Не нашла чисел 🙈", description="Пример: кофе 3 чай 5 · 80к +5% · 30 из 100",
                input_message_content=InputTextMessageContent(message_text=text),
            )],
            cache_time=5, is_personal=True,
        )
        return
    file_id, cap = res
    await q.answer(
        [InlineQueryResultCachedPhoto(
            id=_key(text), photo_file_id=file_id, caption=cap, reply_markup=await share_keyboard(),
        )],
        cache_time=300, is_personal=False,
    )


async def main():
    me = await bot.me()
    log.info("started as @%s, channel=%s, require_sub=%s, cache_chat=%s", me.username, CHANNEL_ID, REQUIRE_SUB, CACHE_CHAT_ID)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
