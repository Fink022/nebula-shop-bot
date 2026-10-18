#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

echo "============================================"
echo "  Nebula Shop - Telegram shop bot"
echo "============================================"
echo

PYTHON=$(command -v python3 || command -v python || true)
if [ -z "$PYTHON" ]; then
    echo "[Ошибка] Python не найден. Установи Python 3.11+ и запусти снова."
    exit 1
fi

if [ ! -d ".venv" ]; then
    echo "[1/4] Создаю виртуальное окружение..."
    "$PYTHON" -m venv .venv
else
    echo "[1/4] Виртуальное окружение уже есть."
fi

echo "[2/4] Устанавливаю зависимости..."
.venv/bin/python -m pip install --quiet --upgrade pip
.venv/bin/python -m pip install --quiet -r requirements.txt

if [ ! -f ".env" ]; then
    cp .env.example .env
fi

while ! grep -qE "^BOT_TOKEN=..+" .env; do
    echo
    echo "[3/4] Открой .env и вставь BOT_TOKEN от @BotFather и ADMIN_IDS (@userinfobot)."
    read -r -p "Нажми Enter, когда сохранишь файл..."
done
echo "[3/4] Токен на месте."

if [ ! -f "nebula.db" ]; then
    echo "[4/4] Заполняю каталог демо-данными..."
    .venv/bin/python scripts/seed.py
else
    echo "[4/4] База уже создана."
fi

echo
echo "Бот запускается. Остановить: Ctrl+C."
echo
exec .venv/bin/python main.py
