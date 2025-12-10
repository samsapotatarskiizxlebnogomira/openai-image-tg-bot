# main.py
import logging
import os
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor

import config
from handlers import register_handlers

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)

# Опциональный прокси для Telegram (НЕ для OpenAI)
# В .env / config.py: TELEGRAM_PROXY_URL=http://login:pass@host:port
telegram_proxy = getattr(config, "TELEGRAM_PROXY_URL", None)
parse_mode = getattr(config, "PARSE_MODE", "HTML")

if telegram_proxy:
    bot = Bot(token=config.BOT_TOKEN, parse_mode=parse_mode, proxy=telegram_proxy)
else:
    bot = Bot(token=config.BOT_TOKEN, parse_mode=parse_mode)

dp = Dispatcher(bot)

# Регистрируем хендлеры
register_handlers(dp)

async def on_startup(_dispatcher: Dispatcher):
    me = await bot.get_me()
    logging.info(f"✅ Bot started: @{me.username} (id={me.id})")

    # По желанию — выставим команды в меню бота
    try:
        await bot.set_my_commands([
            types.BotCommand(command="start", description="Помощь"),
            types.BotCommand(command="balance", description="Остаток генераций"),
            types.BotCommand(command="pay", description="Пополнить генерации"),
            types.BotCommand(command="check", description="Проверить оплату"),
            types.BotCommand(command="edit", description="Редактировать последнее фото"),
            types.BotCommand(command="clear", description="Забыть фото/маску"),
        ])
    except Exception as e:
        logging.warning(f"Не удалось установить команды: {e}")

if __name__ == "__main__":
    # skip_updates=True — не разгребаем старые апдейты при старте
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup)