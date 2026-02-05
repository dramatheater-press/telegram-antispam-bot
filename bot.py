# -*- coding: utf-8 -*-
import os
import logging
import asyncio
import re
import json
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from dotenv import load_dotenv

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS", "").split(",")))

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

SPAM_FILE = "spam_patterns.json"

def load_spam_patterns():
    try:
        with open(SPAM_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []

def save_spam_patterns(patterns):
    with open(SPAM_FILE, 'w', encoding='utf-8') as f:
        json.dump(patterns, f, ensure_ascii=False, indent=2)

def is_spam(text: str) -> bool:
    if not text:
        return False
    
    text_lower = text.lower()
    patterns = load_spam_patterns()
    
    for pattern in patterns:
        if pattern.lower() in text_lower:
            return True
    
    links = re.findall(r'https?://[^\s]+|t\.me/[^\s]+|@[a-zA-Z0-9_]{5,}', text)
    if len(links) >= 2:
        return True
    
    if re.search(r'([a-z]{15,})', text_lower):
        return True
    
    return False

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    if message.chat.type != "private":
        return
    if message.from_user.id not in ADMIN_IDS:
        return
    await message.answer(
        "🛡️ Антиспам-бот готов.\n\n"
        "Команды (только в ЛС):\n"
        "/add_spam — добавить пример спама (ответьте на сообщение)\n"
        "/list_spam — список паттернов"
    )

@dp.message(Command("add_spam"))
async def cmd_add_spam(message: types.Message):
    if message.chat.type != "private" or message.from_user.id not in ADMIN_IDS:
        return
    if not message.reply_to_message:
        await message.answer("⚠️ Ответьте на сообщение со спамом командой /add_spam")
        return
    spam_text = (message.reply_to_message.text or message.reply_to_message.caption or "")
    if not spam_text.strip():
        await message.answer("⚠️ Сообщение пустое")
        return
    
    patterns = load_spam_patterns()
    if spam_text not in patterns:
        patterns.append(spam_text)
        save_spam_patterns(patterns)
        await message.answer(f"✅ Паттерн добавлен!\nКоличество паттернов: {len(patterns)}")
    else:
        await message.answer("ℹ️ Этот паттерн уже есть в базе")

@dp.message(Command("list_spam"))
async def cmd_list_spam(message: types.Message):
    if message.chat.type != "private" or message.from_user.id not in ADMIN_IDS:
        return
    patterns = load_spam_patterns()
    if not patterns:
        await message.answer("📭 Нет сохранённых паттернов")
        return
    text = f"Список паттернов ({len(patterns)}):\n\n"
    for i, pattern in enumerate(patterns[:20], 1):
        preview = pattern[:60].replace('\n', ' ') + ("..." if len(pattern) > 60 else "")
        text += f"{i}. {preview}\n"
    await message.answer(text)

@dp.message()
async def handle_message(message: types.Message):
    if not message.text and not message.caption:
        return
    
    try:
        member = await bot.get_chat_member(message.chat.id, message.from_user.id)
        if member.status in ['creator', 'administrator']:
            return
    except Exception:
        pass
    
    full_text = (message.text or message.caption or "")
    
    if is_spam(full_text):
        try:
            await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
            await bot.ban_chat_member(chat_id=message.chat.id, user_id=message.from_user.id, until_date=None)
            logger.info(
                f"🚫 Забанен @{message.from_user.username or message.from_user.id} | "
                f"Чат: {message.chat.title or message.chat.id} | "
                f"Текст: {full_text[:80]}"
            )
        except Exception as e:
            logger.error(f"Ошибка при обработке спама: {e}")

async def main():
    logger.info("🛡️ Антиспам-бот запущен")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())