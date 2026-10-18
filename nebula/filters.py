from aiogram.filters import BaseFilter
from aiogram.types import TelegramObject

from nebula.config import config


class AdminFilter(BaseFilter):
    async def __call__(self, event: TelegramObject) -> bool:
        user = getattr(event, "from_user", None)
        return bool(user and user.id in config.admin_ids)


class IsPrivate(BaseFilter):
    async def __call__(self, event: TelegramObject) -> bool:
        chat = getattr(event, "chat", None)
        if chat is None:
            message = getattr(event, "message", None)
            chat = getattr(message, "chat", None)
        return bool(chat and chat.type == "private")
