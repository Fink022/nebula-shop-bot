from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder

from nebula.config import config
from nebula.db.models import Category, Product
from nebula.utils import STATUS_RU


def main_menu_kb(is_admin: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if config.webapp_url:
        builder.row(
            InlineKeyboardButton(
                text="🛍 Открыть магазин", web_app=WebAppInfo(url=config.webapp_url)
            )
        )
    builder.button(text="🛍 Каталог", callback_data="menu:catalog")
    builder.button(text="🛒 Корзина", callback_data="menu:cart")
    builder.button(text="✨ ИИ-консультант", callback_data="menu:ai")
    builder.button(text="👤 Профиль", callback_data="menu:profile")
    builder.button(text="⭐ Отзывы", callback_data="menu:reviews")
    builder.button(text="🎁 Пригласить друга", callback_data="menu:ref")
    builder.adjust(2, 2, 2)
    if is_admin:
        builder.row(InlineKeyboardButton(text="🛠 Админ-панель", callback_data="admin:panel"))
    return builder.as_markup()


def back_menu_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="⬅️ В меню", callback_data="menu:main")
    return builder.as_markup()


def categories_kb(categories: list[Category]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for category in categories:
        builder.button(
            text=f"{category.emoji} {category.title}", callback_data=f"cat:{category.id}:0"
        )
    builder.adjust(2)
    builder.row(InlineKeyboardButton(text="🛍 Все товары", callback_data="cat:0:0"))
    builder.row(InlineKeyboardButton(text="⬅️ В меню", callback_data="menu:main"))
    return builder.as_markup()


def product_kb(product_id: int, cat_id: int, index: int, total: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="➕ В корзину", callback_data=f"add:{product_id}"),
        InlineKeyboardButton(text="🤖 Спросить ИИ", callback_data="menu:ai"),
    )
    nav = [
        InlineKeyboardButton(text="⬅️", callback_data=f"cat:{cat_id}:{max(0, index - 1)}"),
        InlineKeyboardButton(text=f"{index + 1}/{total}", callback_data="noop"),
        InlineKeyboardButton(text="➡️", callback_data=f"cat:{cat_id}:{min(total - 1, index + 1)}"),
    ]
    builder.row(*nav)
    builder.row(InlineKeyboardButton(text="⬅️ К категориям", callback_data="menu:catalog"))
    return builder.as_markup()


def cart_kb(rows, total: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for item, _product in rows:
        builder.row(
            InlineKeyboardButton(text="➖", callback_data=f"cart:dec:{item.id}"),
            InlineKeyboardButton(text=f"🗑 {item.qty} шт", callback_data=f"cart:del:{item.id}"),
            InlineKeyboardButton(text="➕", callback_data=f"cart:inc:{item.id}"),
        )
    builder.row(
        InlineKeyboardButton(text="🎟 Промокод", callback_data="cart:promo"),
        InlineKeyboardButton(text="🧹 Очистить", callback_data="cart:clear"),
    )
    builder.row(InlineKeyboardButton(text=f"✅ Оформить · {total} ₽", callback_data="checkout"))
    builder.row(InlineKeyboardButton(text="🛍 В каталог", callback_data="menu:catalog"))
    return builder.as_markup()


def empty_cart_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🛍 В каталог", callback_data="menu:catalog"))
    builder.row(InlineKeyboardButton(text="⬅️ В меню", callback_data="menu:main"))
    return builder.as_markup()


def checkout_kb(total: int, can_pay_bonus: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=f"⭐ Оплатить {total} ⭐", callback_data="pay:stars"))
    if can_pay_bonus:
        builder.row(InlineKeyboardButton(text="💠 Оплатить бонусами", callback_data="pay:bonus"))
    builder.row(
        InlineKeyboardButton(text="⬅️ В корзину", callback_data="menu:cart"),
        InlineKeyboardButton(text="⬅️ В меню", callback_data="menu:main"),
    )
    return builder.as_markup()


def review_kb(order_id: int, product_id: int | None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="⭐ Оценить заказ", callback_data=f"review:{order_id}:{product_id or 0}")
    return builder.as_markup()


def rating_kb(order_id: int, product_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for score in range(1, 6):
        builder.button(text="⭐" * score, callback_data=f"rate:{order_id}:{product_id}:{score}")
    builder.adjust(1)
    return builder.as_markup()


def review_text_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="⏭ Пропустить", callback_data="revskip")
    return builder.as_markup()


def profile_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="📦 Мои заказы", callback_data="my:orders"))
    builder.row(InlineKeyboardButton(text="⬅️ В меню", callback_data="menu:main"))
    return builder.as_markup()


def referral_kb(link: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="📤 Поделиться ссылкой",
            url=f"https://t.me/share/url?url={link}&text=Смотри, какой магазин нашёл!",
        )
    )
    builder.row(InlineKeyboardButton(text="⬅️ В меню", callback_data="menu:main"))
    return builder.as_markup()


def ai_chat_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="⬅️ Выйти", callback_data="menu:main")
    return builder.as_markup()


def ai_answer_kb(product_index: int | None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if product_index is not None:
        builder.row(
            InlineKeyboardButton(text="🛍 Открыть товар", callback_data=f"cat:0:{product_index}")
        )
    builder.row(InlineKeyboardButton(text="⬅️ В меню", callback_data="menu:main"))
    return builder.as_markup()


def admin_panel_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📊 Обновить", callback_data="admin:panel")
    builder.button(text="📦 Заказы", callback_data="admin:orders")
    builder.button(text="🛍 Товары", callback_data="admin:products")
    builder.button(text="🎟 Промокоды", callback_data="admin:promos")
    builder.button(text="📣 Рассылка", callback_data="admin:broadcast")
    builder.button(text="⬅️ В меню", callback_data="menu:main")
    builder.adjust(1, 2, 2, 1)
    return builder.as_markup()


def admin_products_kb(products: list[Product]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for product in products:
        status = "🟢" if product.is_active else "⚪"
        # в тексте кнопки лимит Telegram 64 символа — длинные названия обрезаем
        title = product.title if len(product.title) <= 30 else product.title[:29] + "…"
        builder.row(
            InlineKeyboardButton(
                text=f"{status} {title} · {product.price} ₽",
                callback_data=f"admin:toggle:{product.id}",
            ),
            InlineKeyboardButton(text="✏️ цена", callback_data=f"admin:price:{product.id}"),
        )
    builder.row(InlineKeyboardButton(text="➕ Добавить товар", callback_data="admin:addprod"))
    builder.row(InlineKeyboardButton(text="⬅️ Админ-панель", callback_data="admin:panel"))
    return builder.as_markup()


def admin_promos_kb(promos) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for promo in promos:
        builder.row(
            InlineKeyboardButton(
                text=f"🎟 {promo.code} · −{promo.discount}% · {promo.used}/{promo.max_uses}",
                callback_data=f"admin:promotoggle:{promo.id}",
            )
        )
    builder.row(InlineKeyboardButton(text="➕ Новый промокод", callback_data="admin:addpromo"))
    builder.row(InlineKeyboardButton(text="⬅️ Админ-панель", callback_data="admin:panel"))
    return builder.as_markup()


def admin_orders_kb(orders) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for order in orders:
        status = STATUS_RU.get(order.status, order.status)
        builder.row(
            InlineKeyboardButton(
                text=f"#{order.id} · {order.total} ₽ · {status}",
                callback_data=f"admin:order:{order.id}",
            )
        )
    builder.row(InlineKeyboardButton(text="⬅️ Админ-панель", callback_data="admin:panel"))
    return builder.as_markup()


def admin_cancel_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Отмена", callback_data="admin:panel")
    return builder.as_markup()


def admin_categories_kb(categories: list[Category]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for category in categories:
        builder.button(
            text=f"{category.emoji} {category.title}", callback_data=f"admin:newcat:{category.id}"
        )
    builder.adjust(2)
    builder.row(InlineKeyboardButton(text="⏭ Без категории", callback_data="admin:newcat:0"))
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="admin:panel"))
    return builder.as_markup()


def admin_photo_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="⏭ Пропустить фото", callback_data="admin:skipphoto")
    builder.button(text="❌ Отмена", callback_data="admin:panel")
    builder.adjust(1)
    return builder.as_markup()


def admin_confirm_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Отправить", callback_data="admin:bc:send"),
        InlineKeyboardButton(text="❌ Отмена", callback_data="admin:bc:cancel"),
    )
    return builder.as_markup()
