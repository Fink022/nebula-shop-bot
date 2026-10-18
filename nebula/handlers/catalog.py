from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from sqlalchemy import func, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from nebula.db.models import CartItem, Category, Product
from nebula.filters import IsPrivate
from nebula.keyboards import categories_kb, product_kb
from nebula.utils import photo_source, product_caption, render_screen

router = Router()
router.callback_query.filter(IsPrivate())


@router.callback_query(F.data == "noop")
async def noop(call: CallbackQuery) -> None:
    await call.answer()


@router.callback_query(F.data.startswith("cat:"))
async def show_product(call: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    await state.set_state(None)
    _, raw_cat, raw_idx = call.data.split(":")
    cat_id, idx = int(raw_cat), int(raw_idx)

    query = select(Product).where(Product.is_active).order_by(Product.id)
    if cat_id:
        query = query.where(Product.category_id == cat_id)
    products = list((await session.scalars(query)).all())

    if not products:
        await call.answer("В этой категории пока пусто 🙈", show_alert=True)
        return

    idx = max(0, min(idx, len(products) - 1))
    product = products[idx]
    await render_screen(
        call.message,
        product_caption(product, idx + 1, len(products)),
        product_kb(product.id, cat_id, idx, len(products)),
        photo=photo_source(product),
    )
    await call.answer()


@router.callback_query(F.data == "menu:catalog")
async def categories(call: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    await state.set_state(None)
    cats = list((await session.scalars(select(Category).order_by(Category.id))).all())
    count = await session.scalar(select(func.count()).select_from(Product).where(Product.is_active))
    text = (
        "🛍 <b>Каталог Nebula Shop</b>\n\n"
        f"В наличии <b>{count}</b> позиций. Выбери категорию или смотри всё подряд:"
    )
    await render_screen(call.message, text, categories_kb(cats))
    await call.answer()


@router.callback_query(F.data.startswith("add:"))
async def add_to_cart(call: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    await state.set_state(None)
    product_id = int(call.data.split(":")[1])
    product = await session.get(Product, product_id)
    if not product or not product.is_active:
        await call.answer("Товар недоступен 😔", show_alert=True)
        return

    stmt = (
        sqlite_insert(CartItem)
        .values(user_id=call.from_user.id, product_id=product_id, qty=1)
        .on_conflict_do_update(
            index_elements=[CartItem.user_id, CartItem.product_id],
            set_={"qty": func.min(CartItem.qty + 1, 99)},
        )
    )
    await session.execute(stmt)

    count = await session.scalar(
        select(func.coalesce(func.sum(CartItem.qty), 0)).where(
            CartItem.user_id == call.from_user.id
        )
    )
    await call.answer(f"✅ «{product.title}» в корзине · всего {count} шт")
