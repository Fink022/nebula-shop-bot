import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


def _parse_ids(raw: str) -> list[int]:
    return [int(part) for part in raw.replace(" ", "").split(",") if part]


@dataclass
class Config:
    bot_token: str = os.getenv("BOT_TOKEN", "")
    admin_ids: list[int] = field(default_factory=lambda: _parse_ids(os.getenv("ADMIN_IDS", "")))
    ai_api_key: str = os.getenv("AI_API_KEY", "")
    ai_base_url: str = os.getenv("AI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    ai_model: str = os.getenv("AI_MODEL", "gpt-4o-mini")
    db_url: str = os.getenv("DB_URL", "sqlite+aiosqlite:///nebula.db")

    bot_username: str = ""

    webapp_enabled: bool = os.getenv("WEBAPP_ENABLED", "1") == "1"
    webapp_host: str = os.getenv("WEBAPP_HOST", "127.0.0.1")
    webapp_port: int = int(os.getenv("WEBAPP_PORT", "8080"))
    webapp_url: str = os.getenv("WEBAPP_URL", "")
    webapp_dev_mode: bool = os.getenv("WEBAPP_DEV_MODE", "0") == "1"

    referral_bonus_inviter: int = 100
    referral_bonus_newbie: int = 50
    cashback_percent: int = 3
    stars_rate: float = float(os.getenv("STARS_RATE", "1"))


config = Config()
