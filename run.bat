@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================
echo   Nebula Shop - Telegram shop bot
echo ============================================
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo [Ошибка] Python не найден.
    echo Установи Python 3.11 или новее с https://python.org
    echo При установке поставь галочку "Add Python to PATH".
    pause
    exit /b 1
)

if not exist ".venv" (
    echo [1/4] Создаю виртуальное окружение...
    python -m venv .venv
    if errorlevel 1 (
        echo [Ошибка] Не удалось создать окружение.
        pause
        exit /b 1
    )
) else (
    echo [1/4] Виртуальное окружение уже есть.
)

echo [2/4] Устанавливаю зависимости...
".venv\Scripts\python.exe" -m pip install --quiet --upgrade pip
".venv\Scripts\python.exe" -m pip install --quiet -r requirements.txt
if errorlevel 1 (
    echo [Ошибка] Не удалось установить зависимости. Проверь интернет.
    pause
    exit /b 1
)

if not exist ".env" (
    copy .env.example .env >nul
)

:checkenv
findstr /r /c:"^BOT_TOKEN=..*" .env >nul
if errorlevel 1 (
    echo.
    echo [3/4] Открываю .env - вставь BOT_TOKEN от @BotFather,
    echo       ADMIN_IDS (узнать: @userinfobot^) и сохрани файл.
    echo.
    start /wait notepad .env
    goto checkenv
)
echo [3/4] Токен на месте.

if not exist "nebula.db" (
    echo [4/4] Заполняю каталог демо-данными...
    ".venv\Scripts\python.exe" scripts\seed.py
) else (
    echo [4/4] База уже создана.
)

echo.
echo Бот запускается. Остановить: Ctrl+C или закрыть это окно.
echo.
".venv\Scripts\python.exe" main.py
pause
