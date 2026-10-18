import hashlib
import hmac
import json
import logging
import time
from urllib.parse import parse_qsl

from nebula.config import config

logger = logging.getLogger(__name__)

INIT_DATA_MAX_AGE = 24 * 60 * 60


def parse_init_data(init_data: str) -> dict | None:
    if not init_data or not config.bot_token:
        return None
    try:
        pairs = dict(parse_qsl(init_data, strict_parsing=True, keep_blank_values=True))
    except ValueError:
        return None

    received_hash = pairs.pop("hash", None)
    if not received_hash:
        return None

    check_string = "\n".join(f"{key}={pairs[key]}" for key in sorted(pairs))
    secret = hmac.new(b"WebAppData", config.bot_token.encode(), hashlib.sha256).digest()
    calculated = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calculated, received_hash):
        return None

    try:
        auth_date = int(pairs.get("auth_date") or 0)
    except ValueError:
        return None
    if not auth_date or abs(time.time() - auth_date) > INIT_DATA_MAX_AGE:
        return None

    try:
        user = json.loads(pairs.get("user", "{}"))
    except json.JSONDecodeError:
        return None
    return user or None


def _is_local_request(request) -> bool:
    if request.remote not in ("127.0.0.1", "::1"):
        return False
    forwarded_headers = ("cf-connecting-ip", "cf-connecting-ipv6", "x-forwarded-for")
    return not any(header in request.headers for header in forwarded_headers)


async def authenticate(request) -> dict | None:
    if config.webapp_dev_mode and _is_local_request(request):
        dev_id = request.headers.get("X-Dev-Id")
        if dev_id and dev_id.isdigit() and len(dev_id) <= 18 and int(dev_id) > 0:
            return {"id": int(dev_id)}
    init_data = request.headers.get("X-Init-Data", "")
    if not init_data:
        logger.info("Mini App: запрос без авторизации (%s)", request.path)
        return None
    user = parse_init_data(init_data)
    if user is None:
        logger.warning("Mini App: невалидная подпись initData (%s)", request.path)
    return user
