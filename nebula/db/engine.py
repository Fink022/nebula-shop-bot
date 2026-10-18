from pathlib import Path

from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from nebula.config import config
from nebula.db.models import Base

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _resolve_db_url(url: str) -> str:
    prefix = "sqlite+aiosqlite:///"
    if not url.startswith(prefix):
        return url
    path = Path(url[len(prefix) :])
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return prefix + path.as_posix()


engine = create_async_engine(_resolve_db_url(config.db_url))
Session = async_sessionmaker(engine, expire_on_commit=False)

if engine.dialect.name == "sqlite":

    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection, _connection_record) -> None:
        # WAL + busy_timeout: бот и Mini App пишут в одну базу параллельно
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
