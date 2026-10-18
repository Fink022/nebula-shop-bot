import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from nebula.config import config
from nebula.db.engine import Session, init_db
from nebula.db.models import Order, OrderItem, Product, PromoCode, Review, User


async def seed_activity(user_id: int) -> None:
    await init_db()
    async with Session() as session:
        user = await session.get(User, user_id)
        if user is None:
            user = User(id=user_id, username="demo_user", first_name="Иван")
            session.add(user)

        products = {
            product.title: product for product in (await session.scalars(select(Product))).all()
        }
        required = {"Nebula Watch S2", "AirPods Nebula Pro", "Nebula Charge 20K"}
        if not required.issubset(products):
            print("Каталог пуст. Сначала выполни: python scripts/seed.py")
            return

        watch = products["Nebula Watch S2"]
        buds = products["AirPods Nebula Pro"]
        powerbank = products["Nebula Charge 20K"]

        promo_discount = watch.price * 10 // 100
        first_total = watch.price - promo_discount
        second_total = buds.price + powerbank.price
        bonus = (first_total + second_total) * config.cashback_percent // 100

        now = datetime.now(timezone.utc).replace(tzinfo=None)

        first = Order(
            user_id=user.id,
            total=first_total,
            discount=promo_discount,
            promo="NEBULA10",
            payment="stars",
            status="delivered",
            created_at=now - timedelta(days=6),
        )
        session.add(first)
        await session.flush()
        session.add(
            OrderItem(
                order_id=first.id,
                product_id=watch.id,
                title=watch.title,
                price=watch.price,
                qty=1,
            )
        )

        second = Order(
            user_id=user.id,
            total=second_total,
            payment="bonus",
            status="delivered",
            created_at=now - timedelta(days=2),
        )
        session.add(second)
        await session.flush()
        session.add_all(
            [
                OrderItem(
                    order_id=second.id,
                    product_id=buds.id,
                    title=buds.title,
                    price=buds.price,
                    qty=1,
                ),
                OrderItem(
                    order_id=second.id,
                    product_id=powerbank.id,
                    title=powerbank.title,
                    price=powerbank.price,
                    qty=1,
                ),
            ]
        )

        promo = await session.scalar(select(PromoCode).where(PromoCode.code == "NEBULA10"))
        if promo:
            promo.used += 1

        session.add_all(
            [
                Review(
                    user_id=user.id,
                    product_id=watch.id,
                    order_id=first.id,
                    rating=5,
                    text="заказал вечером, утром уже всё было. часы классные, неделю точно держат",
                    created_at=now - timedelta(days=5),
                ),
                Review(
                    user_id=user.id,
                    product_id=buds.id,
                    order_id=second.id,
                    rating=4,
                    text="Наушники норм, бас на месте. Шумодав средний, за эти деньги ок. Кейс поцарапался за неделю",
                    created_at=now - timedelta(days=1),
                ),
            ]
        )

        user.bonus = bonus
        await session.commit()
        print(f"OK | Демо-история для {user_id}: 2 заказа, 2 отзыва, бонусов {bonus}")


if __name__ == "__main__":
    target = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    if not target:
        print("Использование: python scripts/seed_activity.py <telegram_user_id>")
        raise SystemExit(1)
    asyncio.run(seed_activity(target))
