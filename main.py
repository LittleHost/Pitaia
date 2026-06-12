import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Tuple

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command, ChatMemberUpdatedFilter, IS_NOT_MEMBER, IS_MEMBER
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup,
    InlineKeyboardButton, CallbackQuery, Message, ChatMemberUpdated
)
from aiogram.fsm.storage.memory import MemoryStorage

# ========== КОНФИГУРАЦИЯ ==========
BOT_TOKEN = "8733656900:AAElErRrQXDcg-Evu167wyJ2aR81yjNNO1o"
CHANNEL_ID = -1002236766440      # ID канала https://t.me/PitaiaTime
COMMENTS_CHAT_ID = -1003720079599  # ID чата, где комментарии

# База данных (in-memory для демо)
users_db: Dict[int, dict] = {}
posts_loot_tracker: Dict[int, list] = {}

# ========== ФУНКЦИИ БД ==========
def register_user(user_id: int, username: str):
    if user_id not in users_db:
        users_db[user_id] = {
            "name": username or str(user_id),
            "reg_date": datetime.now().strftime("%d.%m.%Y %H:%M"),
            "cookies": 0,
            "last_loot_post_id": None
        }

def get_user_cookies(user_id: int) -> int:
    return users_db.get(user_id, {}).get("cookies", 0)

def add_cookies(user_id: int, amount: int):
    if user_id in users_db:
        users_db[user_id]["cookies"] += amount

def get_top_users(limit=5) -> List[Tuple[int, str, int]]:
    sorted_users = sorted(users_db.items(), key=lambda x: x[1]["cookies"], reverse=True)
    result = []
    for uid, data in sorted_users[:limit]:
        result.append((uid, data["name"], data["cookies"]))
    return result

def get_user_rank(user_id: int) -> int:
    sorted_list = sorted(users_db.values(), key=lambda x: x["cookies"], reverse=True)
    user_data = users_db.get(user_id)
    if not user_data:
        return None
    for idx, u in enumerate(sorted_list, start=1):
        if u["name"] == user_data["name"] and u["cookies"] == user_data["cookies"]:
            return idx
    return len(sorted_list) + 1

# ========== КЛАВИАТУРЫ ==========
main_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Профиль"), KeyboardButton(text="Топы")],
        [KeyboardButton(text="Помощь"), KeyboardButton(text="Донат")]
    ],
    resize_keyboard=True
)

back_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="Назад")]],
    resize_keyboard=True
)

# ========== ИНИЦИАЛИЗАЦИЯ ==========
logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# ========== ФИЛЬТР ДЛЯ ЛИЧНЫХ СООБЩЕНИЙ ==========
async def private_chat_filter(message: Message) -> bool:
    """Разрешаем команды только в личных сообщениях"""
    return message.chat.type == "private"

# ========== ОБРАБОТЧИКИ ТОЛЬКО ДЛЯ ЛС ==========
@dp.message(Command("start"), F.chat.type == "private")
async def cmd_start(message: Message):
    user_id = message.from_user.id
    username = message.from_user.full_name
    register_user(user_id, username)

    text = (
        f"🥰 Приветик, {username}!\n"
        "Я - бот для раздачи печенек за активность в нашем Telegram канале.\n\n"
        "🍪 В конце каждого месяца подводятся итоги, а топ-5 мест в топе по печенькам, "
        "получают крутые вознаграждения на нашем сервере!\n\n"
        "😎 Вперед на Охоту за Печеньками!\n"
        "Покажи всем, кто здесь BOSS!"
    )
    await message.answer(text, reply_markup=main_kb)

@dp.message(F.text == "Профиль", F.chat.type == "private")
async def show_profile(message: Message):
    user_id = message.from_user.id
    if user_id not in users_db:
        register_user(user_id, message.from_user.full_name)

    data = users_db[user_id]
    rank = get_user_rank(user_id)
    text = (
        f"⭐ Твой профиль:\n\n"
        f"👤 Ник: {data['name']}\n"
        f"📱 ID: {user_id}\n"
        f"🗓️ Дата регистрации: {data['reg_date']}\n\n"
        f"💰 В твоем мешке: {data['cookies']} 🍪\n"
        f"📊 Позиция в топе: {rank} Место"
    )
    await message.answer(text, reply_markup=back_kb)

@dp.message(F.text == "Топы", F.chat.type == "private")
async def show_top(message: Message):
    top = get_top_users(5)
    if not top:
        text = "Пока нет участников. Будь первым!"
    else:
        lines = ["🏆 Топ Охотников за Печеньем:\n(серьезные чуваки)\n"]
        medals = ["🥇", "🥈", "🥉", "🏅", "🏅"]
        for i, (uid, name, cookies) in enumerate(top):
            medal = medals[i] if i < len(medals) else "🏅"
            lines.append(f"{medal}{i+1} Место: {name} ({cookies} 🍪)")
        text = "\n".join(lines)

    user_id = message.from_user.id
    user_cookies = get_user_cookies(user_id)
    user_rank = get_user_rank(user_id)
    text += f"\n\n💰 В твоем мешке: {user_cookies} 🍪\n📊 Позиция в топе: {user_rank} Место"

    await message.answer(text, reply_markup=back_kb)

@dp.message(F.text == "Помощь", F.chat.type == "private")
async def show_help(message: Message):
    text = (
        "❓ Помощь:\n\n"
        "😉 Если что-то не понятно, воспользуйся кнопочным меню.\n"
        "🔗 Поддержка: t.me/theid777"
    )
    await message.answer(text, reply_markup=back_kb)

@dp.message(F.text == "Донат", F.chat.type == "private")
async def show_donate(message: Message):
    text = (
        "💎 Поддержка проекта.\n\n"
        "❤️ Если тебе понравился бот и ты хочешь поддержать его развитие, "
        "можешь сделать добровольное пожертвование.\n\n"
        "🙃 Для этого просто перейди по кнопке\n"
        "Пожертвовать - t.me/Dev_Pranik"
    )
    await message.answer(text, reply_markup=back_kb)

@dp.message(F.text == "Назад", F.chat.type == "private")
async def back_to_main(message: Message):
    await message.answer("Главное меню:", reply_markup=main_kb)

# ========== ИГНОРИРУЕМ ВСЕ СООБЩЕНИЯ В ДРУГИХ ЧАТАХ ==========
@dp.message(F.chat.type.in_({"group", "supergroup"}))
async def ignore_group_messages(message: Message):
    """Полностью игнорируем любые сообщения в группах/чатах"""
    return  # Ничего не делаем

# ========== ЛОГИКА РАЗДАЧИ ПЕЧЕНЕК (работает только в чате комментариев) ==========
def calculate_cookie_reward(loot_order: int) -> int:
    if loot_order == 1:
        return 100
    elif 2 <= loot_order <= 5:
        return 75
    elif 6 <= loot_order <= 10:
        return 50
    elif 11 <= loot_order <= 100:
        return 25
    else:
        return 0

@dp.callback_query(F.data.startswith("loot_"))
async def handle_loot_callback(callback: CallbackQuery):
    # Проверяем, что колбэк пришел из чата комментариев
    if callback.message.chat.id != COMMENTS_CHAT_ID:
        await callback.answer("Этот бот работает только в чате комментариев канала!", show_alert=True)
        return

    user_id = callback.from_user.id
    username = callback.from_user.full_name
    register_user(user_id, username)

    post_id = int(callback.data.split("_")[1])

    if post_id not in posts_loot_tracker:
        posts_loot_tracker[post_id] = []

    if user_id in posts_loot_tracker[post_id]:
        await callback.answer("Ты уже забирал печеньки под этим постом!", show_alert=True)
        return

    if len(posts_loot_tracker[post_id]) >= 100:
        await callback.answer("Увы, все 100 порций печенек уже разобраны 😢", show_alert=True)
        return

    loot_order = len(posts_loot_tracker[post_id]) + 1
    reward = calculate_cookie_reward(loot_order)

    add_cookies(user_id, reward)
    new_balance = get_user_cookies(user_id)
    posts_loot_tracker[post_id].append(user_id)

    # Убираем кнопку у оригинального сообщения
    await callback.message.edit_reply_markup(reply_markup=None)
    
    # Отправляем уведомление
    user_mention = callback.from_user.mention_html()
    await callback.message.answer(
        f"🍪 Ура, {user_mention} залутал печеньки - твоё место {loot_order} - поздравляю 🎉\n\n"
        f"💰 Ты залутал {reward} печенек. В твоем мешке {new_balance} 🍪",
        parse_mode="HTML"
    )
    
    await callback.answer(f"Ты получил {reward} 🍪!", show_alert=False)

# ========== ОТСЛЕЖИВАНИЕ НОВЫХ ПОСТОВ В КАНАЛЕ ==========
@dp.channel_post()
async def handle_channel_post(message: Message):
    """Когда в канале новый пост - отправляем в чат комментариев"""
    if message.chat.id != CHANNEL_ID:
        return

    post_id = message.message_id

    inline_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🍪 Забрать печеньки", callback_data=f"loot_{post_id}")]
        ]
    )

    await bot.send_message(
        chat_id=COMMENTS_CHAT_ID,
        text="💰 Юху, новый пост!\n💎 Успей первым забрать печеньки!",
        reply_markup=inline_kb
    )

# ========== ЗАПУСК ==========
async def main():
    logging.info("Бот запущен")
    await bot.set_my_commands([
        types.BotCommand(command="start", description="Запустить бота")
    ])
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
