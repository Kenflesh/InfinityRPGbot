import asyncio
import random
import time
import re
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from config import *
from database import Database

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
db = Database()

# --- FSM STATES ---
class GameStates(StatesGroup):
    waiting_for_action = State()
    waiting_for_difficulty = State()
    waiting_for_cancel = State()

# --- ГЕЙМ ЛОГИКА ---

def check_lock(user):
    now = int(time.time())
    if now < user['death_until']:
        return f"💀 Вы мертвы. Воскрешение через {int((user['death_until'] - now)/60)} мин."
    if now < user['lock_until']:
        return f"⏳ Вы заняты. Ожидание {int((user['lock_until'] - now)/60)} мин."
    return None

def calc_stat_level(current_val, base_val, growth):
    if growth == 0: return 0
    return int((current_val - base_val) / growth)

def get_upgrade_cost(stat_name, user_stats):
    base = BASE_STATS[stat_name]
    current = user_stats.get(stat_name, base)
    growth = STAT_GROWTH[stat_name]
    level = calc_stat_level(current, base, growth)
    return TRAINING_BASE_COST + (level * TRAINING_COST_STEP)

def generate_enemy(difficulty_multiplier):
    template = random.choice(ENEMIES)
    scale = 1 + (difficulty_multiplier * 0.5)
    enemy = {
        "name": template["name"],
        "hp": int(template["base_hp"] * scale),
        "max_hp": int(template["base_hp"] * scale),
        "dmg": int(template["base_dmg"] * scale),
        "def": int(5 * scale),  # Добавил защиту врагу
        "gold": random.randint(template["gold_min"], template["gold_max"]) * int(scale)
    }
    return enemy

def simulate_combat(player, enemy):
    logs = []
    p_hp = player['stats'].get('hp', 100)
    e_hp = enemy['hp']
    turn = 0
    
    dmg_bonus = 0
    def_bonus = 0
    for slot, item in player.get('equipped', {}).items():
        if item:
            dmg_bonus += item.get('stats', {}).get('dmg', 0)
            def_bonus += item.get('stats', {}).get('def', 0)
            
    # Безопасное получение статов с дефолтными значениями
    p_dmg = player['stats'].get('dmg', 10) + dmg_bonus
    p_def = player['stats'].get('def', 5) + def_bonus
    p_crit = player['stats'].get('crit_chance', 5)
    p_dodge = player['stats'].get('dodge_chance', 5)

    while p_hp > 0 and e_hp > 0 and turn < 50:
        turn += 1
        # Ход игрока
        is_crit = random.randint(1, 100) <= p_crit
        dmg_dealt = max(1, (p_dmg * (2 if is_crit else 1)) - enemy.get('def', 0))
        e_hp -= dmg_dealt
        logs.append(f"⚔️ Вы нанесли {dmg_dealt} урона{' (КРИТ!)' if is_crit else ''}. Враг HP: {max(0, e_hp)}")
        
        if e_hp <= 0: break

        # Ход врага
        is_dodge = random.randint(1, 100) <= p_dodge
        if is_dodge:
            logs.append(f"💨 Вы уклонились от атаки {enemy['name']}!")
        else:
            dmg_rec = max(0, enemy['dmg'] - p_def)
            p_hp -= dmg_rec
            logs.append(f"🛡️ {enemy['name']} атакует. Вы получили {dmg_rec} урона. Ваше HP: {max(0, p_hp)}")
            
    return p_hp > 0, logs, p_hp

def generate_item(player_rarity):
    types_ru = {"weapon": "Оружие", "armor": "Броня", "accessory": "Аксессуар"}
    itype = random.choice(list(types_ru.keys()))
    rarity_roll = random.randint(1, 100) + player_rarity
    
    quality = "Обычное"
    mult = 1
    if rarity_roll > 90: quality, mult = "Легендарное", 5
    elif rarity_roll > 70: quality, mult = "Эпическое", 3
    elif rarity_roll > 50: quality, mult = "Редкое", 2
    
    stats = {}
    if itype == "weapon": stats['dmg'] = random.randint(5, 15) * mult
    if itype == "armor": stats['def'] = random.randint(5, 15) * mult
    if itype == "accessory": stats['hp'] = random.randint(20, 50) * mult
    
    return {
        "name": f"{quality} {types_ru[itype]}",
        "type": itype,
        "quality": quality,
        "stats": stats,
        "level": 1
    }

# --- КЛАВИАТУРЫ ---

def main_menu_kb():
    kb = [
        [InlineKeyboardButton(text="⚔️ Бой", callback_data="menu_fight"), InlineKeyboardButton(text="🧘 Прокачка", callback_data="menu_train")],
        [InlineKeyboardButton(text="🎒 Инвентарь", callback_data="menu_inv"), InlineKeyboardButton(text="🏪 Магазин", callback_data="menu_shop")],
        [InlineKeyboardButton(text="📜 Способности", callback_data="menu_skills"), InlineKeyboardButton(text="🧘‍♂️ Медитация", callback_data="menu_meditate")],
        [InlineKeyboardButton(text="👤 Профиль", callback_data="menu_profile")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def train_kb():
    kb = []
    row = []
    for stat, name in STAT_NAMES_RU.items():
        row.append(InlineKeyboardButton(text=f"{name}", callback_data=f"train_{stat}"))
        if len(row) == 2:
            kb.append(row)
            row = []
    if row: kb.append(row)
    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data="menu_back")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def fight_kb(difficulty):
    kb = [
        [InlineKeyboardButton(text="◀️", callback_data="fight_diff_down"), 
         InlineKeyboardButton(text=f"Сложность: {difficulty}", callback_data="fight_diff_input"), 
         InlineKeyboardButton(text="▶️", callback_data="fight_diff_up")],
        [InlineKeyboardButton(text="⚔️ Атаковать", callback_data="fight_start"), 
         InlineKeyboardButton(text="🔙 Назад", callback_data="menu_back")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def cancel_kb():
    kb = [[InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_action")]]
    return InlineKeyboardMarkup(inline_keyboard=kb)

# --- HANDLERS ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await db.connect()
    user = await db.get_user(message.from_user.id)
    lock_msg = check_lock(user)
    if lock_msg:
        await message.answer(f"🔒 {lock_msg}")
    else:
        await message.answer(f"👋 Добро пожаловать в RPG Бот!\n💰 Золото: {user['gold']}", reply_markup=main_menu_kb())

@dp.callback_query(F.data == "menu_back")
async def back_menu(call: types.CallbackQuery):
    await dp.storage.set_state(call.from_user.id, None)
    user = await db.get_user(call.from_user.id)
    lock_msg = check_lock(user)
    text = f"📊 💰 Золото: {user['gold']}\n❤️ HP: {user['stats']['hp']}"
    if lock_msg: text += f"\n⚠️ {lock_msg}"
    await call.message.edit_text(text, reply_markup=main_menu_kb())

@dp.callback_query(F.data == "menu_profile")
async def profile(call: types.CallbackQuery):
    user = await db.get_user(call.from_user.id)
    stats_text = "\n".join([f"{STAT_NAMES_RU.get(k, k)}: {v}" for k, v in user['stats'].items()])
    equip_text = "\n".join([f"{k}: {v['name']}" for k, v in user['equipped'].items() if v])
    await call.message.edit_text(f"👤 Профиль\n\n📈 Характеристики:\n{stats_text}\n\n🎒 Экипировка:\n{equip_text if equip_text else 'Пусто'}", reply_markup=main_menu_kb())

# --- ПРОКАЧКА ---

@dp.callback_query(F.data == "menu_train")
async def train_menu(call: types.CallbackQuery):
    user = await db.get_user(call.from_user.id)
    lock = check_lock(user)
    if lock:
        await call.answer(lock, show_alert=True)
        return
    await call.message.edit_text("📈 Выберите характеристику для улучшения:", reply_markup=train_kb())

@dp.callback_query(F.data.startswith("train_"))
async def train_stat(call: types.CallbackQuery, state: FSMContext):
    user = await db.get_user(call.from_user.id)
    lock = check_lock(user)
    if lock:
        await call.answer(lock, show_alert=True)
        return

    stat = call.data.split("_")[1]
    cost = get_upgrade_cost(stat, user['stats'])
    stat_name_ru = STAT_NAMES_RU.get(stat, stat)
    
    if user['gold'] >= cost:
        # Сохраняем информацию о текущей прокачке для отмены
        await state.update_data(training_stat=stat, training_cost=cost)
        await state.set_state(GameStates.waiting_for_cancel)
        
        await call.message.edit_text(f"⏳ Прокачка {stat_name_ru} началась!\nСписано {cost} золота.\nВремя: 10 мин.\n\n❌ Нажмите 'Отменить' чтобы прервать.", reply_markup=cancel_kb())
        
        # Запускаем таймер в фоне
        asyncio.create_task(training_timer(call.from_user.id, stat, cost))
    else:
        await call.answer(f"💰 Недостаточно золота! Нужно {cost}", show_alert=True)

async def training_timer(user_id, stat, cost):
    await asyncio.sleep(TRAINING_TIME_SECONDS)
    user = await db.get_user(user_id)
    # Проверяем не отменил ли игрок
    if user['lock_until'] > int(time.time()) - TRAINING_TIME_SECONDS + 60:
        new_val = user['stats'][stat] + STAT_GROWTH[stat]
        user['stats'][stat] = new_val
        await db.update_user(user_id, stats=user['stats'])
        # Разблокируем
        await db.update_user(user_id, lock_until=0)
        await dp.storage.set_state(user_id, None)

@dp.callback_query(F.data == "cancel_action")
async def cancel_action(call: types.CallbackQuery):
    user = await db.get_user(call.from_user.id)
    data = await dp.storage.get_data(call.from_user.id)
    
    # Возвращаем золото если была прокачка
    if 'training_cost' in data:
        await db.update_user(user['user_id'], gold=user['gold'] + data['training_cost'], lock_until=0)
        await call.answer("✅ Прокачка отменена, золото возвращено", show_alert=True)
    
    await dp.storage.set_state(call.from_user.id, None)
    await back_menu(call)

# --- БОЙ ---

@dp.callback_query(F.data == "menu_fight")
async def fight_menu(call: types.CallbackQuery, state: FSMContext):
    user = await db.get_user(call.from_user.id)
    lock = check_lock(user)
    if lock:
        await call.answer(lock, show_alert=True)
        return
    
    data = await state.get_data()
    diff = data.get("difficulty", 1)
    
    await call.message.edit_text(f"⚔️ Арена Боя\n📊 Сложность: {diff}\n\nВыберите действие:", reply_markup=fight_kb(diff))

@dp.callback_query(F.data == "fight_diff_up")
async def fight_diff_up(call: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    diff = data.get("difficulty", 1)
    new_diff = min(diff + 1, 100)
    await state.update_data(difficulty=new_diff)
    await fight_menu(call, state)

@dp.callback_query(F.data == "fight_diff_down")
async def fight_diff_down(call: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    diff = data.get("difficulty", 1)
    new_diff = max(diff - 1, 1)
    await state.update_data(difficulty=new_diff)
    await fight_menu(call, state)

@dp.callback_query(F.data == "fight_diff_input")
async def fight_diff_input(call: types.CallbackQuery, state: FSMContext):
    await state.set_state(GameStates.waiting_for_difficulty)
    await call.message.edit_text("🔢 Введите число сложности (1-100):", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="menu_fight")]]))

@dp.message(GameStates.waiting_for_difficulty)
async def set_difficulty(message: types.Message, state: FSMContext):
    try:
        new_diff = int(message.text)
        if 1 <= new_diff <= 100:
            await state.update_data(difficulty=new_diff)
            await state.set_state(None)
            await message.answer(f"✅ Сложность установлена: {new_diff}", reply_markup=main_menu_kb())
        else:
            await message.answer("❌ Число должно быть от 1 до 100")
    except ValueError:
        await message.answer("❌ Введите корректное число")

@dp.callback_query(F.data == "fight_start")
async def fight_start(call: types.CallbackQuery, state: FSMContext):
    user = await db.get_user(call.from_user.id)
    lock = check_lock(user)
    if lock:
        await call.answer(lock, show_alert=True)
        return

    data = await state.get_data()
    diff = data.get("difficulty", 1)
    enemy = generate_enemy(diff)
    
    lock_time = int(time.time()) + 30
    await db.update_user(user['user_id'], lock_until=lock_time)
    
    await call.message.edit_text(f"⚔️ Бой начался!\n👹 Враг: {enemy['name']}