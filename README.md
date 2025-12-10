# Telegram OpenAI Image Bot 

Телеграм-бот, который по текстовому запросу генерирует изображения через OpenAI API и отправляет их пользователю.

## Стек

- Python 3.x
- Aiogram
- OpenAI API (image generation)
- python-dotenv

## Переменные окружения

Создайте файл `.env` в корне проекта:

```env
TELEGRAM_BOT_TOKEN=токен
OPENAI_API_KEY=твой_openai_api_key
OPENAI_BASE_URL=https://api.openai.com/v1