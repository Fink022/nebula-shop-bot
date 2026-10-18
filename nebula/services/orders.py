import logging

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from nebula.config import config
from nebula.db.models import CartItem, Order, OrderItem, PromoCode, User
from nebula.keyboards import review_kb
from nebula.utils import esc, fmt_price

logger = logging.getLogger(__name__)


async def valid_promo(session: AsyncSession, code: str) -> PromoCode | None:
    if not code:
        return None
    promo = await session.scalar(select(PromoCode).where(PromoCode.code == code.upper()))
    if promo and promo.is_active and promo.used < promo.max_uses:
        return promo
    return None


async def consume_promo(session: AsyncSession, code: str) -> bool:
    if not code:
        return False
    # атомарный инкремент: параллельные заказы не смогут превысить max_uses
    result = await session.execute(
        update(PromoCode)
        .where(PromoCode.code == code.upper(), PromoCode.used < PromoCode.max_uses)
        .values(used=PromoCode.used + 1)
    )
    return result.rowcount > 0


async def create_order(
    session: AsyncSession,
    user: User,
    rows,
    total: int,
    discount: int,
    promo: str,
    payment: str,
    status: str,
) -> Order:
    order = Order(
        user_id=user.id,
        total=total,
        discount=discount,
        promo=promo,
        payment=payment,
        status=status,
    )
    session.add(order)
    await session.flush()
    for item, product in rows:
        session.add(
            OrderItem(
                order_id=order.id,
                product_id=product.id,
                title=product.title,
                price=product.price,
                qty=item.qty,
            )
        )
    return order


async def cancel_pending_orders(bot: Bot, session: AsyncSession, user_id: int) -> None:
    # старые счета Stars отменяем, чтобы не висели в чате и не оплачивались дважды
    pending = list(
        (
            await session.scalars(
                select(Order).where(Order.user_id == user_id, Order.status == "pending")
            )
        ).all()
    )
    for order in pending:
        order.status = "cancelled"
        if order.invoice_message_id:
            try:
                await bot.delete_message(user_id, order.invoice_message_id)
            except Exception:
                pass


async def deliver_order(
    session: AsyncSession, order: Order, user: User
) -> tuple[str, InlineKeyboardMarkup]:
    order.status = "delivered"
    cashback = order.total * config.cashback_percent // 100
    user.bonus += cashback

    items = list(
        (await session.scalars(select(OrderItem).where(OrderItem.order_id == order.id))).all()
    )
    product_ids = [item.product_id for item in items]
    if product_ids:
        await session.execute(
            delete(CartItem).where(
                CartItem.user_id == user.id, CartItem.product_id.in_(product_ids)
            )
        )

    lines = "\n".join(
        f"▪️ {esc(item.title)} ×{item.qty} — {fmt_price(item.price * item.qty)}" for item in items
    )
    first_product = items[0].product_id if items else None

    text = (
        f"✅ <b>Заказ #{order.id} оплачен!</b>\n\n{lines}\n\n"
        f"💫 Начислено {cashback} бонусов (всего: {user.bonus})\n"
        "Спасибо за покупку в Nebula Shop!"
    )
    return text, review_kb(order.id, first_product)


async def send_delivery_message(
    bot: Bot, user_id: int, text: str, kb: InlineKeyboardMarkup
) -> None:
    try:
        await bot.send_message(user_id, text, reply_markup=kb)
    except Exception:
        logger.warning("Не удалось отправить уведомление о заказе пользователю %s", user_id)
