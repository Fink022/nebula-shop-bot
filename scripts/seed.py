import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func, select

from nebula.db.engine import Session, init_db
from nebula.db.models import Category, Product, PromoCode


async def seed() -> None:
    await init_db()
    async with Session() as session:
        if await session.scalar(select(func.count(Category.id))):
            print("База уже заполнена — пропускаю")
            return

        gadgets = Category(title="Гаджеты", emoji="⌚️")
        audio = Category(title="Аудио", emoji="🎧")
        projectors = Category(title="Проекторы", emoji="📽")
        accessories = Category(title="Аксессуары", emoji="🔌")
        session.add_all([gadgets, audio, projectors, accessories])
        await session.flush()

        session.add_all(
            [
                Product(
                    category_id=gadgets.id,
                    title="Nebula Watch S2",
                    description="AMOLED, пульсометр, GPS, шагомер. До 14 дней автономности, 5 ATM.",
                    price=4990,
                    photo="assets/products/p0.png",
                ),
                Product(
                    category_id=audio.id,
                    title="AirPods Nebula Pro",
                    description="Активный шумодав, плотный бас, до 30 часов с кейсом. Зарядка беспроводная.",
                    price=7490,
                    photo="assets/products/p1.png",
                ),
                Product(
                    category_id=projectors.id,
                    title="Nebula Beam Mini",
                    description="1080p, картинка до 120 дюймов, Wi-Fi, HDMI, автофокус. Три часа от аккумулятора.",
                    price=15990,
                    photo="assets/products/p2.png",
                ),
                Product(
                    category_id=audio.id,
                    title="Nebula Sound 360",
                    description="30 Вт, звук 360°, IPX7. Подсветка мигает под музыку.",
                    price=3990,
                    photo="assets/products/p3.png",
                ),
                Product(
                    category_id=accessories.id,
                    title="Nebula Charge 20K",
                    description="20 000 мАч и 65 Вт — хватает на два дня поездки, ноутбук тоже зарядит.",
                    price=2990,
                    photo="assets/products/p4.png",
                ),
                Product(
                    category_id=accessories.id,
                    title="Nebula Keys RGB",
                    description="Механика, hot-swap, Bluetooth и 2.4 ГГц. Красные свитчи, ход тихий — соседи не проснутся.",
                    price=5990,
                    photo="assets/products/p5.png",
                ),
            ]
        )
        session.add_all(
            [
                PromoCode(code="NEBULA10", discount=10, max_uses=100),
                PromoCode(code="WELCOME5", discount=5, max_uses=50),
            ]
        )
        await session.commit()
        print("OK | База заполнена: 4 категории, 6 товаров, 2 промокода")


if __name__ == "__main__":
    asyncio.run(seed())
