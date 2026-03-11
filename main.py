import asyncio
import random
import time
import re
import json
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
        "def": int(5 * scale),
        "gold": random.randint(template["gold_min"], template["gold_max"]) * int(scale)
    }
    return enemy

def simulate_combat(player, enemy):
    logs = []
    p_hp = player['stats'].get('hp', 100)
    p_hp_max = player['stats'].get('hp', 100)
    e_hp = enemy['hp']
    e_hp_max = enemy['hp']
    turn = 0
    
    dmg_bonus = 0
    def_bonus = 0
    for slot, item in player.get('equipped', {}).items():
        if item:
            dmg_bonus += item.get('stats', {}).get('dmg', 0)
            def_bonus += item.get('stats', {}).get('def', 0)
            
    p_dmg = player['stats'].get('dmg', 10) + dmg_bonus
    p_def = player['stats'].get('def', 5) + def_bonus
    p_crit = player['stats'].get('crit_chance', 5)
    p_dodge = player['stats'].get('dodge_chance', 5)

    while p_hp > 0 and e_hp > 0 and turn < 50:
        turn += 1
        is_crit = random.randint(1, 100) <= p_crit
        dmg_dealt = max(1, (p_dmg * (2 if is_crit else 1)) - enemy.get('def', 0))
        e_hp_before = e_hp
        e_hp -= dmg_dealt
        e_hp = max(0, e_hp)
        
        crit_text = " (КРИТ!)" if is_crit else ""
        logs.append({
            "type": "player",
            "dmg": dmg_dealt,
            "enemy_hp": e_hp,
            "enemy_hp_max": e_hp_max,
            "crit": is_crit
        })
        
        if e_hp <= 0:
            logs.append({"type": "win"})
            break

        is_dodge = random.randint(1, 100) <= p_dodge
        if is_dodge:
            logs.append({
                "type": "dodge",
                "enemy_name": enemy['name']
            })
        else:
            dmg_rec = max(0, enemy['dmg'] - p_def)
            p_hp_before = p_hp
            p_hp -= dmg_rec
            p_hp = max(0, p_hp)
            logs.append({
                "type": "enemy",
                "dmg": dmg_rec,
                "player_hp": p_hp,
                "player_hp_max": p_hp_max,
                "enemy_name": enemy['name']
            })
            
        if p_hp <= 0:
            logs.append({"type": "death"})
            break
            
    return p_hp > 0, logs, p_hp

def format_item_name(item):
    """Форматирует название предмета с правильным родом"""
    quality = item['quality']
    itype = item['type']
    
    # Род для качества
    if itype == "weapon":
        quality_adj = "Обычное" if quality == "Обычное" else "Редкое" if quality == "Редкое" else "Эпическое" if quality == "Эпическое" else "Легендарное"
        type_name = "Оружие"
    elif itype == "armor":
        quality_adj = "Обычная" if quality == "Обычное" else "Редкая" if quality == "Редкое" else "Эпическая" if quality == "Эпическое" else "Легендарная"
        type_name = "Броня"
    else:  # accessory
        quality_adj = "Обычный" if quality == "Обычное" else "Редкий" if quality == "Редкое" else "Эпический" if quality == "Эпическое" else "Легендарный"
        type_name = "Аксессуар"
    
    return f"{quality_adj} {type_name}"

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
        "name": format_item_name({"quality": quality, "type": itype}),
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
    profile_text = f"👤 Профиль\n\n📈 Характеристики:\n{stats_text}\n\n🎒 Экипировка:\n{equip_text if equip_text else 'Пусто'}"
    await call.message.edit_text(profile_text, reply_markup=main_menu_kb())

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
        await state.update_data(training_stat=stat, training_cost=cost)
        await state.set_state(GameStates.waiting_for_cancel)
        
        train_msg = f"⏳ Прокачка {stat_name_ru} началась!\nСписано {cost} золота.\nВремя: 10 мин.\n\n❌ Нажмите 'Отменить' чтобы прервать."
        await call.message.edit_text(train_msg, reply_markup=cancel_kb())
        
        asyncio.create_task(training_timer(call.from_user.id, stat, cost))
    else:
        await call.answer(f"💰 Недостаточно золота! Нужно {cost}", show_alert=True)

async def training_timer(user_id, stat, cost):
    await asyncio.sleep(TRAINING_TIME_SECONDS)
    user = await db.get_user(user_id)
    if user['lock_until'] > int(time.time()) - TRAINING_TIME_SECONDS + 60:
        new_val = user['stats'][stat] + STAT_GROWTH[stat]
        user['stats'][stat] = new_val
        await db.update_user(user_id, stats=user['stats'])
        await db.update_user(user_id, lock_until=0)
        await dp.storage.set_state(user_id, None)

@dp.callback_query(F.data == "cancel_action")
async def cancel_action(call: types.CallbackQuery):
    user = await db.get_user(call.from_user.id)
    data = await dp.storage.get_data(call.from_user.id)
    
    if 'training_cost' in 
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
    
    fight_text = f"⚔️ Арена Боя\n📊 Сложность: {diff}\n\nВыберите действие:"
    await call.message.edit_text(fight_text, reply_markup=fight_kb(diff))

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
    back_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="menu_fight")]])
    await call.message.edit_text("🔢 Введите число сложности (1-100):", reply_markup=back_kb)

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
    
    fight_start_msg = f"⚔️ Бой начался!\n👹 {enemy['name']} (❤️ {enemy['hp']})\n⏳ Идет симуляция..."
    await call.message.edit_text(fight_start_msg)
    
    await asyncio.sleep(2)
    
    win, logs, hp_left = simulate_combat(user, enemy)
    
    # Форматируем лог боя
    combat_log = []
    for log in logs:
        if log["type"] == "player":
            crit = " (КРИТ!)" if log["crit"] else ""
            combat_log.append(f"⚔️ Вы атакуете. Здоровье врага: {log['enemy_hp']}/{log['enemy_hp_max']}, вы нанесли {log['dmg']} урона{crit}.")
        elif log["type"] == "enemy":
            combat_log.append(f"🛡️ {log['enemy_name']} атакует. Ваше здоровье: {log['player_hp']}/{log['player_hp_max']}, вы получили {log['dmg']} урона.")
        elif log["type"] == "dodge":
            combat_log.append(f"💨 Вы уклонились от атаки {log['enemy_name']}!")
        elif log["type"] == "win":
            combat_log.append("🏆 Враг мёртв!")
        elif log["type"] == "death":
            combat_log.append("💀 Вы погибли.")
    
    if win:
        gold_gain = enemy['gold']
        await db.update_user(user['user_id'], gold=user['gold'] + gold_gain)
        user['stats']['hp'] = max(1, hp_left)
        await db.update_user(user['user_id'], stats=user['stats'])
        
        # Формируем сообщение о победе
        result_lines = [
            "🏆 Победа!",
            "",
            f"💰 Золото: +{gold_gain}"
        ]
        
        loot_roll = random.randint(1, 100) + user['stats'].get('luck', 0)
        if loot_roll > 80:
            item = generate_item(user['stats'].get('rarity', 0))
            await db.add_item(user['user_id'], item)
            result_lines.append(f"🎁 Предмет: {item['name']}")
        
        result_lines.append("")
        result_lines.append("📜 Лог боя:")
        result_lines.extend(combat_log)
        
        result_msg = "\n".join(result_lines)
        await call.message.edit_text(result_msg, reply_markup=main_menu_kb())
    else:
        death_time = int(time.time()) + DEATH_LOCK_TIME
        await db.update_user(user['user_id'], death_until=death_time, lock_until=death_time)
        
        death_lines = [
            "💀 Вы погибли!",
            "",
            "⏳ Блокировка на 1 час.",
            "",
            "📜 Лог боя:"
        ]
        death_lines.extend(combat_log)
        
        death_msg = "\n".join(death_lines)
        await call.message.edit_text(death_msg, reply_markup=main_menu_kb())

# --- МЕДИТАЦИЯ ---

@dp.callback_query(F.data == "menu_meditate")
async def meditate_menu(call: types.CallbackQuery, state: FSMContext):
    user = await db.get_user(call.from_user.id)
    lock = check_lock(user)
    if lock:
        await call.answer(lock, show_alert=True)
        return
    
    await state.set_state(GameStates.waiting_for_cancel)
    lock_time = int(time.time()) + MEDITATION_TIME
    await db.update_user(user['user_id'], lock_until=lock_time)
    
    meditate_msg = f"🧘‍♂️ Вы медитируете {MEDITATION_TIME//60} мин.\n✨ Мана восстанавливается...\n\n❌ Нажмите 'Отменить' чтобы прервать."
    await call.message.edit_text(meditate_msg, reply_markup=cancel_kb())

# --- МАГАЗИН ---

@dp.callback_query(F.data == "menu_shop")
async def shop_menu(call: types.CallbackQuery):
    user = await db.get_user(call.from_user.id)
    now = int(time.time())
    
    if now - user['last_shop_refresh'] > SHOP_REFRESH_TIME:
        new_items = [generate_item(user['stats'].get('rarity', 0)) for _ in range(SHOP_SLOTS_COUNT)]
        await db.update_user(user['user_id'], shop_items=new_items, last_shop_refresh=now)
        user['shop_items'] = new_items
    
    if not user['shop_items']:
        await call.answer("📦 Товары закончились", show_alert=True)
        return

    kb = []
    for i, item in enumerate(user['shop_items']):
        price = (item['stats'].get('dmg', 1) + item['stats'].get('def', 1) + item['stats'].get('hp', 0)) * 10
        kb.append([InlineKeyboardButton(text=f"{item['name']} - {price}💰", callback_data=f"shop_buy_{i}")])
    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data="menu_back")])
    
    await call.message.edit_text("🏪 Магазин\n🔄 Обновление через 10 мин", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data.startswith("shop_buy_"))
async def shop_buy(call: types.CallbackQuery):
    user = await db.get_user(call.from_user.id)
    idx = int(call.data.split("_")[2])
    
    if idx >= len(user['shop_items']):
        await call.answer("❌ Товар недоступен", show_alert=True)
        return
        
    item = user['shop_items'][idx]
    price = (item['stats'].get('dmg', 1) + item['stats'].get('def', 1) + item['stats'].get('hp', 0)) * 10
    
    if user['gold'] >= price:
        await db.update_user(user['user_id'], gold=user['gold'] - price)
        await db.add_item(user['user_id'], item)
        user['shop_items'].pop(idx)
        await db.update_user(user['user_id'], shop_items=user['shop_items'])
        await call.answer(f"✅ Куплено: {item['name']}", show_alert=True)
        await shop_menu(call)
    else:
        await call.answer("❌ Недостаточно золота", show_alert=True)

# --- ИНВЕНТАРЬ ---

@dp.callback_query(F.data == "menu_inv")
async def inv_menu(call: types.CallbackQuery):
    user = await db.get_user(call.from_user.id)
    items = await db.get_inventory(user['user_id'])
    
    kb = []
    if len(items) >= user['inventory_slots']:
        kb.append([InlineKeyboardButton(text="🔒 Слоты полны", callback_data="none")])
    else:
        kb.append([InlineKeyboardButton(text=f"➕ Слот ({SLOT_UPGRADE_COST}💰)", callback_data="inv_buy_slot")])

    for db_id, item_json in items[:user['inventory_slots']]:
        item = json.loads(item_json)
        kb.append([InlineKeyboardButton(text=f"{item['name']}", callback_data=f"inv_item_{db_id}")])
    
    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data="menu_back")])
    
    await call.message.edit_text(f"🎒 Инвентарь ({len(items)}/{user['inventory_slots']})", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data == "inv_buy_slot")
async def inv_buy_slot(call: types.CallbackQuery):
    user = await db.get_user(call.from_user.id)
    if user['gold'] >= SLOT_UPGRADE_COST:
        await db.update_user(user['user_id'], gold=user['gold'] - SLOT_UPGRADE_COST, inventory_slots=user['inventory_slots'] + 1)
        await call.answer("✅ Слот куплен!", show_alert=True)
        await inv_menu(call)
    else:
        await call.answer("❌ Не хватает золота", show_alert=True)

@dp.callback_query(F.data.startswith("inv_item_"))
async def inv_item_action(call: types.CallbackQuery):
    item_id = int(call.data.split("_")[2])
    user = await db.get_user(call.from_user.id)
    items = await db.get_inventory(user['user_id'])
    
    target = None
    for db_id, item_json in items:
        if db_id == item_id:
            target = json.loads(item_json)
            break
            
    if not target:
        await call.answer("❌ Предмет не найден", show_alert=True)
        return

    stats_str = ", ".join([f"{STAT_NAMES_RU.get(k, k)}:{v}" for k,v in target['stats'].items()])
    kb = [
        [InlineKeyboardButton(text="📥 Надеть", callback_data=f"inv_equip_{item_id}")],
        [InlineKeyboardButton(text="⬆️ Улучшить (100💰)", callback_data=f"inv_up_{item_id}")],
        [InlineKeyboardButton(text="🗑️ Удалить", callback_data=f"inv_del_{item_id}")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="menu_inv")]
    ]
    
    await call.message.edit_text(f"📦 {target['name']}\n{stats_str}", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data.startswith("inv_equip_"))
async def inv_equip(call: types.CallbackQuery):
    item_id = int(call.data.split("_")[2])
    user = await db.get_user(call.from_user.id)
    items = await db.get_inventory(user['user_id'])
    
    target = None
    for db_id, item_json in items:
        if db_id == item_id:
            target = json.loads(item_json)
            break
            
    if target:
        slot = target['type']
        user['equipped'][slot] = target
        await db.update_user(user['user_id'], equipped=user['equipped'])
        await call.answer(f"✅ Надето в слот {slot}", show_alert=True)
        await inv_menu(call)

@dp.callback_query(F.data.startswith("inv_up_"))
async def inv_upgrade(call: types.CallbackQuery):
    item_id = int(call.data.split("_")[2])
    user = await db.get_user(call.from_user.id)
    
    if user['gold'] < 100:
        await call.answer("💰 Нужно 100 золота", show_alert=True)
        return

    items = await db.get_inventory(user['user_id'])
    for db_id, item_json in items:
        if db_id == item_id:
            item = json.loads(item_json)
            for stat in item['stats']:
                item['stats'][stat] = int(item['stats'][stat] * 1.1)
            item['level'] = item.get('level', 1) + 1
            await db.conn.execute("UPDATE inventory SET item_data = ? WHERE id = ?", (json.dumps(item), item_id))
            await db.conn.commit()
            break

    await db.update_user(user['user_id'], gold=user['gold'] - 100)
    await call.answer("✅ Предмет улучшен!", show_alert=True)
    await inv_item_action(call)

@dp.callback_query(F.data.startswith("inv_del_"))
async def inv_del(call: types.CallbackQuery):
    item_id = int(call.data.split("_")[2])
    await db.delete_item(item_id)
    await call.answer("🗑️ Предмет удален", show_alert=True)
    await inv_menu(call)

# --- ЗАПУСК ---

async def main():
    await db.connect()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())