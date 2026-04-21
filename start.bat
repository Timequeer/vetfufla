@echo off
chcp 65001 >nul
title VetFuture — запуск сервера

echo.
echo  ╔══════════════════════════════════╗
echo  ║     VetFuture — старт сервера   ║
echo  ╚══════════════════════════════════╝
echo.

:: Перевірка Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ПОМИЛКА] Python не знайдено! Встанови Python 3.10+
    pause & exit
)

:: Створення .env якщо немає
if not exist .env (
    echo [INFO] Створюю .env файл...
    (
        echo SECRET_KEY=change-this-secret-key-123
        echo TELEGRAM_BOT_TOKEN=
        echo ENOTE_BASE_URL=
        echo ENOTE_LOGIN=
        echo ENOTE_PASSWORD=
        echo OPENAI_API_KEY=
        echo MAIL_USERNAME=
        echo MAIL_PASSWORD=
    ) > .env
    echo [INFO] Заповни .env своїми ключами!
    echo.
)

:: Завантаження змінних з .env
for /f "tokens=1,2 delims==" %%a in (.env) do (
    if not "%%a"=="" if not "%%b"=="" set %%a=%%b
)

:: Створення venv якщо немає
if not exist venv (
    echo [INFO] Створюю віртуальне середовище...
    python -m venv venv
)

:: Активація venv
call venv\Scripts\activate.bat

:: Встановлення залежностей
echo [INFO] Перевірка залежностей...
pip install -r requirements.txt -q

:: Запуск
echo.
echo  ✅ Сервер запущено!
echo  🌐 Відкрий браузер: http://localhost:5000
echo  Ctrl+C — зупинити
echo.
python app.py

pause