import logging
import re
from pathlib import Path

import aiohttp
from aiohttp import web

from nebula.config import config
from nebula.db.engine import Session
from nebula.db.models import Product
from nebula.webapp.api import routes

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
WEBAPP_DIR = PROJECT_ROOT / "webapp"
PRODUCTS_DIR = PROJECT_ROOT / "assets" / "products"


@web.middleware
async def error_middleware(request: web.Request, handler):
    try:
        return await handler(request)
    except web.HTTPException:
        raise
    except Exception:
        logger.exception("Ошибка в Mini App: %s", request.path)
        return web.json_response({"error": "Внутренняя ошибка, попробуй ещё раз"}, status=500)


@web.middleware
async def cache_middleware(request: web.Request, handler):
    response = await handler(request)
    if request.path == "/" or request.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-cache"
    return response


@routes.get("/")
async def index(request: web.Request) -> web.Response:
    return web.FileResponse(WEBAPP_DIR / "index.html")


@routes.get("/products/{name}")
async def product_image(request: web.Request) -> web.Response:
    name = request.match_info["name"]
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", name):
        raise web.HTTPNotFound()
    path = PRODUCTS_DIR / name
    if not path.is_file():
        raise web.HTTPNotFound()
    return web.FileResponse(path)


@routes.get("/photo/{product_id}")
async def bot_photo(request: web.Request) -> web.Response:
    try:
        product_id = int(request.match_info["product_id"])
    except ValueError:
        raise web.HTTPNotFound()

    async with Session() as session:
        product = await session.get(Product, product_id)
    if not product or not product.photo or product.photo.startswith("assets/"):
        raise web.HTTPNotFound()

    bot = request.app["bot"]
    try:
        file = await bot.get_file(product.photo)
    except Exception:
        raise web.HTTPNotFound()

    url = f"https://api.telegram.org/file/bot{config.bot_token}/{file.file_path}"
    async with aiohttp.ClientSession() as client:
        async with client.get(url) as response:
            if response.status != 200:
                raise web.HTTPNotFound()
            body = await response.read()
            content_type = response.headers.get("Content-Type", "image/jpeg")
    return web.Response(body=body, content_type=content_type)


def create_webapp(bot) -> web.Application:
    app = web.Application(middlewares=[error_middleware, cache_middleware])
    app["bot"] = bot
    app.add_routes(routes)
    app.router.add_static("/static", WEBAPP_DIR, name="static")
    return app


async def start_webapp(bot) -> web.AppRunner | None:
    if not config.webapp_enabled:
        return None
    try:
        runner = web.AppRunner(create_webapp(bot))
        await runner.setup()
        site = web.TCPSite(runner, config.webapp_host, config.webapp_port)
        await site.start()
        logger.info("Mini App запущено: http://%s:%s", config.webapp_host, config.webapp_port)
        return runner
    except OSError as error:
        logger.error("Не удалось запустить Mini App сервер: %s", error)
        return None
