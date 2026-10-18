from aiogram import F, Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, Message
from sqlalchemy.ext.asyncio import AsyncSession

from nebula.config import config
from nebula.db.models import User
from nebula.filters import IsPrivate
from nebula.keyboards import main_menu_kb
from nebula.utils import PROJECT_ROOT, esc, get_or_create_user, render_screen

router = Router()
router.message.filter(IsPrivate())
router.callback_query.filter(IsPrivate())

WELCOME = (
    "👋 Привет! Это <b>Nebula Shop</b>.\n\n"
    "Смотри каталог, собирай корзину. Платить можно звёздами или бонусами, "
    "а если не знаешь, что выбрать — спроси ИИ-консультанта."
)

MENU = "🏠 <b>Главное меню</b>\n\nКуда отправимся?"


def _banner():
    path = PROJECT_ROOT / "assets" / "banner.png"
    return FSInputFile(path) if path.exists() else None


@router.message(CommandStart())
async def start(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    await state.clear()
    tg_user = message.from_user
    user = await session.get(User, tg_user.id)

    if user is None and command.args and command.args.startswith("ref_"):
        try:
            inviter_id = int(command.args.split("_", 1)[1])
        except ValueError:
            inviter_id = 0
        inviter = await session.get(User, inviter_id) if inviter_id else None
        if inviter and inviter.id != tg_user.id:
            user = await get_or_create_user(session, tg_user)
            user.referred_by = inviter.id
            user.bonus += config.referral_bonus_newbie
            inviter.bonus += config.referral_bonus_inviter
            try:
                await message.bot.send_message(
                    inviter.id,
                    f"🎉 По твоей ссылке пришёл <b>{esc(tg_user.first_name)}</b>!\n"
                    f"Начислено +{config.referral_bonus_inviter} бонусов.",
                )
            except Exception:
                pass

    if user is None:
        user = await get_or_create_user(session, tg_user)

    is_admin = tg_user.id in config.admin_ids
    caption = WELCOME
    if user.referred_by:
        caption += f"\n\n🎁 Тебе начислено {config.referral_bonus_newbie} приветственных бонусов!"

    banner = _banner()
    await render_screen(message, caption, main_menu_kb(is_admin), photo=banner)


@router.callback_query(F.data == "menu:main")
async def main_menu(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    is_admin = call.from_user.id in config.admin_ids
    await render_screen(call.message, MENU, main_menu_kb(is_admin))
    await call.answer()
