import asyncio

from aiogram import F, Router
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from nebula.db.models import Category, Order, OrderItem, Product, PromoCode, User
from nebula.filters import AdminFilter, IsPrivate
from nebula.keyboards import (
    admin_cancel_kb,
    admin_categories_kb,
    admin_confirm_kb,
    admin_orders_kb,
    admin_panel_kb,
    admin_photo_kb,
    admin_products_kb,
    admin_promos_kb,
)
from nebula.utils import PAYMENT_RU, STATUS_RU, as_local, esc, fmt_price, render_screen

router = Router()
router.message.filter(AdminFilter(), IsPrivate())
router.callback_query.filter(AdminFilter(), IsPrivate())


class AddProduct(StatesGroup):
    title = State()
    description = State()
    price = State()
    category = State()
    photo = State()


class EditPrice(StatesGroup):
    waiting = State()


class AddPromo(StatesGroup):
    code = State()
    percent = State()
    max_uses = State()


class Broadcast(StatesGroup):
    waiting = State()
    confirm = State()


async def _stats_text(session: AsyncSession) -> str:
    users = await session.scalar(select(func.count(User.id)))
    orders = await session.scalar(select(func.count(Order.id)).where(Order.status == "delivered"))
    revenue = await session.scalar(
        select(func.coalesce(func.sum(Order.total), 0)).where(Order.status == "delivered")
    )
    top = (
        await session.execute(
            select(OrderItem.title, func.sum(OrderItem.qty).label("sold"))
            .group_by(OrderItem.title)
            .order_by(func.sum(OrderItem.qty).desc())
            .limit(3)
        )
    ).all()
    top_lines = (
        "\n".join(
            f"{index}. {esc(title)} — {int(sold)} шт" for index, (title, sold) in enumerate(top, 1)
        )
        or "—"
    )
    avg = revenue // orders if orders else 0
    return (
        "📊 <b>Статистика Nebula Shop</b>\n\n"
        f"👥 Пользователей: <b>{users}</b>\n"
        f"📦 Заказов: <b>{orders}</b>\n"
        f"💰 Выручка: <b>{fmt_price(revenue)}</b>\n"
        f"🧾 Средний чек: {fmt_price(avg)}\n\n"
        f"🔥 <b>Топ товаров:</b>\n{top_lines}"
    )


@router.callback_query(F.data == "admin:panel")
async def panel(call: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    await state.clear()
    await render_screen(call.message, await _stats_text(session), admin_panel_kb())
    await call.answer()


@router.callback_query(F.data == "admin:orders")
async def orders_list(call: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    await state.set_state(None)
    orders = list((await session.scalars(select(Order).order_by(Order.id.desc()).limit(8))).all())
    text = "📦 <b>Последние заказы</b>" if orders else "📦 Заказов пока нет"
    await render_screen(call.message, text, admin_orders_kb(orders))
    await call.answer()


@router.callback_query(F.data.startswith("admin:order:"))
async def order_details(call: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    await state.set_state(None)
    order = await session.get(Order, int(call.data.split(":")[2]))
    if not order:
        await call.answer("Заказ не найден", show_alert=True)
        return
    user = await session.get(User, order.user_id)
    items = list(
        (await session.scalars(select(OrderItem).where(OrderItem.order_id == order.id))).all()
    )
    lines = "\n".join(
        f"▪️ {esc(item.title)} ×{item.qty} — {fmt_price(item.price * item.qty)}" for item in items
    )
    username_display = f"@{esc(user.username)}" if user.username else "без юзернейма"
    text = (
        f"📦 <b>Заказ #{order.id}</b>\n\n"
        f"👤 {username_display} · ID <code>{user.id}</code>\n"
        f"💳 Оплата: {PAYMENT_RU.get(order.payment, order.payment)} · "
        f"статус: {STATUS_RU.get(order.status, order.status)}\n"
        f"📅 {as_local(order.created_at):%d.%m.%Y %H:%M}\n\n"
        f"{lines}\n\n💰 Итого: <b>{fmt_price(order.total)}</b>"
    )
    builder = InlineKeyboardBuilder()
    builder.button(text="⬅️ К заказам", callback_data="admin:orders")
    await render_screen(call.message, text, builder.as_markup())
    await call.answer()


@router.callback_query(F.data == "admin:products")
async def products_list(call: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    await state.set_state(None)
    products = list((await session.scalars(select(Product).order_by(Product.id))).all())
    text = "🛍 <b>Товары</b>\n\nНажми на товар, чтобы включить/выключить показ. ✏️ — изменить цену."
    await render_screen(call.message, text, admin_products_kb(products))
    await call.answer()


@router.callback_query(F.data.startswith("admin:toggle:"))
async def toggle_product(call: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    await state.set_state(None)
    product = await session.get(Product, int(call.data.split(":")[2]))
    if product:
        product.is_active = not product.is_active
    products = list((await session.scalars(select(Product).order_by(Product.id))).all())
    await render_screen(
        call.message,
        "🛍 <b>Товары</b>\n\nНажми на товар, чтобы включить/выключить показ. ✏️ — изменить цену.",
        admin_products_kb(products),
    )
    await call.answer("Обновлено")


@router.callback_query(F.data.startswith("admin:price:"))
async def edit_price(call: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    product = await session.get(Product, int(call.data.split(":")[2]))
    if not product:
        await call.answer("Товар не найден", show_alert=True)
        return
    await state.set_state(EditPrice.waiting)
    await state.update_data(product_id=product.id)
    await render_screen(
        call.message,
        f"✏️ Новая цена для <b>{esc(product.title)}</b>\n\nТекущая: {fmt_price(product.price)}\n"
        "Отправь число в рублях:",
        admin_cancel_kb(),
    )
    await call.answer()


@router.message(EditPrice.waiting, F.text)
async def save_price(message: Message, session: AsyncSession, state: FSMContext) -> None:
    try:
        price = int(message.text.replace(" ", ""))
    except ValueError:
        price = 0
    if price <= 0:
        await message.answer("⚠️ Нужно целое число больше нуля. Попробуй ещё раз:")
        return
    data = await state.get_data()
    product = await session.get(Product, data["product_id"])
    if not product:
        await state.clear()
        await message.answer("⚠️ Товар не найден — возможно, он был удалён.")
        return
    product.price = price
    await state.clear()
    products = list((await session.scalars(select(Product).order_by(Product.id))).all())
    await render_screen(
        message,
        "✅ Цена обновлена!\n\n🛍 <b>Товары</b>",
        admin_products_kb(products),
    )


@router.callback_query(F.data == "admin:addprod")
async def add_product_start(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AddProduct.title)
    await render_screen(
        call.message, "📝 <b>Новый товар</b>\n\nОтправь название:", admin_cancel_kb()
    )
    await call.answer()


@router.message(AddProduct.title, F.text)
async def add_product_title(message: Message, state: FSMContext) -> None:
    await state.update_data(title=message.text.strip()[:120])
    await state.set_state(AddProduct.description)
    await render_screen(message, "Отправь описание товара:", admin_cancel_kb())


@router.message(AddProduct.description, F.text)
async def add_product_description(message: Message, state: FSMContext) -> None:
    await state.update_data(description=message.text.strip()[:900])
    await state.set_state(AddProduct.price)
    await render_screen(message, "Отправь цену в рублях (только число):", admin_cancel_kb())


@router.message(AddProduct.price, F.text)
async def add_product_price(message: Message, session: AsyncSession, state: FSMContext) -> None:
    try:
        price = int(message.text.replace(" ", ""))
    except ValueError:
        price = 0
    if price <= 0:
        await message.answer("⚠️ Нужно целое число больше нуля. Попробуй ещё раз:")
        return
    await state.update_data(price=price)
    await state.set_state(AddProduct.category)
    categories = list((await session.scalars(select(Category).order_by(Category.id))).all())
    await render_screen(message, "Выбери категорию:", admin_categories_kb(categories))


@router.callback_query(StateFilter(AddProduct.category), F.data.startswith("admin:newcat:"))
async def add_product_category(call: CallbackQuery, state: FSMContext) -> None:
    category_id = int(call.data.split(":")[2])
    await state.update_data(category_id=category_id or None)
    await state.set_state(AddProduct.photo)
    await render_screen(
        call.message,
        "📸 Отправь фото товара или пропусти этот шаг:",
        admin_photo_kb(),
    )
    await call.answer()


@router.message(AddProduct.photo, F.photo)
async def add_product_photo(message: Message, session: AsyncSession, state: FSMContext) -> None:
    await _finish_product(message, session, state, message.photo[-1].file_id)


@router.callback_query(StateFilter(AddProduct.photo), F.data == "admin:skipphoto")
async def add_product_skip_photo(
    call: CallbackQuery, session: AsyncSession, state: FSMContext
) -> None:
    await _finish_product(call.message, session, state, "")


async def _finish_product(
    message: Message, session: AsyncSession, state: FSMContext, photo: str
) -> None:
    data = await state.get_data()
    if not data.get("title") or not data.get("price"):
        await state.clear()
        await render_screen(
            message, "⚠️ Не хватает данных — начни добавление заново.", admin_panel_kb()
        )
        return
    product = Product(
        title=data.get("title", "Без названия"),
        description=data.get("description", ""),
        price=data.get("price", 0),
        category_id=data.get("category_id"),
        photo=photo,
    )
    session.add(product)
    await state.clear()
    products = list((await session.scalars(select(Product).order_by(Product.id))).all())
    await render_screen(
        message,
        f"✅ Товар <b>{esc(product.title)}</b> добавлен!\n\n🛍 <b>Товары</b>",
        admin_products_kb(products),
    )


@router.callback_query(F.data == "admin:promos")
async def promos_list(call: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    await state.set_state(None)
    promos = list((await session.scalars(select(PromoCode).order_by(PromoCode.id))).all())
    text = "🎟 <b>Промокоды</b>\n\nНажми, чтобы вкл/выкл:"
    await render_screen(call.message, text, admin_promos_kb(promos))
    await call.answer()


@router.callback_query(F.data.startswith("admin:promotoggle:"))
async def toggle_promo(call: CallbackQuery, session: AsyncSession) -> None:
    promo = await session.get(PromoCode, int(call.data.split(":")[2]))
    if promo:
        promo.is_active = not promo.is_active
    promos = list((await session.scalars(select(PromoCode).order_by(PromoCode.id))).all())
    await render_screen(
        call.message, "🎟 <b>Промокоды</b>\n\nНажми, чтобы вкл/выкл:", admin_promos_kb(promos)
    )
    await call.answer("Обновлено")


@router.callback_query(F.data == "admin:addpromo")
async def add_promo_start(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AddPromo.code)
    await render_screen(call.message, "🎟 <b>Новый промокод</b>\n\nОтправь код:", admin_cancel_kb())
    await call.answer()


@router.message(AddPromo.code, F.text)
async def add_promo_code(message: Message, state: FSMContext) -> None:
    await state.update_data(code=message.text.strip().upper()[:32])
    await state.set_state(AddPromo.percent)
    await render_screen(message, "Скидка в % (число от 1 до 90):", admin_cancel_kb())


@router.message(AddPromo.percent, F.text)
async def add_promo_percent(message: Message, state: FSMContext) -> None:
    try:
        percent = int(message.text.strip())
    except ValueError:
        percent = 0
    if not 1 <= percent <= 90:
        await message.answer("⚠️ Нужно число от 1 до 90. Попробуй ещё раз:")
        return
    await state.update_data(percent=percent)
    await state.set_state(AddPromo.max_uses)
    await render_screen(
        message, "Сколько раз можно использовать промокод? (число)", admin_cancel_kb()
    )


@router.message(AddPromo.max_uses, F.text)
async def add_promo_max_uses(message: Message, session: AsyncSession, state: FSMContext) -> None:
    try:
        max_uses = int(message.text.strip())
    except ValueError:
        max_uses = 0
    if max_uses <= 0:
        await message.answer("⚠️ Нужно целое число больше нуля. Попробуй ещё раз:")
        return
    data = await state.get_data()
    existing = await session.scalar(select(PromoCode).where(PromoCode.code == data["code"]))
    await state.clear()
    if existing:
        promos = list((await session.scalars(select(PromoCode).order_by(PromoCode.id))).all())
        await render_screen(
            message,
            f"⚠️ Промокод <b>{esc(data['code'])}</b> уже существует.\n\n🎟 <b>Промокоды</b>",
            admin_promos_kb(promos),
        )
        return
    session.add(PromoCode(code=data["code"], discount=data["percent"], max_uses=max_uses))
    await session.flush()
    promos = list((await session.scalars(select(PromoCode).order_by(PromoCode.id))).all())
    await render_screen(
        message,
        f"✅ Промокод <b>{esc(data['code'])}</b> создан!\n\n🎟 <b>Промокоды</b>",
        admin_promos_kb(promos),
    )


@router.callback_query(F.data == "admin:broadcast")
async def broadcast_start(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(Broadcast.waiting)
    await render_screen(
        call.message,
        "📣 <b>Рассылка</b>\n\nОтправь сообщение, которое нужно разослать "
        "всем пользователям (текст, фото, видео — что угодно):",
        admin_cancel_kb(),
    )
    await call.answer()


@router.message(Broadcast.waiting, ~F.text.startswith("/"))
async def broadcast_preview(message: Message, session: AsyncSession, state: FSMContext) -> None:
    total = await session.scalar(select(func.count(User.id)))
    await state.update_data(bc_chat=message.chat.id, bc_msg=message.message_id)
    await state.set_state(Broadcast.confirm)
    await render_screen(
        message,
        f"📣 Отправить это сообщение <b>{total}</b> пользователям?",
        admin_confirm_kb(),
    )


@router.callback_query(F.data == "admin:bc:send")
async def broadcast_send(call: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    data = await state.get_data()
    if "bc_msg" not in data:
        await call.answer("Нет сообщения для рассылки", show_alert=True)
        return
    await call.answer("📣 Рассылка запущена")

    user_ids = list((await session.scalars(select(User.id))).all())
    total = len(user_ids)
    sent = blocked = failed = 0

    for index, user_id in enumerate(user_ids, start=1):
        try:
            await _copy_broadcast(call.bot, user_id, data)
            sent += 1
        except TelegramRetryAfter as error:
            await asyncio.sleep(error.retry_after + 1)
            try:
                await _copy_broadcast(call.bot, user_id, data)
                sent += 1
            except TelegramForbiddenError:
                blocked += 1
            except Exception:
                failed += 1
        except TelegramForbiddenError:
            blocked += 1
        except Exception:
            failed += 1

        if index % 25 == 0:
            try:
                await call.message.edit_text(f"📣 Рассылка… {index}/{total}")
            except Exception:
                pass
        await asyncio.sleep(0.05)

    await state.clear()
    await render_screen(
        call.message,
        "📣 <b>Рассылка завершена</b>\n\n"
        f"✅ Доставлено: {sent}\n"
        f"🚫 Заблокировали бота: {blocked}\n"
        f"❌ Ошибок: {failed}",
        admin_panel_kb(),
    )


async def _copy_broadcast(bot, user_id: int, data: dict) -> None:
    await bot.copy_message(
        chat_id=user_id,
        from_chat_id=data["bc_chat"],
        message_id=data["bc_msg"],
    )


@router.callback_query(F.data == "admin:bc:cancel")
async def broadcast_cancel(call: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    await state.clear()
    await render_screen(call.message, await _stats_text(session), admin_panel_kb())
    await call.answer("Отменено")
