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
                    description=(
                        "AMOLED-экран, пульсометр, GPS. Держат заряд до двух недель, "
                        "на руке почти не чувствуются."
                    ),
                    price=4990,
                    photo="assets/products/p0.png",
                ),
                Product(
                    category_id=audio.id,
                    title="AirPods Nebula Pro",
                    description="Активный шумодав и плотный бас. Кейс держит заряд до 30 часов.",
                    price=7490,
                    photo="assets/products/p1.png",
                ),
                Product(
                    category_id=projectors.id,
                    title="Nebula Beam Mini",
                    description=(
                        "Кинотеатр 120 дюймов на любой стене: Wi-Fi, автофокус, HDMI. "
                        "От аккумулятора — около трёх часов."
                    ),
                    price=15990,
                    photo="assets/products/p2.png",
                ),
                Product(
                    category_id=audio.id,
                    title="Nebula Sound 360",
                    description="Звук 360°, защита IPX7, подсветка. Играет громко, дождя не боится.",
                    price=3990,
                    photo="assets/products/p3.png",
                ),
                Product(
                    category_id=accessories.id,
                    title="Nebula Charge 20K",
                    description="20 000 мАч, быстрая зарядка 65 Вт, дисплей. Ноутбук тоже тянет.",
                    price=2990,
                    photo="assets/products/p4.png",
                ),
                Product(
                    category_id=accessories.id,
                    title="Nebula Keys RGB",
                    description=(
                        "Механика, RGB, hot-swap, Bluetooth и 2.4G. Печатать удобно, "
                        "но подсветку на ночь лучше выключать."
                    ),
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
