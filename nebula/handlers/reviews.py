from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from nebula.db.models import Order, Product, Review
from nebula.filters import IsPrivate
from nebula.keyboards import back_menu_kb, rating_kb, review_text_kb
from nebula.utils import esc, render_screen

router = Router()
router.message.filter(IsPrivate())
router.callback_query.filter(IsPrivate())


class ReviewText(StatesGroup):
    text = State()


async def _already_reviewed(session: AsyncSession, user_id: int, order_id: int) -> bool:
    count = await session.scalar(
        select(func.count(Review.id)).where(Review.user_id == user_id, Review.order_id == order_id)
    )
    return bool(count)


async def _save_review(session: AsyncSession, user_id: int, data: dict, text: str) -> None:
    session.add(
        Review(
            user_id=user_id,
            product_id=data.get("product_id") or None,
            order_id=data.get("order_id"),
            rating=data.get("rating", 5),
            text=text,
        )
    )


@router.callback_query(F.data.startswith("review:"))
async def ask_rating(call: CallbackQuery, session: AsyncSession) -> None:
    _, order_id, product_id = call.data.split(":")
    order = await session.get(Order, int(order_id))
    if not order or order.user_id != call.from_user.id:
        await call.answer("Это не твой заказ 🙂", show_alert=True)
        return
    if await _already_reviewed(session, call.from_user.id, order.id):
        await call.answer("Ты уже оценил этот заказ — спасибо!", show_alert=True)
        return
    await render_screen(
        call.message,
        f"⭐ <b>Как тебе заказ #{order.id}?</b>\n\nПоставь оценку:",
        rating_kb(order.id, int(product_id)),
    )
    await call.answer()


@router.callback_query(F.data.startswith("rate:"))
async def save_rating(call: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    _, order_id, product_id, score = call.data.split(":")
    order = await session.get(Order, int(order_id))
    if not order or order.user_id != call.from_user.id:
        await call.answer("Это не твой заказ 🙂", show_alert=True)
        return
    if await _already_reviewed(session, call.from_user.id, order.id):
        await call.answer("Ты уже оценил этот заказ — спасибо!", show_alert=True)
        return
    await state.set_state(ReviewText.text)
    await state.update_data(order_id=order.id, product_id=int(product_id), rating=int(score))
    await render_screen(
        call.message,
        f"Оценка: {'⭐' * int(score)}\n\nРасскажи пару слов о заказе — или пропусти этот шаг:",
        review_text_kb(),
    )
    await call.answer()


@router.callback_query(F.data == "revskip")
async def skip_text(call: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    data = await state.get_data()
    if "rating" not in data:
        await call.answer("Отзыв уже отправлен", show_alert=True)
        return
    if await _already_reviewed(session, call.from_user.id, data["order_id"]):
        await state.clear()
        await call.answer("Ты уже оценил этот заказ — спасибо!", show_alert=True)
        return
    await _save_review(session, call.from_user.id, data, "")
    await state.clear()
    await render_screen(
        call.message,
        "🙏 Спасибо! Отзыв опубликован.",
        back_menu_kb(),
    )
    await call.answer()


@router.message(ReviewText.text, F.text)
async def save_text(message: Message, session: AsyncSession, state: FSMContext) -> None:
    data = await state.get_data()
    if "rating" not in data:
        return
    if await _already_reviewed(session, message.from_user.id, data["order_id"]):
        await state.clear()
        await message.answer("Ты уже оценил этот заказ — спасибо!", reply_markup=back_menu_kb())
        return
    text = (message.text or "").strip()[:600]
    await _save_review(session, message.from_user.id, data, text)
    await state.clear()
    await message.answer(
        "🙏 Спасибо! Отзыв опубликован.",
        reply_markup=back_menu_kb(),
    )


@router.callback_query(F.data == "menu:reviews")
async def show_reviews(call: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    await state.set_state(None)
    rows = (
        await session.execute(
            select(Review, Product.title)
            .outerjoin(Product, Review.product_id == Product.id)
            .order_by(Review.id.desc())
            .limit(5)
        )
    ).all()

    if not rows:
        text = "⭐ <b>Отзывы</b>\n\nПока отзывов нет — стань первым покупателем!"
    else:
        blocks = ["⭐ <b>Отзывы покупателей</b>\n"]
        for review, title in rows:
            blocks.append(
                f"{'⭐' * review.rating} · <b>{esc(title) or 'Nebula Shop'}</b>\n"
                f"{esc(review.text[:400]) or '<i>без комментария</i>'}"
            )
        text = "\n\n".join(blocks)

    await render_screen(call.message, text, back_menu_kb())
    await call.answer()
