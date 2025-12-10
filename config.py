import os
from dotenv import load_dotenv

# Загружаем переменные окружения из .env
load_dotenv()

# 🔑 Основные токены
BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
CRYPTOBOT_TOKEN = os.getenv("CRYPTOBOT_TOKEN")

# 👨‍💻 Админы (список ID через запятую в .env)
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x]

# 🌍 Прокси для Telegram (если нужно)
# Пример для .env: TELEGRAM_PROXY_URL=http://login:password@181.215.184.208:50100
TELEGRAM_PROXY_URL = os.getenv("TELEGRAM_PROXY_URL")

# 📑 Режим парсинга сообщений (по умолчанию HTML)
PARSE_MODE = os.getenv("PARSE_MODE", "HTML")