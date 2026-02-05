import os
import logging
import asyncio
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command, IS_MEMBER, IS_NOT_MEMBER
from aiogram.types import Message
from dotenv import load_dotenv
from database import SpamDB
from spam_filter import SilentSpamFilter

# Без вывода в чат — только в лог файл/консоль
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler('antispam.log'),
        logging.StreamHandler()  # Только для сервера, не для чата!
    ]
)
logger = logging.getLogger(__name__)

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS", "").split(",")))  # В .env: ADMIN_IDS=123456789,987654321

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
db = SpamDB()
filter_engine = SilentSpamFilter(db)

# === ПРИВАТНЫЕ КОМАНДЫ ДЛЯ АДМИНИСТРАТОРА (только в ЛС с ботом) ===
@dp.message(Command("start"))
async def cmd_start(message: Message):
    if message.chat.type != "private":
        return  # Игнорируем в группах
    
    if message.from_user.id not in ADMIN_IDS:
        return  # Только для админов
    
    await message.answer(
        "??? Антиспам-бот готов.\n\n"
        "Команды (только в ЛС):\n"
        "/add_spam — добавить пример спама (ответьте на сообщение)\n"
        "/list_spam — список паттернов\n"
        "/del_spam ID — удалить паттерн"
    )

@dp.message(Command("add_spam"))
async def cmd_add_spam(message: Message):
    if message.chat.type != "private" or message.from_user.id not in ADMIN_IDS:
        return
    
    if not message.reply_to_message:
        await message.answer("?? Ответьте на сообщение со спамом командой /add_spam")
        return
    
    spam_text = (message.reply_to_message.text or message.reply_to_message.caption or "")
    if not spam_text.strip():
        await message.answer("?? Сообщение пустое или содержит только медиа")
        return
    
    sample_id = db.add_sample(spam_text, pattern_type='substring', admin_id=message.from_user.id)
    filter_engine.reload_patterns()
    
    await message.answer(f"? Паттерн добавлен (ID: {sample_id})\n\nПример:\n{spam_text[:100]}")

@dp.message(Command("list_spam"))
async def cmd_list_spam(message: Message):
    if message.chat.type != "private" or message.from_user.id not in ADMIN_IDS:
        return
    
    samples = db.get_all_samples()
    if not samples:
        await message.answer("?? Нет сохранённых паттернов")
        return
    
    text = "Список паттернов:\n"
    for i, (pattern, ptype) in enumerate(samples[:20], 1):  # Первые 20
        preview = pattern[:50].replace('\n', ' ') + ("..." if len(pattern) > 50 else "")
        text += f"{i}. [{ptype}] {preview}\n"
    
    await message.answer(text)

# === ОСНОВНАЯ ЛОГИКА: МОЛЧАЛИВАЯ ОЧИСТКА ЧАТА ===
@dp.message()
async def handle_message(message: Message):
    # Игнорируем служебные сообщения и сообщения от администраторов
    if message.content_type not in ['text', 'caption']:
        return
    
    # Проверяем, админ ли отправитель (чтобы не забанить админа по ошибке)
    try:
        member = await bot.get_chat_member(message.chat.id, message.from_user.id)
        if member.status in ['creator', 'administrator']:
            return
    except Exception:
        pass  # Если ошибка — продолжаем проверку
    
    full_text = (message.text or message.caption or "")
    
    if filter_engine.is_spam(full_text):
        try:
            # 1. Удаляем сообщение
            await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
            
            # 2. Баним пользователя навсегда
            await bot.ban_chat_member(
                chat_id=message.chat.id,
                user_id=message.from_user.id,
                until_date=None  # Навсегда
            )
            
            # 3. Логируем действие (только в файл, НЕ в чат!)
            logger.info(
                f"Забанен @{message.from_user.username or message.from_user.id} | "
                f"Чат: {message.chat.title or message.chat.id} | "
                f"Текст: {full_text[:80]}"
            )
            
        except Exception as e:
            logger.error(f"Ошибка при обработке спама: {e}")

async def main():
    logger.info("??? Антиспам-бот запущен (режим полной тишины)")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())