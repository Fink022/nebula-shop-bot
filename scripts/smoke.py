import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from main import build_dispatcher
from nebula.db.engine import Session
from nebula.db.models import CartItem, Category, Product, PromoCode, Review, User
from scripts.seed import seed


async def main() -> None:
    await seed()
    dp = build_dispatcher()

    async with Session() as session:
        counts = {
            "categories": len((await session.scalars(select(Category))).all()),
            "products": len((await session.scalars(select(Product))).all()),
            "promos": len((await session.scalars(select(PromoCode))).all()),
            "users": len((await session.scalars(select(User))).all()),
            "cart_items": len((await session.scalars(select(CartItem))).all()),
            "reviews": len((await session.scalars(select(Review))).all()),
        }

    print(f"OK | routers: {len(dp.sub_routers)} | {counts}")


if __name__ == "__main__":
    asyncio.run(main())
