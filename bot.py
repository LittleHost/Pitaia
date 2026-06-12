import asyncio
import logging
import sqlite3
import aiohttp
from datetime import datetime
from typing import Dict, List

from aiogram import Bot, Dispatcher, types, F
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup,
    KeyboardButton, CallbackQuery, Message, LabeledPrice, PreCheckoutQuery
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# ========== КОНФИГ ==========
BOT_TOKEN = "8724279434:AAGtxMmPlEly-z8AGs8GDjT3zgxTNE40pt4"
CRYPTOBOT_TOKEN = "595344:AAvNd6KMeDX1Thp5xd9T5csPIp7sOXGmgzY"
ADMIN_IDS = [7966949924]
SUPPORT_USERNAME = "theid777"

# НАСТРОЙКИ СЕРВЕРА (ОБЯЗАТЕЛЬНО ЗАПОЛНИТЬ!)
RCON_HOST = "127.0.0.1"      # IP сервера
RCON_PORT = 25575             # Порт RCON (обычно 25575)
RCON_PASSWORD = "ваш_пароль"  # Пароль от RCON

RUB_TO_USD = 0.013

# ТОВАРЫ
PRODUCTS = {
    "baron": {"name": "Барон", "price": 19, "cmd": "lp user {nick} parent set baron"},
    "straj": {"name": "Страж", "price": 29, "cmd": "lp user {nick} parent set straj"},
    "hero": {"name": "Герой", "price": 37, "cmd": "lp user {nick} parent set hero"},
    "aspid": {"name": "Аспид", "price": 55, "cmd": "lp user {nick} parent set aspid"},
    "skvid": {"name": "Сквид", "price": 79, "cmd": "lp user {nick} parent set skvid"},
    "glava": {"name": "Глава", "price": 99, "cmd": "lp user {nick} parent set glava"},
    "elita": {"name": "Элита", "price": 119, "cmd": "lp user {nick} parent set elita"},
    "titan": {"name": "Титан", "price": 138, "cmd": "lp user {nick} parent set titan"},
    "prince": {"name": "Принц", "price": 177, "cmd": "lp user {nick} parent set prince"},
    "knyaz": {"name": "Князь", "price": 219, "cmd": "lp user {nick} parent set knyaz"},
    "gercog": {"name": "Герцог", "price": 333, "cmd": "lp user {nick} parent set gercog"},
    "donate_case": {"name": "Донат кейс", "price": 67, "cmd": "cubelets give {nick} donate 1"},
}

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# ========== СОСТОЯНИЯ ==========
class BuyState(StatesGroup):
    waiting_nick = State()
    waiting_payment = State()

class PromoState(StatesGroup):
    waiting_code = State()

class AdminState(StatesGroup):
    waiting_promo_code = State()
    waiting_promo_discount = State()
    waiting_promo_limit = State()

# ========== БАЗА ДАННЫХ ==========
def init_db():
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute('''CREATE TABLE IF NOT EXISTS users (
        uid INTEGER PRIMARY KEY,
        username TEXT,
        last_nick TEXT
    )''')
    cur.execute('''CREATE TABLE IF NOT EXISTS purchases (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        uid INTEGER,
        item_key TEXT,
        item_name TEXT,
        price REAL,
        nick TEXT,
        status TEXT DEFAULT 'pending',
        invoice_id TEXT,
        created_at TEXT
    )''')
    cur.execute('''CREATE TABLE IF NOT EXISTS promocodes (
        code TEXT PRIMARY KEY,
        discount INTEGER,
        max_uses INTEGER,
        used_count INTEGER DEFAULT 0
    )''')
    cur.execute('''CREATE TABLE IF NOT EXISTS promo_used (
        code TEXT,
        uid INTEGER
    )''')
    conn.commit()
    conn.close()

init_db()

def get_user(uid: int) -> Dict:
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE uid = ?", (uid,))
    u = cur.fetchone()
    conn.close()
    if not u:
        conn = sqlite3.connect('shop.db')
        cur = conn.cursor()
        cur.execute("INSERT INTO users (uid, username) VALUES (?, ?)", (uid, ""))
        conn.commit()
        conn.close()
        return {"uid": uid, "username": "", "last_nick": None}
    return {"uid": u[0], "username": u[1] or "", "last_nick": u[2]}

def update_last_nick(uid: int, nick: str):
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute("UPDATE users SET last_nick = ? WHERE uid = ?", (nick, uid))
    conn.commit()
    conn.close()

def upd_username(uid: int, name: str):
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute("UPDATE users SET username = ? WHERE uid = ?", (name, uid))
    conn.commit()
    conn.close()

def save_purchase(uid: int, item_key: str, item_name: str, price: float, nick: str, inv_id: str = ""):
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute("INSERT INTO purchases (uid, item_key, item_name, price, nick, invoice_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
               (uid, item_key, item_name, price, nick, inv_id, datetime.now()))
    conn.commit()
    conn.close()

def update_payment_status(inv_id: str, status: str):
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute("UPDATE purchases SET status = ? WHERE invoice_id = ?", (status, inv_id))
    conn.commit()
    conn.close()

def get_purchase_by_invoice(inv_id: str) -> Dict:
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute("SELECT uid, item_key, item_name, price, nick FROM purchases WHERE invoice_id = ?", (inv_id,))
    r = cur.fetchone()
    conn.close()
    if r:
        return {"uid": r[0], "item_key": r[1], "item_name": r[2], "price": r[3], "nick": r[4]}
    return None

def get_pending_purchase(uid: int) -> Dict:
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute("SELECT item_key, item_name, price, nick FROM purchases WHERE uid = ? AND status = 'pending' ORDER BY id DESC LIMIT 1", (uid,))
    r = cur.fetchone()
    conn.close()
    if r:
        return {"item_key": r[0], "item_name": r[1], "price": r[2], "nick": r[3]}
    return None

def complete_purchase(uid: int, item_key: str):
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute("UPDATE purchases SET status = 'completed' WHERE uid = ? AND item_key = ? AND status = 'pending'", (uid, item_key))
    conn.commit()
    conn.close()

def get_discount(uid: int, code: str) -> int:
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute("SELECT discount, max_uses, used_count FROM promocodes WHERE code = ?", (code,))
    p = cur.fetchone()
    if not p:
        conn.close()
        return 0
    discount, max_uses, used = p
    if max_uses > 0 and used >= max_uses:
        conn.close()
        return 0
    cur.execute("SELECT 1 FROM promo_used WHERE code = ? AND uid = ?", (code, uid))
    if cur.fetchone():
        conn.close()
        return 0
    conn.close()
    return discount

def use_promo(uid: int, code: str):
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute("INSERT INTO promo_used VALUES (?, ?)", (code, uid))
    cur.execute("UPDATE promocodes SET used_count = used_count + 1 WHERE code = ?", (code,))
    conn.commit()
    conn.close()

def create_promo(code: str, discount: int, max_uses: int):
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute("INSERT OR REPLACE INTO promocodes (code, discount, max_uses) VALUES (?, ?, ?)", (code, discount, max_uses))
    conn.commit()
    conn.close()

# ========== RCON ВЫДАЧА (ГАРАНТИРОВАННАЯ) ==========
import struct

class RCONClient:
    def __init__(self, host: str, port: int, password: str):
        self.host = host
        self.port = port
        self.password = password
        self.reader = None
        self.writer = None
    
    async def connect(self):
        try:
            self.reader, self.writer = await asyncio.open_connection(self.host, self.port, timeout=5)
            await self._send(3, self.password)
            response = await self._read()
            if response[0] == -1:
                return False
            return True
        except Exception as e:
            logging.error(f"RCON connect error: {e}")
            return False
    
    async def _send(self, packet_type: int, body: str):
        packet_id = int(datetime.now().timestamp())
        body_bytes = body.encode('utf-8')
        packet = struct.pack('<ii', packet_id, packet_type) + body_bytes + b'\x00\x00'
        self.writer.write(struct.pack('<i', len(packet)) + packet)
        await self.writer.drain()
    
    async def _read(self):
        try:
            length_data = await self.reader.read(4)
            if not length_data:
                return (-1, None)
            length = struct.unpack('<i', length_data)[0]
            data = await self.reader.read(length)
            packet_id, packet_type = struct.unpack('<ii', data[:8])
            body = data[8:-2].decode('utf-8')
            return (packet_id, body)
        except:
            return (-1, None)
    
    async def execute(self, command: str) -> str:
        await self._send(2, command)
        response = await self._read()
        return response[1] if response[1] else "OK"
    
    async def close(self):
        if self.writer:
            self.writer.close()
            await self.writer.wait_closed()

async def give_to_server(nick: str, command_template: str) -> tuple:
    """
    Выдаёт товар на сервер через RCON
    Возвращает (успех, сообщение)
    """
    if not nick:
        return (False, "Ник не указан")
    
    if not command_template:
        return (False, "Команда не найдена")
    
    cmd = command_template.format(nick=nick)
    
    logging.info(f"📤 Отправка RCON команды: {cmd}")
    
    try:
        rcon = RCONClient(RCON_HOST, RCON_PORT, RCON_PASSWORD)
        if not await rcon.connect():
            return (False, "Не удалось подключиться к серверу")
        
        result = await rcon.execute(cmd)
        await rcon.close()
        
        logging.info(f"✅ RCON ответ: {result}")
        return (True, result)
    except Exception as e:
        logging.error(f"❌ RCON ошибка: {e}")
        return (False, str(e))

# ========== КЛАВИАТУРЫ ==========
main_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🛒 Магазин"), KeyboardButton(text="👤 Профиль")],
        [KeyboardButton(text="🎁 Промокод"), KeyboardButton(text="❓ Помощь")]
    ],
    resize_keyboard=True
)

def shop_kb(discount: int = 0):
    b = []
    for key, p in PRODUCTS.items():
        if discount > 0:
            new_price = int(p["price"] * (100 - discount) / 100)
            b.append([InlineKeyboardButton(text=f"{p['name']} — {new_price}₽ (скидка {discount}%)", callback_data=f"buy_{key}_{discount}")])
        else:
            b.append([InlineKeyboardButton(text=f"{p['name']} — {p['price']}₽", callback_data=f"buy_{key}_0")])
    return InlineKeyboardMarkup(inline_keyboard=b)

def pay_kb(item_key: str, price: float, discount: int):
    usd = price * RUB_TO_USD
    stars = int(usd / 0.011)
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💎 CryptoBot (USDT)", callback_data=f"crypto_{item_key}_{price}_{discount}")],
        [InlineKeyboardButton(text="⭐ Telegram Stars", callback_data=f"stars_{item_key}_{stars}_{price}_{discount}")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back")]
    ])

def cancel_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_buy")]
    ])

# ========== ОСНОВНЫЕ ОБРАБОТЧИКИ ==========
@dp.message(Command("start"))
async def start(msg: Message):
    if msg.from_user.username:
        upd_username(msg.from_user.id, msg.from_user.username)
    get_user(msg.from_user.id)
    await msg.answer(
        f"🎮 Добро пожаловать в магазин!\n\n"
        f"🛒 Привилегии и донат кейсы\n"
        f"📖 Описание: https://t.me/PitaiaTime/3114\n"
        f"👤 Поддержка: @{SUPPORT_USERNAME}",
        reply_markup=main_kb
    )

@dp.message(F.text == "🛒 Магазин")
async def shop(msg: Message, state: FSMContext):
    await state.clear()
    await msg.answer("🛒 Выберите товар:", reply_markup=shop_kb())

@dp.message(F.text == "👤 Профиль")
async def profile(msg: Message):
    u = get_user(msg.from_user.id)
    await msg.answer(f"👤 Профиль\n\n🆔 ID: {u['uid']}\n🎮 Последний ник: {u['last_nick'] or 'не указан'}")

@dp.message(F.text == "❓ Помощь")
async def help_msg(msg: Message):
    await msg.answer(
        f"❓ Помощь\n\n"
        f"🛒 Магазин - покупка привилегий и кейсов\n"
        f"🎁 Промокод - активация скидки\n"
        f"👤 Профиль - ваш ID и последний ник\n\n"
        f"📖 Описание: https://t.me/PitaiaTime/3114\n"
        f"👤 Поддержка: @{SUPPORT_USERNAME}"
    )

@dp.message(F.text == "🎁 Промокод")
async def promo_start(msg: Message, state: FSMContext):
    await msg.answer("🎁 Введите промокод:")
    await state.set_state(PromoState.waiting_code)

@dp.message(PromoState.waiting_code)
async def promo_use(msg: Message, state: FSMContext):
    code = msg.text.upper()
    discount = get_discount(msg.from_user.id, code)
    
    if discount == 0:
        await msg.answer("❌ Промокод недействителен или уже использован!")
        await state.clear()
        return
    
    use_promo(msg.from_user.id, code)
    await msg.answer(f"✅ Промокод активирован! Скидка {discount}%")
    await msg.answer("🛒 Выберите товар со скидкой:", reply_markup=shop_kb(discount))
    await state.clear()

# ========== ПОКУПКА ==========
@dp.callback_query(F.data.startswith("buy_"))
async def start_buy(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    item_key = parts[1]
    discount = int(parts[2])
    
    product = PRODUCTS.get(item_key)
    if not product:
        await callback.answer("❌ Товар не найден!")
        return
    
    final_price = int(product["price"] * (100 - discount) / 100) if discount > 0 else product["price"]
    
    await state.update_data(item_key=item_key, discount=discount, final_price=final_price)
    
    user = get_user(callback.from_user.id)
    last_nick = user.get("last_nick")
    
    text = f"💰 {product['name']}\nЦена: {final_price}₽"
    if discount > 0:
        text += f"\n🎁 Скидка: {discount}%"
    
    text += f"\n\n🎮 Введите ваш ник на сервере:"
    if last_nick:
        text += f"\n(последний ник: {last_nick})"
    
    await callback.message.edit_text(text, reply_markup=cancel_kb())
    await state.set_state(BuyState.waiting_nick)
    await callback.answer()

@dp.message(BuyState.waiting_nick)
async def get_nick(msg: Message, state: FSMContext):
    nick = msg.text.strip()
    if len(nick) < 2 or len(nick) > 16:
        await msg.answer("❌ Ник должен быть от 2 до 16 символов!\nВведите ещё раз:")
        return
    
    data = await state.get_data()
    item_key = data["item_key"]
    discount = data["discount"]
    final_price = data["final_price"]
    
    product = PRODUCTS[item_key]
    
    # Сохраняем ник
    update_last_nick(msg.from_user.id, nick)
    
    await state.update_data(nick=nick)
    
    await msg.answer(
        f"✅ Ник принят: {nick}\n\n"
        f"📦 {product['name']}\n"
        f"💰 Цена: {final_price}₽\n\n"
        f"💳 Выберите способ оплаты:",
        reply_markup=pay_kb(item_key, final_price, discount)
    )
    await state.set_state(BuyState.waiting_payment)

@dp.callback_query(F.data == "cancel_buy")
async def cancel_buy(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Покупка отменена")
    await callback.answer()

# ========== CRYPTOBOT ОПЛАТА ==========
@dp.callback_query(F.data.startswith("crypto_"))
async def pay_crypto(callback: CallbackQuery, state: FSMContext):
    _, item_key, price, discount = callback.data.split("_")
    price = float(price)
    
    data = await state.get_data()
    nick = data.get("nick")
    product = PRODUCTS.get(item_key)
    
    if not nick:
        await callback.answer("❌ Ошибка: ник не указан!")
        return
    
    usd = round(price * RUB_TO_USD, 2)
    
    url = "https://pay.crypt.bot/api/createInvoice"
    headers = {"Crypto-Pay-API-Token": CRYPTOBOT_TOKEN}
    body = {"asset": "USDT", "amount": str(usd)}
    
    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=body, timeout=30) as resp:
            res = await resp.json()
            if res.get("ok"):
                inv_url = res["result"]["bot_invoice_url"]
                inv_id = str(res["result"]["invoice_id"])
                
                save_purchase(callback.from_user.id, item_key, product["name"], price, nick, inv_id)
                
                await callback.message.edit_text(
                    f"💳 Счёт создан!\n\n"
                    f"📦 {product['name']}\n"
                    f"🎮 Ник: {nick}\n"
                    f"💰 Сумма: ${usd} USDT\n\n"
                    f"🔗 <a href='{inv_url}'>Оплатить</a>\n\n"
                    f"✅ После оплаты нажмите кнопку:",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="✅ Проверить оплату", callback_data=f"check_{inv_id}")]
                    ]),
                    parse_mode=ParseMode.HTML
                )
            else:
                await callback.message.answer("❌ Ошибка создания счёта!\nПопробуйте позже.")
    await callback.answer()
    await state.clear()

@dp.callback_query(F.data.startswith("check_"))
async def check_payment(callback: CallbackQuery):
    inv_id = callback.data.split("_")[1]
    
    url = "https://pay.crypt.bot/api/getInvoices"
    headers = {"Crypto-Pay-API-Token": CRYPTOBOT_TOKEN}
    params = {"invoice_id": inv_id}
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers, params=params, timeout=30) as resp:
            res = await resp.json()
            if res.get("ok") and res["result"]["items"]:
                inv = res["result"]["items"][0]
                if inv.get("status") == "paid":
                    update_payment_status(inv_id, "completed")
                    purchase = get_purchase_by_invoice(inv_id)
                    
                    if purchase:
                        product = PRODUCTS.get(purchase["item_key"])
                        if product:
                            # ГАРАНТИРОВАННАЯ ВЫДАЧА
                            success, result = await give_to_server(purchase["nick"], product["cmd"])
                            
                            if success:
                                await callback.message.edit_text(
                                    f"✅ ОПЛАТА ПОДТВЕРЖДЕНА!\n\n"
                                    f"📦 {product['name']}\n"
                                    f"🎮 Ник: {purchase['nick']}\n"
                                    f"✅ Товар выдан на сервер!\n\n"
                                    f"🎮 Приятной игры!"
                                )
                                await callback.answer("✅ Выдано успешно!", show_alert=True)
                            else:
                                await callback.message.edit_text(
                                    f"⚠️ ОПЛАТА ПОДТВЕРЖДЕНА!\n\n"
                                    f"📦 {product['name']}\n"
                                    f"🎮 Ник: {purchase['nick']}\n"
                                    f"❌ Ошибка выдачи: {result}\n\n"
                                    f"📞 Свяжитесь с @{SUPPORT_USERNAME} и сообщите этот ник!"
                                )
                        else:
                            await callback.message.answer("❌ Товар не найден!")
                    else:
                        await callback.message.answer("❌ Платёж не найден в базе!")
                else:
                    await callback.answer("⏳ Платёж ещё не оплачен! Оплатите и нажмите снова.", show_alert=True)
            else:
                await callback.answer("❌ Ошибка проверки платежа!", show_alert=True)
    await callback.answer()

# ========== STARS ОПЛАТА ==========
@dp.callback_query(F.data.startswith("stars_"))
async def pay_stars(callback: CallbackQuery, state: FSMContext):
    _, item_key, stars, price, discount = callback.data.split("_")
    stars = int(stars)
    price = float(price)
    
    data = await state.get_data()
    nick = data.get("nick")
    product = PRODUCTS.get(item_key)
    
    if not nick:
        await callback.answer("❌ Ошибка: ник не указан!")
        return
    
    # Сохраняем покупку
    save_purchase(callback.from_user.id, item_key, product["name"], price, nick, f"stars_{callback.from_user.id}")
    
    await callback.message.answer_invoice(
        title=f"Покупка {product['name']}",
        description=f"Ник: {nick}\nЦена: {price}₽",
        payload=f"stars_{item_key}_{price}_{nick}",
        currency="XTR",
        prices=[LabeledPrice(label=product['name'], amount=stars)],
        provider_token=""
    )
    await callback.answer()
    await state.clear()

@dp.pre_checkout_query()
async def pre_checkout(q: PreCheckoutQuery):
    await q.answer(ok=True)

@dp.message(F.successful_payment)
async def stars_success(msg: Message):
    payload = msg.successful_payment.invoice_payload
    parts = payload.split("_")
    item_key = parts[1]
    price = float(parts[2])
    nick = parts[3]
    
    product = PRODUCTS.get(item_key)
    
    if product:
        # ГАРАНТИРОВАННАЯ ВЫДАЧА
        success, result = await give_to_server(nick, product["cmd"])
        
        if success:
            await msg.answer(
                f"✅ ОПЛАТА ПОДТВЕРЖДЕНА!\n\n"
                f"📦 {product['name']}\n"
                f"🎮 Ник: {nick}\n"
                f"✅ Товар выдан на сервер!\n\n"
                f"🎮 Приятной игры!"
            )
        else:
            await msg.answer(
                f"⚠️ ОПЛАТА ПОДТВЕРЖДЕНА!\n\n"
                f"📦 {product['name']}\n"
                f"🎮 Ник: {nick}\n"
                f"❌ Ошибка выдачи: {result}\n\n"
                f"📞 Свяжитесь с @{SUPPORT_USERNAME} и сообщите этот ник!"
            )
    else:
        await msg.answer("❌ Товар не найден!")

@dp.callback_query(F.data == "back")
async def back(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("🛒 Выберите товар:", reply_markup=shop_kb())
    await callback.answer()

# ========== АДМИН КОМАНДЫ ==========
@dp.message(Command("admin"))
async def admin_panel(msg: Message):
    if msg.from_user.id not in ADMIN_IDS:
        return
    await msg.answer(
        "👑 АДМИН ПАНЕЛЬ\n\n"
        "🔧 Команды:\n"
        "/create_promo КОД СКИДКА ЛИМИТ - создать промокод\n"
        "/test_rcon - проверить подключение к серверу\n"
        "/give НИК ТОВАР - выдать вручную\n"
        "/stats - статистика"
    )

@dp.message(Command("create_promo"))
async def create_promo_cmd(msg: Message):
    if msg.from_user.id not in ADMIN_IDS:
        return
    try:
        parts = msg.text.split()
        code = parts[1].upper()
        discount = int(parts[2])
        limit = int(parts[3])
        
        if discount < 1 or discount > 99:
            await msg.answer("❌ Скидка от 1 до 99%")
            return
        
        create_promo(code, discount, limit)
        await msg.answer(f"✅ Промокод {code} создан!\nСкидка: {discount}%\nЛимит: {limit}")
    except:
        await msg.answer("❌ Формат: /create_promo КОД СКИДКА ЛИМИТ")

@dp.message(Command("test_rcon"))
async def test_rcon(msg: Message):
    if msg.from_user.id not in ADMIN_IDS:
        return
    await msg.answer("🔄 Проверка подключения к серверу...")
    success, result = await give_to_server("test", "list")
    if success:
        await msg.answer(f"✅ Подключение работает!\nОтвет: {result[:100]}")
    else:
        await msg.answer(f"❌ Ошибка подключения!\n{result}")

@dp.message(Command("give"))
async def manual_give(msg: Message):
    if msg.from_user.id not in ADMIN_IDS:
        return
    try:
        parts = msg.text.split()
        nick = parts[1]
        item_key = parts[2]
        
        product = PRODUCTS.get(item_key)
        if not product:
            await msg.answer(f"❌ Товар {item_key} не найден!\nДоступные: {', '.join(PRODUCTS.keys())}")
            return
        
        success, result = await give_to_server(nick, product["cmd"])
        if success:
            await msg.answer(f"✅ Выдано {product['name']} игроку {nick}!")
        else:
            await msg.answer(f"❌ Ошибка: {result}")
    except:
        await msg.answer("❌ Формат: /give НИК ТОВАР\nПример: /give Player123 baron")

@dp.message(Command("stats"))
async def stats(msg: Message):
    if msg.from_user.id not in ADMIN_IDS:
        return
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users")
    users = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM purchases WHERE status = 'completed'")
    purchases = cur.fetchone()[0]
    cur.execute("SELECT SUM(price) FROM purchases WHERE status = 'completed'")
    total = cur.fetchone()[0] or 0
    conn.close()
    
    await msg.answer(
        f"📊 СТАТИСТИКА\n\n"
        f"👥 Пользователей: {users}\n"
        f"🛒 Покупок: {purchases}\n"
        f"💰 Доход: {total:.0f}₽"
    )

# ========== ЗАПУСК ==========
async def main():
    await bot.set_my_commands([
        Command(command="start", description="🚀 Запуск"),
        Command(command="admin", description="👑 Админ панель"),
    ])
    
    logging.info("✅ Бот запущен!")
    logging.info(f"📡 RCON: {RCON_HOST}:{RCON_PORT}")
    
    # Проверяем RCON при старте
    success, result = await give_to_server("test", "list")
    if success:
        logging.info("✅ RCON подключение работает!")
    else:
        logging.warning(f"⚠️ RCON не работает! {result}")
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    asyncio.run(main())