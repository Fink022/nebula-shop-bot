import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, LabeledPrice, Message, PreCheckoutQuery
from sqlalchemy.ext.asyncio import AsyncSession

from nebula.config import config
from nebula.db.models import Order
from nebula.filters import IsPrivate
from nebula.keyboards import checkout_kb
from nebula.services.orders import (
    cancel_pending_orders,
    consume_promo,
    create_order,
    deliver_order,
    send_delivery_message,
    valid_promo,
)
from nebula.utils import (
    cart_totals,
    drop_screen,
    fmt_price,
    get_cart_rows,
    get_or_create_user,
    render_screen,
    user_lock,
)

logger = logging.getLogger(__name__)

router = Router()
router.message.filter(IsPrivate())
router.callback_query.filter(IsPrivate())


async def _cart_context(session: AsyncSession, user_id: int, state: FSMContext):
    rows = await get_cart_rows(session, user_id)
    data = await state.get_data()
    promo = data.get("promo") or ""
    promo_row = await valid_promo(session, promo)
    discount_percent = promo_row.discount if promo_row else 0
    subtotal, discount = cart_totals(rows, discount_percent)
    return rows, promo, subtotal, discount


@router.callback_query(F.data == "checkout")
async def checkout(call: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    rows, _promo, subtotal, discount = await _cart_context(session, call.from_user.id, state)
    if not rows:
        await call.answer("Корзина пуста — сначала добавь товары 🛍", show_alert=True)
        return

    total = subtotal - discount
    user = await get_or_create_user(session, call.from_user)
    text = (
        "🧾 <b>Оформление заказа</b>\n\n"
        f"Товаров: {sum(item.qty for item, _ in rows)} шт на {fmt_price(subtotal)}"
    )
    if discount:
        text += f"\n🎟 Скидка по промокоду: −{fmt_price(discount)}"
    stars = max(1, round(total * config.stars_rate))
    rate_note = "1:1" if config.stars_rate == 1 else f"курс {config.stars_rate:g}"
    text += (
        f"\n\n💰 <b>К оплате: {fmt_price(total)}</b>\n"
        f"⭐ Можно оплатить звёздами: {stars} ⭐ ({rate_note})\n"
        f"💠 У тебя {user.bonus} бонусов"
    )

    await render_screen(call.message, text, checkout_kb(total, user.bonus >= total))
    await call.answer()


@router.callback_query(F.data == "pay:stars")
async def pay_stars(call: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    async with user_lock(call.from_user.id):
        rows, promo, subtotal, discount = await _cart_context(session, call.from_user.id, state)
        if not rows:
            await call.answer("Корзина пуста", show_alert=True)
            return

        total = subtotal - discount
        user = await get_or_create_user(session, call.from_user)
        await cancel_pending_orders(call.bot, session, user.id)

        order = await create_order(
            session, user, rows, total, discount, promo, payment="stars", status="pending"
        )
        stars = max(1, round(total * config.stars_rate))
        invoice = await call.bot.send_invoice(
            chat_id=user.id,
            title=f"Заказ #{order.id} · Nebula Shop",
            description=f"Оплата {sum(item.qty for item, _ in rows)} товаров в Nebula Shop",
            payload=f"order:{order.id}",
            provider_token="",
            currency="XTR",
            prices=[LabeledPrice(label=f"Заказ #{order.id}", amount=stars)],
        )
        order.invoice_message_id = invoice.message_id
    await call.answer("⭐ Счёт отправлен!")


@router.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery, session: AsyncSession) -> None:
    try:
        order_id = int(query.invoice_payload.split(":")[1])
    except (ValueError, IndexError):
        await query.answer(ok=False, error_message="Некорректный счёт")
        return
    order = await session.get(Order, order_id)
    if not order or order.user_id != query.from_user.id:
        await query.answer(ok=False, error_message="Заказ не найден")
        return
    if order.status != "pending":
        await query.answer(ok=False, error_message="Этот счёт уже неактуален")
        return
    await query.answer(ok=True)


@router.message(F.successful_payment)
async def paid(message: Message, session: AsyncSession, state: FSMContext) -> None:
    try:
        order_id = int(message.successful_payment.invoice_payload.split(":")[1])
    except (ValueError, IndexError):
        return

    async with user_lock(message.from_user.id):
        # проверка под локом: Telegram может доставить апдейт об оплате дважды
        order = await session.get(Order, order_id)
        if not order or order.user_id != message.from_user.id:
            logger.warning("Оплата по неизвестному заказу: %s", order_id)
            await message.answer("⚠️ Платёж пришёл, но заказ не нашёлся. Напиши в этот чат ещё раз.")
            return
        if order.status == "delivered":
            return

        user = await get_or_create_user(session, message.from_user)
        await consume_promo(session, order.promo)
        text, kb = await deliver_order(session, order, user)
        await session.commit()
        await send_delivery_message(message.bot, user.id, text, kb)
    await drop_screen(message.bot, message.chat.id)
    await state.clear()


@router.callback_query(F.data == "pay:bonus")
async def pay_bonus(call: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    async with user_lock(call.from_user.id):
        rows, promo, subtotal, discount = await _cart_context(session, call.from_user.id, state)
        if not rows:
            await call.answer("Корзина пуста", show_alert=True)
            return

        total = subtotal - discount
        user = await get_or_create_user(session, call.from_user)
        if user.bonus < total:
            await call.answer("Недостаточно бонусов 💠", show_alert=True)
            return

        await cancel_pending_orders(call.bot, session, user.id)
        user.bonus -= total
        order = await create_order(
            session, user, rows, total, discount, promo, payment="bonus", status="paid"
        )
        await consume_promo(session, promo)
        text, kb = await deliver_order(session, order, user)
        await session.commit()
        await send_delivery_message(call.bot, user.id, text, kb)
    await drop_screen(call.bot, call.message.chat.id)
    await state.clear()
    await call.answer("Оплачено 💠")
