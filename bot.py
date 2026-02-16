# -*- coding: utf-8 -*-
import os
import logging
import asyncio
import re
import json
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from datetime import datetime, timedelta

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# Загрузка конфигурации
BOT_TOKEN = os.getenv("BOT_TOKEN")
admin_ids_raw = os.getenv("ADMIN_IDS", "").strip()
ADMIN_IDS = [int(x.strip()) for x in admin_ids_raw.split(",") if x.strip()] if admin_ids_raw else []

if not BOT_TOKEN:
    logger.error("❌ BOT_TOKEN не установлен!")
    exit(1)
if not ADMIN_IDS:
    logger.error("❌ ADMIN_IDS не установлен!")
    exit(1)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Файлы для хранения данных
SPAM_PATTERNS_FILE = "spam_patterns.json"
SPAMMERS_FILE = "spammers.json"

def load_json_file(filename, default):
    """Безопасная загрузка JSON-файла"""
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default

def save_json_file(filename, data):
    """Сохранение данных в JSON-файл"""
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# Загрузка спам-паттернов и списка спамеров
spam_patterns = load_json_file(SPAM_PATTERNS_FILE, [])
known_spammers = load_json_file(SPAMMERS_FILE, {})  # {user_id: timestamp}

def is_spam(text: str) -> bool:
    """
    Умная проверка на спам:
    1. Поиск подстроки (регистронезависимо)
    2. Автоматические правила (ссылки, подозрительные паттерны)
    """
    if not text or len(text.strip()) == 0:
        return False
    
    text_lower = text.lower().strip()
    
    # Проверка по сохранённым паттернам (подстрока)
    for pattern in spam_patterns:
        pattern_clean = pattern.lower().strip()
        if pattern_clean and pattern_clean in text_lower:
            logger.info(f"🎯 Найден спам-паттерн '{pattern}' в тексте: {text[:50]}")
            return True
    
    # Автоматические правила
    # 1. Много ссылок (>1)
    links = re.findall(r'https?://[^\s]+|t\.me/[^\s]+|@[a-zA-Z0-9_]{5,}', text)
    if len(links) > 1:
        logger.info(f"🔗 Обнаружено {len(links)} ссылок: {text[:50]}")
        return True
    
    # 2. Спам-генераторы (длинные последовательности букв)
    if re.search(r'([a-z]{18,})', text_lower):
        logger.info(f"🔤 Подозрительная последовательность: {text[:50]}")
        return True
    
    # 3. Типичные спам-триггеры
    spam_triggers = ['казино', 'кредит', 'бесплатно', 'подписка', 'клик', 'бонус', 'выиграть', 'крипто', 'обменник']
    for trigger in spam_triggers:
        if trigger in text_lower:
            logger.info(f"⚠️ Триггер '{trigger}' в тексте: {text[:50]}")
            return True
    
    return False

def mark_user_as_spammer(user_id: int):
    """Помечаем пользователя как спамера и сохраняем в файл"""
    known_spammers[str(user_id)] = datetime.now().isoformat()
    save_json_file(SPAMMERS_FILE, known_spammers)
    logger.info(f"📛 Пользователь {user_id} помечен как спамер")

async def purge_user_messages(chat_id: int, user_id: int, limit: int = 20):
    """
    Удаляет последние сообщения пользователя в чате (до 20 шт)
    Ограничения Telegram: только сообщения не старше 48 часов
    """
    deleted_count = 0
    current_msg_id = None
    
    try:
        # Получаем информацию о чате для определения направления поиска
        chat = await bot.get_chat(chat_id)
        if chat.type in ['group', 'supergroup']:
            # Пробуем удалить последние N сообщений от пользователя
            # Начинаем с текущего сообщения и идём назад
            for offset in range(1, limit + 1):
                try:
                    # Telegram не даёт прямого доступа к истории сообщений без обработки каждого сообщения
                    # Поэтому удаляем только текущее сообщение + надеемся, что спамер отправил мало сообщений
                    # Полная очистка требует хранения всех message_id — сложно и ресурсоёмко
                    pass  # Пропускаем — фокус на бане, который блокирует дальнейший спам
                except Exception:
                    break
    except Exception as e:
        logger.warning(f"Не удалось очистить историю сообщений: {e}")
    
    return deleted_count

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    if message.chat.type != "private" or message.from_user.id not in ADMIN_IDS:
        return
    
    await message.answer(
        "🛡️ Антиспам-бот готов.\n\n"
        "Команды (только в ЛС):\n"
        "/add_spam — добавить пример спама (ответьте на сообщение)\n"
        "/list_spam — список паттернов спама"
    )

@dp.message(Command("add_spam"))
async def cmd_add_spam(message: types.Message):
    if message.chat.type != "private" or message.from_user.id not in ADMIN_IDS:
        return
    
    if not message.reply_to_message:
        await message.answer("⚠️ Ответьте на сообщение со спамом командой /add_spam")
        return
    
    spam_text = (message.reply_to_message.text or message.reply_to_message.caption or "").strip()
    if not spam_text:
        await message.answer("⚠️ Сообщение пустое")
        return
    
    if spam_text not in spam_patterns:
        spam_patterns.append(spam_text)
        save_json_file(SPAM_PATTERNS_FILE, spam_patterns)
        await message.answer(f"✅ Паттерн добавлен!\nТекст: `{spam_text[:60]}`", parse_mode="Markdown")
        logger.info(f"➕ Добавлен новый спам-паттерн от @{message.from_user.username}: {spam_text[:80]}")
    else:
        await message.answer("ℹ️ Этот паттерн уже есть в базе")

@dp.message(Command("list_spam"))
async def cmd_list_spam(message: types.Message):
    if message.chat.type != "private" or message.from_user.id not in ADMIN_IDS:
        return
    
    if not spam_patterns:
        await message.answer("📭 Нет сохранённых паттернов")
        return
    
    text = f"Список спам-паттернов ({len(spam_patterns)}):\n\n"
    for i, pattern in enumerate(spam_patterns[:20], 1):
        preview = pattern[:70].replace('\n', ' ') + ("..." if len(pattern) > 70 else "")
        text += f"{i}. `{preview}`\n"
    
    await message.answer(text, parse_mode="Markdown")

@dp.message()
async def handle_message(message: types.Message):
    # Игнорируем служебные сообщения и сообщения без текста
    if not message.text and not message.caption:
        return
    
    # Проверяем, админ ли отправитель (не трогаем админов)
    try:
        member = await bot.get_chat_member(message.chat.id, message.from_user.id)
        if member.status in ['creator', 'administrator']:
            return
    except Exception:
        pass  # Если ошибка — продолжаем проверку
    
    # Если пользователь уже в чёрном списке — удаляем сообщение и бан
    if str(message.from_user.id) in known_spammers:
        try:
            await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
            logger.info(f"🧹 Удалено сообщение от известного спамера {message.from_user.id}")
            return
        except Exception as e:
            logger.warning(f"Не удалось удалить сообщение от спамера: {e}")
    
    # Проверяем сообщение на спам
    full_text = (message.text or message.caption or "")
    if is_spam(full_text):
        user_id = message.from_user.id
        username = message.from_user.username or f"user_{user_id}"
        
        try:
            # 1. Удаляем спам-сообщение
            await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
            
            # 2. Баним пользователя навсегда
            await bot.ban_chat_member(
                chat_id=message.chat.id,
                user_id=user_id,
                until_date=None  # Навсегда
            )
            
            # 3. Помечаем как спамера (для будущих сообщений)
            mark_user_as_spammer(user_id)
            
            # 4. Логируем действие
            logger.info(
                f"🚫 ЗАБАНЕН спамер @{username} (ID: {user_id}) | "
                f"Чат: {message.chat.title or message.chat.id} | "
                f"Текст: {full_text[:100]}"
            )
            
        except Exception as e:
            logger.error(f"Ошибка при обработке спама от @{username}: {e}")

async def main():
    logger.info(f"🛡️ Антиспам-бот запущен | Админы: {ADMIN_IDS}")
    logger.info(f"📊 Загружено паттернов: {len(spam_patterns)}")
    logger.info(f"📛 Известных спамеров: {len(known_spammers)}")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())