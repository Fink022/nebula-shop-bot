from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from nebula.config import config
from nebula.db.models import Order, User
from nebula.filters import IsPrivate
from nebula.keyboards import profile_kb, referral_kb
from nebula.utils import STATUS_RU, fmt_price, get_or_create_user, render_screen

router = Router()
router.callback_query.filter(IsPrivate())


@router.callback_query(F.data == "menu:profile")
async def profile(call: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    await state.set_state(None)
    user = await get_or_create_user(session, call.from_user)
    orders = await session.scalar(
        select(func.count(Order.id)).where(Order.user_id == user.id, Order.status == "delivered")
    )
    spent = await session.scalar(
        select(func.coalesce(func.sum(Order.total), 0)).where(
            Order.user_id == user.id, Order.status == "delivered"
        )
    )
    invited = await session.scalar(select(func.count(User.id)).where(User.referred_by == user.id))

    text = (
        "👤 <b>Твой профиль</b>\n\n"
        f"🆔 ID: <code>{user.id}</code>\n"
        f"💠 Бонусы: <b>{user.bonus}</b>\n"
        f"📦 Заказов: {orders}\n"
        f"💰 Потрачено: {fmt_price(spent)}\n"
        f"🤝 Приглашено друзей: {invited}"
    )
    await render_screen(call.message, text, profile_kb())
    await call.answer()


@router.callback_query(F.data == "my:orders")
async def my_orders(call: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    await state.set_state(None)
    orders = list(
        (
            await session.scalars(
                select(Order)
                .where(Order.user_id == call.from_user.id)
                .order_by(Order.id.desc())
                .limit(5)
            )
        ).all()
    )
    builder = InlineKeyboardBuilder()
    builder.button(text="⬅️ В профиль", callback_data="menu:profile")

    if not orders:
        text = "📦 <b>Мои заказы</b>\n\nЗаказов пока нет."
    else:
        blocks = ["📦 <b>Мои заказы</b>\n"]
        for order in orders:
            status = STATUS_RU.get(order.status, order.status)
            blocks.append(f"#{order.id} · {fmt_price(order.total)} · {status}")
        text = "\n".join(blocks)

    await render_screen(call.message, text, builder.as_markup())
    await call.answer()


@router.callback_query(F.data == "menu:ref")
async def referral(call: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    await state.set_state(None)
    user = await get_or_create_user(session, call.from_user)
    invited = await session.scalar(select(func.count(User.id)).where(User.referred_by == user.id))
    link = f"https://t.me/{config.bot_username}?start=ref_{user.id}"

    text = (
        "🎁 <b>Партнёрская программа</b>\n\n"
        f"Приглашай друзей и получай <b>{config.referral_bonus_inviter} бонусов</b> "
        "за каждого!\n"
        f"А друг получит {config.referral_bonus_newbie} бонусов на первый заказ.\n\n"
        f"Твоя ссылка:\n<code>{link}</code>\n\n"
        f"🤝 Уже приглашено: {invited}"
    )
    await render_screen(call.message, text, referral_kb(link))
    await call.answer()
