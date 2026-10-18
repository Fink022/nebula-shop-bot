import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import FSInputFile
from sqlalchemy import func, select

from nebula.config import config
from nebula.db.engine import Session
from nebula.db.models import Category, Order, OrderItem, Product, Review, User
from nebula.handlers.admin import _stats_text
from nebula.handlers.start import WELCOME
from nebula.keyboards import (
    admin_panel_kb,
    ai_answer_kb,
    back_menu_kb,
    cart_kb,
    categories_kb,
    checkout_kb,
    main_menu_kb,
    product_kb,
    review_kb,
)
from nebula.services.ai import consult
from nebula.utils import cart_totals, esc, fmt_price, get_cart_rows, product_caption

SCREENS = (
    "welcome",
    "categories",
    "product",
    "cart",
    "checkout",
    "ai",
    "delivered",
    "admin",
    "reviews",
)


def _chat_id() -> int:
    if len(sys.argv) > 2:
        return int(sys.argv[2])
    if config.admin_ids:
        return config.admin_ids[0]
    raise SystemExit("Укажи получателя: python scripts/demo_screens.py <screen> <chat_id>")


async def send(screen: str, chat_id: int) -> None:
    bot = Bot(config.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    async with Session() as session:
        if screen == "welcome":
            await bot.send_photo(
                chat_id,
                FSInputFile(PROJECT_ROOT / "assets" / "banner.png"),
                caption=WELCOME,
                reply_markup=main_menu_kb(is_admin=True),
            )
        elif screen == "categories":
            cats = list((await session.scalars(select(Category).order_by(Category.id))).all())
            count = await session.scalar(
                select(func.count()).select_from(Product).where(Product.is_active)
            )
            await bot.send_message(
                chat_id,
                f"🛍 <b>Каталог Nebula Shop</b>\n\nВ наличии <b>{count}</b> позиций. "
                "Выбери категорию или смотри всё подряд:",
                reply_markup=categories_kb(cats),
            )
        elif screen == "product":
            products = list(
                (
                    await session.scalars(
                        select(Product).where(Product.is_active).order_by(Product.id)
                    )
                ).all()
            )
            if not products:
                raise SystemExit("Нет активных товаров — сначала: python scripts/seed.py")
            product = products[0]
            await bot.send_photo(
                chat_id,
                FSInputFile(PROJECT_ROOT / product.photo),
                caption=product_caption(product, 1, len(products)),
                reply_markup=product_kb(product.id, 0, 0, len(products)),
            )
        elif screen == "cart":
            rows = await get_cart_rows(session, chat_id)
            subtotal, _ = cart_totals(rows)
            lines = ["🛒 <b>Твоя корзина</b>\n"]
            for item, product in rows:
                lines.append(
                    f"▪️ {product.title} ×{item.qty} — {fmt_price(item.qty * product.price)}"
                )
            lines.append("")
            lines.append(f"💰 Итого: <b>{fmt_price(subtotal)}</b>")
            await bot.send_message(chat_id, "\n".join(lines), reply_markup=cart_kb(rows, subtotal))
        elif screen == "checkout":
            rows = await get_cart_rows(session, chat_id)
            subtotal, _ = cart_totals(rows)
            user = await session.get(User, chat_id)
            bonus = user.bonus if user else 0
            text = (
                "🧾 <b>Оформление заказа</b>\n\n"
                f"Товаров: {sum(item.qty for item, _ in rows)} шт на {fmt_price(subtotal)}\n\n"
                f"💰 <b>К оплате: {fmt_price(subtotal)}</b>\n"
                f"⭐ Можно оплатить звёздами: {subtotal} ⭐ (1:1)\n"
                f"💠 У тебя {bonus} бонусов"
            )
            await bot.send_message(
                chat_id, text, reply_markup=checkout_kb(subtotal, bonus >= subtotal)
            )
        elif screen == "ai":
            answer, product = await consult(
                session, "Хочу подарок девушке до 5000, что-нибудь стильное"
            )
            index = None
            if product:
                products = list(
                    (
                        await session.scalars(
                            select(Product).where(Product.is_active).order_by(Product.id)
                        )
                    ).all()
                )
                ids = [item.id for item in products]
                if product.id in ids:
                    index = ids.index(product.id)
            await bot.send_message(
                chat_id, answer, reply_markup=ai_answer_kb(index), parse_mode=None
            )
        elif screen == "delivered":
            order = await session.scalar(
                select(Order).where(Order.status == "delivered").order_by(Order.id.desc())
            )
            if order is None:
                raise SystemExit(
                    "Нет выполненных заказов. Сначала: python scripts/seed_activity.py <chat_id>"
                )
            items = list(
                (
                    await session.scalars(select(OrderItem).where(OrderItem.order_id == order.id))
                ).all()
            )
            lines = "\n".join(
                f"▪️ {item.title} ×{item.qty} — {fmt_price(item.price * item.qty)}" for item in items
            )
            user = await session.get(User, chat_id)
            cashback = order.total * config.cashback_percent // 100
            bonus = user.bonus if user else 0
            text = (
                f"✅ <b>Заказ #{order.id} оплачен!</b>\n\n{lines}\n\n"
                f"💫 Начислено {cashback} бонусов (всего: {bonus})\n"
                "Спасибо за покупку в Nebula Shop!"
            )
            await bot.send_message(
                chat_id,
                text,
                reply_markup=review_kb(order.id, items[0].product_id if items else None),
            )
        elif screen == "admin":
            await bot.send_message(
                chat_id, await _stats_text(session), reply_markup=admin_panel_kb()
            )
        elif screen == "reviews":
            rows = (
                await session.execute(
                    select(Review, Product.title)
                    .outerjoin(Product, Review.product_id == Product.id)
                    .order_by(Review.id.desc())
                    .limit(5)
                )
            ).all()
            blocks = ["⭐ <b>Отзывы покупателей</b>\n"]
            for review, title in rows:
                blocks.append(
                    f"{'⭐' * review.rating} · <b>{esc(title) or 'Nebula Shop'}</b>\n"
                    f"{esc(review.text[:400]) or 'без комментария'}"
                )
            await bot.send_message(chat_id, "\n\n".join(blocks), reply_markup=back_menu_kb())
        else:
            raise SystemExit(f"Неизвестный экран: {screen}. Доступные: {', '.join(SCREENS)}")

    await bot.session.close()
    print(f"sent: {screen}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(
            f"Использование: python scripts/demo_screens.py <screen> [chat_id]\n"
            f"Экраны: {', '.join(SCREENS)}"
        )
    asyncio.run(send(sys.argv[1], _chat_id()))
