from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nebula.db.models import Product
from nebula.filters import IsPrivate
from nebula.keyboards import ai_answer_kb, ai_chat_kb
from nebula.services.ai import consult
from nebula.utils import render_screen

router = Router()
router.message.filter(IsPrivate())
router.callback_query.filter(IsPrivate())


class AiChat(StatesGroup):
    chat = State()


@router.callback_query(F.data == "menu:ai")
async def ai_start(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AiChat.chat)
    text = (
        "✨ <b>ИИ-консультант Nebula</b>\n\n"
        "Напиши, что нужно, — посмотрю, что есть в каталоге.\n\n"
        "Можно писать как есть: «подарок девушке до 5000» или «наушники с басом»."
    )
    await render_screen(call.message, text, ai_chat_kb())
    await call.answer()


@router.message(AiChat.chat, F.text, ~F.text.startswith("/"))
async def ai_chat(message: Message, session: AsyncSession) -> None:
    await message.bot.send_chat_action(message.chat.id, "typing")
    answer, product = await consult(session, message.text)

    index = None
    if product is not None:
        products = list(
            (
                await session.scalars(select(Product).where(Product.is_active).order_by(Product.id))
            ).all()
        )
        ids = [item.id for item in products]
        if product.id in ids:
            index = ids.index(product.id)

    await message.answer(answer, reply_markup=ai_answer_kb(index), parse_mode=None)
