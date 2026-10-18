import asyncio
import html
from datetime import datetime, timezone
from pathlib import Path
from weakref import WeakValueDictionary

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import FSInputFile, InlineKeyboardMarkup, InputMediaPhoto, Message
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from nebula.db.models import CartItem, Product, User

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCREENS: dict[int, int] = {}
USER_LOCKS: WeakValueDictionary[int, asyncio.Lock] = WeakValueDictionary()

STATUS_RU = {
    "pending": "⏳ ожидает оплаты",
    "paid": "✅ оплачен",
    "delivered": "🚀 выполнен",
    "cancelled": "❌ отменён",
}
PAYMENT_RU = {
    "stars": "⭐ Telegram Stars",
    "bonus": "💠 бонусы",
}


def user_lock(user_id: int) -> asyncio.Lock:
    lock = USER_LOCKS.get(user_id)
    if lock is None:
        lock = asyncio.Lock()
        USER_LOCKS[user_id] = lock
    return lock


def esc(value) -> str:
    return html.escape(str(value or ""))


def as_local(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc).astimezone()


def fmt_price(value: int) -> str:
    return f"{value:,}".replace(",", " ") + " ₽"


def photo_source(product: Product):
    if product.photo and product.photo.startswith("assets/"):
        path = PROJECT_ROOT / product.photo
        return FSInputFile(path) if path.exists() else None
    return product.photo or None


def product_caption(product: Product, index: int | None = None, total: int | None = None) -> str:
    description = product.description[:400]
    caption = (
        f"<b>{esc(product.title)}</b>\n\n{esc(description)}\n\n💰 <b>{fmt_price(product.price)}</b>"
    )
    if index and total:
        caption += f"\n\n<i>Позиция {index} из {total}</i>"
    return caption


async def get_or_create_user(session: AsyncSession, tg_user) -> User:
    values = {
        "id": tg_user.id,
        "username": getattr(tg_user, "username", None),
        "first_name": getattr(tg_user, "first_name", None) or "",
    }
    update: dict = {}
    if values["username"]:
        update["username"] = values["username"]
    if values["first_name"]:
        update["first_name"] = values["first_name"]
    stmt = sqlite_insert(User).values(**values)
    if update:
        stmt = stmt.on_conflict_do_update(index_elements=[User.id], set_=update)
    else:
        stmt = stmt.on_conflict_do_nothing(index_elements=[User.id])
    await session.execute(stmt)
    return await session.get(User, tg_user.id)


async def get_cart_rows(session: AsyncSession, user_id: int) -> list[tuple[CartItem, Product]]:
    result = await session.execute(
        select(CartItem, Product)
        .join(Product, CartItem.product_id == Product.id)
        .where(CartItem.user_id == user_id, Product.is_active)
        .order_by(CartItem.id)
    )
    return list(result.all())


def cart_totals(rows: list[tuple[CartItem, Product]], promo_discount: int = 0) -> tuple[int, int]:
    subtotal = sum(item.qty * product.price for item, product in rows)
    discount = subtotal * promo_discount // 100
    return subtotal, discount


async def _safe_delete(bot, chat_id: int, message_id: int) -> None:
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception:
        pass


async def drop_screen(bot, chat_id: int) -> None:
    tracked = SCREENS.pop(chat_id, None)
    if tracked:
        await _safe_delete(bot, chat_id, tracked)


async def render_screen(
    msg: Message,
    caption: str,
    kb: InlineKeyboardMarkup | None = None,
    photo=None,
) -> Message:
    bot = msg.bot
    chat_id = msg.chat.id
    private = msg.chat.type == "private"
    tracked = SCREENS.get(chat_id) if private else None
    is_bot_message = msg.from_user is not None and msg.from_user.id == bot.id

    target = msg if is_bot_message else None
    stale = tracked if tracked and (target is None or tracked != target.message_id) else None

    if photo is not None and len(caption) > 1024:
        photo = None

    if target is not None:
        try:
            if photo is not None and target.photo:
                result = await target.edit_media(
                    media=InputMediaPhoto(media=photo, caption=caption, parse_mode="HTML"),
                    reply_markup=kb,
                )
                if private:
                    SCREENS[chat_id] = result.message_id
                if stale:
                    await _safe_delete(bot, chat_id, stale)
                return result
            if photo is None and not target.photo:
                result = await target.edit_text(caption, reply_markup=kb)
                if private:
                    SCREENS[chat_id] = result.message_id
                if stale:
                    await _safe_delete(bot, chat_id, stale)
                return result
        except TelegramBadRequest as error:
            if "not modified" in str(error):
                if private:
                    SCREENS[chat_id] = target.message_id
                return target

    if photo is not None:
        result = await msg.answer_photo(photo, caption=caption, reply_markup=kb)
    else:
        result = await msg.answer(caption, reply_markup=kb)
    if private:
        SCREENS[chat_id] = result.message_id
    if target is not None:
        await _safe_delete(bot, chat_id, target.message_id)
    if stale and stale != result.message_id:
        await _safe_delete(bot, chat_id, stale)
    return result
