# handlers.py
from io import BytesIO
from aiogram import Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, InputFile
from generator import generate_image_bytes, edit_image_bytes, ModerationError
from database import (
    has_credits, consume_credit, get_credits,
    is_payment_recorded, record_payment, add_uses,
)
from payment import create_invoice, cryptopay
from config import ADMIN_IDS

# Память последних изображений (на проде лучше хранить в БД/кеше)
LAST_PHOTO: dict[int, bytes] = {}
LAST_MASK: dict[int, bytes] = {}

# ── утилиты
def _humanize_categories(cats):
    mapping = {
        "sexual": "сексуальный контент/нюд",
        "sexual_minors": "сексуальный контент с участием несовершеннолетних (запрет)",
        "graphic_violence": "графическое насилие/жестокость",
        "self-harm": "самоповреждение/суицид",
        "hate": "ненависть/разжигание",
        "weapons": "оружие/взрывчатка",
        "drugs": "наркотики",
        "copyright": "нарушение авторских прав",
        "political_persuasion": "политическая агитация",
    }
    if not cats:
        return "контент, нарушающий правила безопасности"
    return ", ".join(mapping.get(c, c) for c in cats)

async def _ensure_quota_or_pay(message: types.Message, is_admin: bool) -> bool:
    if is_admin:
        return True
    if has_credits(message.from_user.id):
        return True
    keyboard = InlineKeyboardMarkup().add(
        InlineKeyboardButton("Пополнить 1 TON (10 генераций)", callback_data="pay_now")
    )
    await message.answer(
        "⚠️ У тебя закончились генерации. Пополни баланс, чтобы продолжить:",
        reply_markup=keyboard
    )
    return False

async def _send_png(message: types.Message, png_bytes: bytes, caption: str = ""):
    bio = BytesIO(png_bytes)
    bio.name = "image.png"
    await message.answer_photo(photo=InputFile(bio, filename="image.png"), caption=caption)

# ── команды
async def start_handler(message: types.Message):
    left = get_credits(message.from_user.id)
    await message.answer(
        "👋 Привет! Я — AI-бот для генерации и редактирования изображений.\n\n"
        "🖼 Сгенерировать с нуля: просто пришли текст-описание.\n"
        "✏️ Редактировать: пришли фото (по желанию — PNG-маску как Документ), затем /edit \"описание правок\".\n"
        "   Можно сразу: фото с подписью — если маска уже загружена, применю её.\n\n"
        "💳 Команды:\n"
        "/pay — пополнить генерации\n"
        "/check — проверить оплату\n"
        "/balance — остаток генераций\n"
        "/edit \"описание правок\" — отредактировать последнее фото (учту маску)\n"
        "/clear — забыть сохранённые фото/маску\n\n"
        f"🎁 Бесплатные генерации: {left}"
    )

async def balance_handler(message: types.Message):
    left = get_credits(message.from_user.id)
    await message.answer(f"💰 Остаток генераций: {left}")

async def pay_handler(message: types.Message):
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton("💎 10 генераций — 1 TON", callback_data="buy_10"),
        InlineKeyboardButton("💎 50 генераций — 4 TON", callback_data="buy_50"),
        InlineKeyboardButton("💎 200 генераций — 12 TON", callback_data="buy_200"),
    )
    await message.answer("Выберите тариф:", reply_markup=keyboard)

async def check_handler(message: types.Message):
    user_id = message.from_user.id
    try:
        invoices = await cryptopay.get_invoices()
        for inv in invoices:
            if getattr(inv, "status", None) != "paid":
                continue
            desc = getattr(inv, "description", "") or ""
            if not desc.startswith(str(user_id)):
                continue
            if is_payment_recorded(inv.invoice_id):
                continue
            try:
                _, gens_str = desc.split(":")
                gens = int(gens_str)
            except Exception as parse_err:
                print(f"[CHECK] Ошибка разбора description: {desc} | {parse_err}")
                continue
            record_payment(inv.invoice_id, user_id, inv.amount)
            add_uses(user_id, gens)
            await message.answer(f"✅ Платёж подтверждён! Начислено {gens} генераций. Баланс: {get_credits(user_id)}")
            return
        await message.answer("🕓 Пока не найдено подтверждённых счетов. Попробуй позже.")
    except Exception as e:
        print("[💥] Ошибка /check:", e)
        await message.answer("❌ Ошибка при проверке. Попробуй позже.")

async def clear_handler(message: types.Message):
    uid = message.from_user.id
    LAST_PHOTO.pop(uid, None)
    LAST_MASK.pop(uid, None)
    await message.answer("🧹 Ок! Забыл твоё последнее фото и маску.")

# ── генерация с текста
async def prompt_text_handler(message: types.Message):
    user_id = message.from_user.id
    is_admin = user_id in (ADMIN_IDS or [])
    if not await _ensure_quota_or_pay(message, is_admin):
        return

    prompt = (message.text or "").strip()
    if not prompt:
        await message.answer("Напиши описание изображения текстом 🙂")
        return

    wait_msg = await message.answer("🎨 Генерирую изображение... ⏳" + (" (режим админа)" if is_admin else ""))
    try:
        png_bytes = generate_image_bytes(prompt, size="1024x1024")
        if not png_bytes:
            await message.answer("❌ Не удалось сгенерировать изображение. Попробуй позже.")
            return

        # успех → списываем 1 генерацию (не для админа)
        if not is_admin:
            consume_credit(user_id)

        caption = f"Готово ✅\nPrompt: {prompt}" + ("\n👑 Админ-режим: безлимит" if is_admin else "")
        await _send_png(message, png_bytes, caption)
    except ModerationError as me:
        cats_h = _humanize_categories(me.categories)
        tips = [
            "исключи слова про обнажёнку/сексуальные детали",
            "убери упоминание несовершеннолетних",
            "замени явные термины на нейтральные (напр. «гламурная фотосессия в платье»)",
            "сфокусируйся на стиле/окружении/ракурсе, а не на телесных деталях",
        ]
        await message.answer(
            "🚫 Запрос заблокирован системой безопасности.\n"
            f"Категории: *{cats_h}*.\n\n"
            "Попробуй переформулировать:\n"
            f"• {tips[0]}\n• {tips[1]}\n• {tips[2]}\n• {tips[3]}",
            parse_mode="Markdown"
        )
    except Exception as e:
        text = str(e)
        if "Verify Organization" in text or "must be verified" in text:
            await message.answer(
                "❌ Модель пока недоступна для организации. Settings → Organization → Verify Organization.\n"
                "После верификации доступ включается примерно за 15 минут."
            )
        else:
            await message.answer(f"❌ Ошибка: {e}")
    finally:
        try:
            await wait_msg.delete()
        except Exception:
            pass

# ── фото (сохраняем/редактируем)
async def photo_handler(message: types.Message):
    user_id = message.from_user.id
    is_admin = user_id in (ADMIN_IDS or [])
    photo_sizes = message.photo
    if not photo_sizes:
        return
    best = photo_sizes[-1]
    file = await message.bot.get_file(best.file_id)
    file_bytes = await message.bot.download_file(file.file_path)
    image_bytes = file_bytes.read()
    LAST_PHOTO[user_id] = image_bytes

    caption = (message.caption or "").strip()
    if not caption:
        await message.answer(
            "📷 Фото сохранено. Теперь:\n"
            "• (опционально) пришли PNG-маску как Документ\n"
            "• затем /edit <что изменить>\n"
            "Пример: `/edit добавить солнцезащитные очки и сделать фон городским`",
            parse_mode="Markdown"
        )
        return

    if not await _ensure_quota_or_pay(message, is_admin):
        return

    wait_msg = await message.answer("✏️ Редактирую фото... ⏳" + (" (режим админа)" if is_admin else ""))
    try:
        mask = LAST_MASK.get(user_id)
        png_bytes = edit_image_bytes(image_bytes=image_bytes, prompt=caption, size="1024x1024", mask_bytes=mask)
        if not png_bytes:
            await message.answer("❌ Не удалось отредактировать изображение. Попробуй позже.")
            return

        if not is_admin:
            consume_credit(user_id)

        cap = f"Готово ✅\nEdit-prompt: {caption}" + ("\n👑 Админ-режим: безлимит" if is_admin else "")
        await _send_png(message, png_bytes, cap)
    except ModerationError as me:
        cats_h = _humanize_categories(me.categories)
        tips = [
            "исключи слова про обнажёнку/сексуальные детали",
            "не проси менять возраст/внешность на несовершеннолетних",
            "используй нейтральные формулировки (напр. «добавить очки», «заменить фон на городской»)",
        ]
        await message.answer(
            "🚫 Редактирование заблокировано системой безопасности.\n"
            f"Категории: *{cats_h}*.\n\n"
            "Попробуй переформулировать:\n"
            f"• {tips[0]}\n• {tips[1]}\n• {tips[2]}",
            parse_mode="Markdown"
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")
    finally:
        try:
            await wait_msg.delete()
        except Exception:
            pass

# ── документы (маска PNG или исходник-картинка как файл)
async def document_handler(message: types.Message):
    user_id = message.from_user.id
    doc: types.Document = message.document
    if not doc:
        return
    file = await message.bot.get_file(doc.file_id)
    file_bytes = await message.bot.download_file(file.file_path)
    content = file_bytes.read()
    filename = (doc.file_name or "").lower()
    mime = (doc.mime_type or "").lower()

    if filename.endswith(".png") or "png" in mime:
        LAST_MASK[user_id] = content
        await message.answer("🖌 Маска сохранена. Пришли `/edit <промпт>` для применения к последнему фото.", parse_mode="Markdown")
    else:
        LAST_PHOTO[user_id] = content
        await message.answer("📷 Фото сохранено как исходник. Пришли PNG-маску (по желанию), затем `/edit <промпт>`.", parse_mode="Markdown")

# ── /edit <промпт> — редактировать последнее фото (учитывая маску)
async def edit_command_handler(message: types.Message):
    user_id = message.from_user.id
    is_admin = user_id in (ADMIN_IDS or [])
    args = (message.get_args() or "").strip()
    if not args:
        await message.reply("Использование: `/edit <описание правок>`", parse_mode="Markdown")
        return
    image_bytes = LAST_PHOTO.get(user_id)
    if not image_bytes:
        await message.reply("Сначала пришли фото, которое нужно отредактировать 📷")
        return
    if not await _ensure_quota_or_pay(message, is_admin):
        return

    wait_msg = await message.answer("✏️ Редактирую последнее фото... ⏳" + (" (режим админа)" if is_admin else ""))
    try:
        mask = LAST_MASK.get(user_id)
        png_bytes = edit_image_bytes(image_bytes=image_bytes, prompt=args, size="1024x1024", mask_bytes=mask)
        if not png_bytes:
            await message.answer("❌ Не удалось отредактировать изображение. Попробуй позже.")
            return

        if not is_admin:
            consume_credit(user_id)

        cap = f"Готово ✅\nEdit-prompt: {args}" + ("\n👑 Админ-режим: безлимит" if is_admin else "")
        await _send_png(message, png_bytes, cap)
    except ModerationError as me:
        cats_h = _humanize_categories(me.categories)
        await message.answer(
            "🚫 Редактирование заблокировано системой безопасности.\n"
            f"Категории: *{cats_h}*.",
            parse_mode="Markdown"
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")
    finally:
        try:
            await wait_msg.delete()
        except Exception:
            pass

# ── inline-кнопки (тарифы/проверка)
async def button_handler(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    data = callback_query.data or ""
    tariffs = {
        "buy_10": (1.0, 10),
        "buy_50": (4.0, 50),
        "buy_200": (12.0, 200),
        "pay_now": (1.0, 10),
    }
    if data in tariffs:
        amount, gens = tariffs[data]
        pay_url = await create_invoice(amount_ton=amount, user_id=user_id, generations=gens)
        keyboard = InlineKeyboardMarkup(row_width=1)
        keyboard.add(
            InlineKeyboardButton(f"Оплатить {amount} TON", url=pay_url),
            InlineKeyboardButton("🔄 Проверить оплату", callback_data="check_payment"),
        )
        await callback_query.message.edit_text(
            f"Нажми кнопку ниже, чтобы оплатить {amount} TON и получить {gens} генераций:",
            reply_markup=keyboard
        )
    elif data == "check_payment":
        msg = callback_query.message
        msg.from_user = callback_query.from_user
        await check_handler(msg)

# ── регистрация
def register_handlers(dp: Dispatcher):
    dp.register_message_handler(start_handler, commands=["start"])
    dp.register_message_handler(balance_handler, commands=["balance"])
    dp.register_message_handler(pay_handler, commands=["pay"])
    dp.register_message_handler(check_handler, commands=["check"])
    dp.register_message_handler(clear_handler, commands=["clear"])
    dp.register_message_handler(edit_command_handler, commands=["edit"])
    dp.register_callback_query_handler(button_handler)

    dp.register_message_handler(document_handler, content_types=types.ContentTypes.DOCUMENT)
    dp.register_message_handler(photo_handler, content_types=types.ContentTypes.PHOTO)
    dp.register_message_handler(prompt_text_handler, content_types=types.ContentTypes.TEXT)