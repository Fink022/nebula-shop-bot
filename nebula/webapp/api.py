import logging
from functools import wraps
from types import SimpleNamespace

from aiogram.types import LabeledPrice
from aiohttp import web
from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from nebula.config import config
from nebula.db.engine import Session
from nebula.db.models import CartItem, Category, Order, Product, User
from nebula.services.orders import (
    cancel_pending_orders,
    consume_promo,
    create_order,
    deliver_order,
    send_delivery_message,
    valid_promo,
)
from nebula.utils import as_local, cart_totals, get_cart_rows, get_or_create_user, user_lock
from nebula.webapp.auth import authenticate

logger = logging.getLogger(__name__)

routes = web.RouteTableDef()


def authed(handler):
    @wraps(handler)
    async def wrapper(request: web.Request) -> web.Response:
        user = await authenticate(request)
        if not user:
            raise web.HTTPUnauthorized(text="Invalid Telegram auth")
        request["tg_user"] = user
        return await handler(request)

    return wrapper


def _as_tg_user(tg_user: dict) -> SimpleNamespace:
    return SimpleNamespace(
        id=tg_user["id"],
        username=tg_user.get("username"),
        first_name=tg_user.get("first_name") or "",
    )


def _photo_url(product: Product) -> str | None:
    photo = product.photo
    if not photo:
        return None
    if photo.startswith("assets/"):
        return "/" + photo[len("assets/") :]
    return f"/photo/{product.id}"


def _cart_payload(rows) -> list[dict]:
    return [
        {
            "item_id": item.id,
            "product_id": product.id,
            "title": product.title,
            "price": product.price,
            "qty": item.qty,
            "photo": _photo_url(product),
        }
        for item, product in rows
    ]


async def _json_body(request: web.Request) -> dict | None:
    try:
        data = await request.json()
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _bad_request(message: str) -> web.Response:
    return web.json_response({"error": message}, status=400)


@routes.get("/api/catalog")
@authed
async def catalog(request: web.Request) -> web.Response:
    async with Session() as session:
        categories = list((await session.scalars(select(Category).order_by(Category.id))).all())
        products = list(
            (
                await session.scalars(select(Product).where(Product.is_active).order_by(Product.id))
            ).all()
        )
    return web.json_response(
        {
            "categories": [
                {"id": category.id, "title": category.title, "emoji": category.emoji}
                for category in categories
            ],
            "products": [
                {
                    "id": product.id,
                    "category_id": product.category_id,
                    "title": product.title,
                    "description": product.description,
                    "price": product.price,
                    "photo": _photo_url(product),
                }
                for product in products
            ],
        }
    )


@routes.get("/api/state")
@authed
async def state(request: web.Request) -> web.Response:
    async with Session() as session:
        user = await get_or_create_user(session, _as_tg_user(request["tg_user"]))
        rows = await get_cart_rows(session, user.id)
        orders = list(
            (
                await session.scalars(
                    select(Order).where(Order.user_id == user.id).order_by(Order.id.desc()).limit(6)
                )
            ).all()
        )
        invited = await session.scalar(
            select(func.count(User.id)).where(User.referred_by == user.id)
        )
        orders_count = await session.scalar(
            select(func.count(Order.id)).where(Order.user_id == user.id)
        )
        spent = await session.scalar(
            select(func.coalesce(func.sum(Order.total), 0)).where(
                Order.user_id == user.id, Order.status == "delivered"
            )
        )
        await session.commit()
        payload = {
            "user": {
                "id": user.id,
                "first_name": user.first_name,
                "bonus": user.bonus,
                "invited": invited or 0,
            },
            "bot_username": config.bot_username,
            "stars_rate": config.stars_rate,
            "cashback_percent": config.cashback_percent,
            "referral_bonus_inviter": config.referral_bonus_inviter,
            "referral_bonus_newbie": config.referral_bonus_newbie,
            "spent": spent or 0,
            "orders_count": orders_count or 0,
            "cart": _cart_payload(rows),
            "orders": [
                {
                    "id": order.id,
                    "total": order.total,
                    "status": order.status,
                    "date": as_local(order.created_at).strftime("%d.%m.%Y"),
                }
                for order in orders
            ],
        }
    return web.json_response(payload)


@routes.post("/api/cart")
@authed
async def cart(request: web.Request) -> web.Response:
    body = await _json_body(request)
    if body is None:
        return _bad_request("Некорректный JSON")
    action = body.get("action")
    async with Session() as session:
        user = await get_or_create_user(session, _as_tg_user(request["tg_user"]))
        if action == "add":
            try:
                product_id = int(body.get("product_id"))
            except (TypeError, ValueError):
                return _bad_request("Некорректный товар")
            product = await session.get(Product, product_id)
            if not product or not product.is_active:
                return _bad_request("Товар недоступен")
            stmt = (
                sqlite_insert(CartItem)
                .values(user_id=user.id, product_id=product.id, qty=1)
                .on_conflict_do_update(
                    index_elements=[CartItem.user_id, CartItem.product_id],
                    set_={"qty": func.min(CartItem.qty + 1, 99)},
                )
            )
            await session.execute(stmt)
        elif action == "set":
            try:
                item_id = int(body.get("item_id"))
                qty = int(body.get("qty", 1))
            except (TypeError, ValueError):
                return _bad_request("Некорректное количество")
            item = await session.get(CartItem, item_id)
            if item and item.user_id == user.id:
                if qty <= 0:
                    await session.delete(item)
                else:
                    item.qty = min(qty, 99)
        elif action == "clear":
            await session.execute(delete(CartItem).where(CartItem.user_id == user.id))
        else:
            return _bad_request("Неизвестное действие")

        await session.commit()
        rows = await get_cart_rows(session, user.id)
        payload = _cart_payload(rows)
    return web.json_response({"items": payload})


@routes.post("/api/promo")
@authed
async def promo(request: web.Request) -> web.Response:
    body = await _json_body(request)
    if body is None:
        return _bad_request("Некорректный JSON")
    async with Session() as session:
        found = await valid_promo(session, str(body.get("code") or "").strip())
    return web.json_response(
        {"valid": found is not None, "discount": found.discount if found else 0}
    )


@routes.post("/api/checkout")
@authed
async def checkout(request: web.Request) -> web.Response:
    bot = request.app["bot"]
    body = await _json_body(request)
    if body is None:
        return _bad_request("Некорректный JSON")
    method = body.get("method")
    promo_code = str(body.get("promo") or "").strip()
    if method not in ("stars", "bonus"):
        return _bad_request("Неизвестный способ оплаты")
    user_id = int(request["tg_user"]["id"])

    async with user_lock(user_id), Session() as session:
        user = await get_or_create_user(session, _as_tg_user(request["tg_user"]))
        rows = await get_cart_rows(session, user.id)
        if not rows:
            return _bad_request("Корзина пуста")

        found_promo = await valid_promo(session, promo_code)
        discount_percent = found_promo.discount if found_promo else 0
        subtotal, discount = cart_totals(rows, discount_percent)
        total = subtotal - discount

        if method == "bonus" and user.bonus < total:
            return _bad_request("Недостаточно бонусов")

        await cancel_pending_orders(bot, session, user.id)

        if method == "stars":
            order = await create_order(
                session, user, rows, total, discount, promo_code, payment="stars", status="pending"
            )
            await session.commit()
            stars = max(1, round(total * config.stars_rate))
            try:
                invoice = await bot.send_invoice(
                    chat_id=user.id,
                    title=f"Заказ #{order.id} · Nebula Shop",
                    description=(
                        f"Оплата {sum(item.qty for item, _ in rows)} товаров из мини-приложения"
                    ),
                    payload=f"order:{order.id}",
                    provider_token="",
                    currency="XTR",
                    prices=[LabeledPrice(label=f"Заказ #{order.id}", amount=stars)],
                )
            except Exception:
                logger.exception("Не удалось выставить счёт для заказа %s", order.id)
                order.status = "cancelled"
                await session.commit()
                return _bad_request("Не удалось выставить счёт. Попробуй ещё раз")
            order.invoice_message_id = invoice.message_id
            await session.commit()
            return web.json_response(
                {
                    "ok": True,
                    "order_id": order.id,
                    "message": f"Счёт на {stars} ⭐ отправлен в чат с ботом",
                }
            )

        result = await session.execute(
            update(User)
            .where(User.id == user.id, User.bonus >= total)
            .values(bonus=User.bonus - total)
        )
        if result.rowcount == 0:
            return _bad_request("Недостаточно бонусов")
        await session.refresh(user)
        order = await create_order(
            session, user, rows, total, discount, promo_code, payment="bonus", status="paid"
        )
        if found_promo:
            await consume_promo(session, found_promo.code)
        text, kb = await deliver_order(session, order, user)
        await session.commit()
        await send_delivery_message(bot, user.id, text, kb)
        return web.json_response(
            {"ok": True, "order_id": order.id, "message": "Заказ оплачен бонусами 💠"}
        )
