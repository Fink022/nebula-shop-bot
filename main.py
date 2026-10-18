import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ErrorEvent, MenuButtonWebApp, WebAppInfo

from nebula.config import config
from nebula.db.engine import init_db
from nebula.handlers import (
    admin,
    ai_consultant,
    cart,
    catalog,
    checkout,
    profile,
    reviews,
    start,
)
from nebula.middlewares.db import DbSessionMiddleware
from nebula.webapp.server import start_webapp

logger = logging.getLogger(__name__)


async def on_error(event: ErrorEvent) -> bool:
    logger.exception("Необработанная ошибка: %s", event.exception)
    update = event.update
    try:
        if update.callback_query:
            await update.callback_query.answer("Не получилось, попробуй ещё раз", show_alert=True)
        elif update.message:
            await update.message.answer("Не получилось. Попробуй ещё раз.")
    except Exception:
        pass
    return True


def build_dispatcher() -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage())
    dp.update.middleware(DbSessionMiddleware())
    dp.errors.register(on_error)
    dp.include_router(start.router)
    dp.include_router(catalog.router)
    dp.include_router(cart.router)
    dp.include_router(checkout.router)
    dp.include_router(reviews.router)
    dp.include_router(profile.router)
    dp.include_router(ai_consultant.router)
    dp.include_router(admin.router)
    return dp


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    await init_db()

    bot = Bot(config.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    me = await bot.get_me()
    config.bot_username = me.username or ""

    await start_webapp(bot)

    if config.webapp_url:
        if not config.webapp_url.startswith("https://"):
            logger.warning(
                "WEBAPP_URL должен начинаться с https:// — кнопка Mini App не будет работать"
            )
        try:
            await bot.set_chat_menu_button(
                menu_button=MenuButtonWebApp(
                    text="🛍 Магазин",
                    web_app=WebAppInfo(url=config.webapp_url),
                )
            )
        except Exception:
            logger.exception("Не удалось установить кнопку Mini App")

    dp = build_dispatcher()
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("Nebula Shop запущен: @%s", me.username)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
