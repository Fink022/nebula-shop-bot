from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from nebula.db.models import CartItem
from nebula.filters import IsPrivate
from nebula.keyboards import cart_kb, empty_cart_kb
from nebula.services.orders import valid_promo
from nebula.utils import cart_totals, esc, fmt_price, get_cart_rows, render_screen

router = Router()
router.message.filter(IsPrivate())
router.callback_query.filter(IsPrivate())


class PromoState(StatesGroup):
    code = State()


def _promo_prompt_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="⬅️ Назад в корзину", callback_data="menu:cart")
    return builder.as_markup()


async def render_cart(
    message: Message,
    session: AsyncSession,
    state: FSMContext,
    user_id: int,
    note: str | None = None,
) -> None:
    data = await state.get_data()
    promo = data.get("promo")
    rows = await get_cart_rows(session, user_id)

    if not rows:
        await render_screen(
            message,
            "🛒 <b>Корзина пуста</b>\n\nДобавь товар из каталога.",
            empty_cart_kb(),
        )
        return

    promo_row = await valid_promo(session, promo)
    discount_percent = promo_row.discount if promo_row else 0
    subtotal, discount = cart_totals(rows, discount_percent)
    total = subtotal - discount

    lines = ["🛒 <b>Твоя корзина</b>\n"]
    for item, product in rows[:20]:
        lines.append(f"▪️ {esc(product.title)} ×{item.qty} — {fmt_price(item.qty * product.price)}")
    if len(rows) > 20:
        lines.append(f"<i>…и ещё {len(rows) - 20} позиций</i>")
    lines.append("")
    if discount:
        lines.append(f"🎟 Промокод <b>{promo}</b>: −{fmt_price(discount)}")
    lines.append(f"💰 Итого: <b>{fmt_price(total)}</b>")

    body = "\n".join(lines)
    if note:
        body = f"{note}\n\n{body}"
    await render_screen(message, body, cart_kb(rows[:20], total))


@router.callback_query(F.data == "menu:cart")
async def show_cart(call: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    await state.set_state(None)
    await render_cart(call.message, session, state, call.from_user.id)
    await call.answer()


@router.callback_query(F.data.startswith("cart:inc:"))
async def increase(call: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    item = await session.get(CartItem, int(call.data.split(":")[2]))
    if item and item.user_id == call.from_user.id:
        item.qty = min(item.qty + 1, 99)
    await render_cart(call.message, session, state, call.from_user.id)
    await call.answer()


@router.callback_query(F.data.startswith("cart:dec:"))
async def decrease(call: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    item = await session.get(CartItem, int(call.data.split(":")[2]))
    if item and item.user_id == call.from_user.id:
        if item.qty > 1:
            item.qty -= 1
        else:
            await session.delete(item)
    await render_cart(call.message, session, state, call.from_user.id)
    await call.answer()


@router.callback_query(F.data.startswith("cart:del:"))
async def remove(call: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    item = await session.get(CartItem, int(call.data.split(":")[2]))
    if item and item.user_id == call.from_user.id:
        await session.delete(item)
    await render_cart(call.message, session, state, call.from_user.id)
    await call.answer("Удалено")


@router.callback_query(F.data == "cart:clear")
async def clear(call: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    await session.execute(delete(CartItem).where(CartItem.user_id == call.from_user.id))
    await state.update_data(promo=None)
    await render_cart(call.message, session, state, call.from_user.id)
    await call.answer("Корзина очищена 🧹")


@router.callback_query(F.data == "cart:promo")
async def ask_promo(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(PromoState.code)
    await render_screen(
        call.message,
        "🎟 <b>Введи промокод</b>\n\nОтправь его сообщением (например, <code>NEBULA10</code>):",
        _promo_prompt_kb(),
    )
    await call.answer()


@router.message(PromoState.code, F.text)
async def apply_promo(message: Message, session: AsyncSession, state: FSMContext) -> None:
    code = message.text.strip().upper()
    promo = await valid_promo(session, code)
    if not promo:
        await message.answer(
            "❌ Промокод не найден или уже не действует.\nПопробуй другой:",
            reply_markup=_promo_prompt_kb(),
        )
        return

    await state.update_data(promo=code)
    await state.set_state(None)
    await render_cart(
        message,
        session,
        state,
        message.from_user.id,
        note=f"✅ Промокод <b>{code}</b> применён: скидка −{promo.discount}%",
    )
