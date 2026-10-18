import aiohttp
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nebula.config import config
from nebula.db.models import Product
from nebula.utils import fmt_price

KEYWORD_GROUPS = {
    "часы": ("час", "watch", "браслет", "трекер"),
    "аудио": ("наушник", "звук", "музык", "аудио", "airpods", "колонк", "бас"),
    "проектор": ("проектор", "кино", "фильм", "экран", "beam"),
    "заряд": ("заряд", "powerbank", "аккумулятор", "батаре"),
    "клавиатура": ("клавиатур", "игр", "печат", "keys", "rgb"),
    "подарок": ("подар", "друг", "девушк", "парн", "день рожден"),
    "дом": ("дом", "умный дом", "колонк", "свет"),
    "путешествие": ("путешеств", "поход", "дорога", "самолет", "отпуск"),
}


def _offline_answer(products: list[Product], user_text: str) -> tuple[str, Product | None]:
    text = user_text.lower()
    matched_tags: set[str] = set()
    for tags in KEYWORD_GROUPS.values():
        if any(tag in text for tag in tags):
            matched_tags.update(tags)

    best_product: Product | None = None
    best_score = 0
    for product in products:
        haystack = f"{product.title} {product.description}".lower()
        score = sum(1 for tag in matched_tags if tag in haystack)
        if score > best_score:
            best_score = score
            best_product = product

    if best_product is None:
        best_product = products[0] if products else None

    if best_product is None:
        return "Каталог пока пуст — загляни чуть позже! 🌌", None

    advantage = best_product.description.split(".")[0].strip() or best_product.title
    answer = (
        "Смотри, что подходит под запрос:\n\n"
        f"{best_product.title} — {fmt_price(best_product.price)}\n"
        f"{advantage}.\n\n"
        "Открой карточку, там фото и кнопка «В корзину»."
    )
    return answer, best_product


async def _llm_answer(products: list[Product], user_text: str) -> tuple[str, Product | None]:
    catalog = "\n".join(
        f"- id={p.id} | {p.title} | {fmt_price(p.price)} | {p.description[:120]}" for p in products
    )
    system = (
        "Ты — дружелюбный ИИ-консультант магазина гаджетов Nebula Shop в Telegram. "
        "Отвечай коротко (до 90 слов), на русском, с эмодзи. Рекомендуй 1 товар из каталога "
        "и в конце укажи его id в формате [id=N]. Не выдумывай товары вне каталога.\n\nКаталог:\n"
        + catalog
    )
    payload = {
        "model": config.ai_model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user_text},
        ],
        "temperature": 0.7,
        "max_tokens": 300,
    }
    headers = {"Authorization": f"Bearer {config.ai_api_key}"}
    async with aiohttp.ClientSession() as client:
        async with client.post(
            f"{config.ai_base_url}/chat/completions", json=payload, headers=headers, timeout=30
        ) as response:
            response.raise_for_status()
            data = await response.json()
    message = data["choices"][0]["message"]["content"]
    product = None
    if "[id=" in message:
        try:
            raw_id = message.split("[id=")[1].split("]")[0]
            product = next((p for p in products if p.id == int(raw_id)), None)
        except (ValueError, IndexError):
            product = None
        message = message.split("[id=")[0].strip()
    return message, product


async def consult(session: AsyncSession, user_text: str) -> tuple[str, Product | None]:
    products = list(
        (await session.scalars(select(Product).where(Product.is_active).order_by(Product.id))).all()
    )
    if config.ai_api_key:
        try:
            return await _llm_answer(products, user_text)
        except Exception:
            pass
    return _offline_answer(products, user_text)
