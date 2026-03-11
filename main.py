import asyncio
import random
import time
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from config import *
from database import Database

# Инициализация
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
db = Database()

# --- ГЕЙМ ЛОГИКА ---

def check_lock(user):
    now = int(time.time())
    if now < user['death_until']:
        return f"Вы мертвы. Воскрешение через {int((user['death_until'] - now)/60)} мин."
    if now < user['lock_until']:
        return f"Вы заняты. Ожидание {int((user['lock_until'] - now)/60)} мин."
    return None

def calc_stat_level(current_val, base_val, growth):
    # Алгебраическая прогрессия: сколько уровней вложено
    if growth == 0: return 0
    return int((current_val - base_val) / growth)

def get_upgrade_cost(stat_name, user_stats):
    base = BASE_STATS[stat_name]
    current = user_stats.get(stat_name, base)
    growth = STAT_GROWTH[stat_name]
    level = calc_stat_level(current, base, growth)
    # Формула: База + (Уровень * Шаг)
    return TRAINING_BASE_COST + (level * TRAINING_COST_STEP)

def generate_enemy(difficulty_multiplier):
    template = random.choice(ENEMIES)
    # Скалирование характеристик врага
    scale = 1 + (difficulty_multiplier * 0.5) 
    enemy = {
        "name": template["name"],
        "hp": int(template["base_hp"] * scale),
        "max_hp": int(template["base_hp"] * scale),
        "dmg": int(template["base_dmg"] * scale),
        "gold": random.randint(template["gold_min"], template["gold_max"]) * int(scale)
    }
    return enemy

def simulate_combat(player, enemy):
    logs = []
    p_hp = player['stats']['hp']
    e_hp = enemy['hp']
    turn = 0
    
    # Учет экипировки
    dmg_bonus = 0
    def_bonus = 0
    for slot, item in player.get('equipped', {}).items():
        if item:
            dmg_bonus += item.get('stats', {}).get('dmg', 0)
            def_bonus += item.get('stats', {}).get('def', 0)
            
    p_dmg = player['stats']['dmg'] + dmg_bonus
    p_def = player['stats']['def'] + def_bonus
    p_crit = player['stats']['crit_chance']
    p_dodge = player['stats']['dodge_chance']

    while p_hp > 0 and e_hp > 0 and turn < 50: # Лимит ходов
        turn += 1
        # Ход игрока
        is_crit = random.randint(1, 100) <= p_crit
        dmg_dealt = max(1, (p_dmg * (2 if is_crit else 1)) - (enemy.get('def', 0)))
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
    types = ["weapon", "armor", "accessory"]
    itype = random.choice(types)
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
        "name": f"{quality} {itype.capitalize()}",
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
    for stat, val in BASE_STATS.items():
        row.append(InlineKeyboardButton(text=f"{stat.upper()}", callback_data=f"train_{stat}"))
        if len(row) == 2:
            kb.append(row)
            row = []
    if row: kb.append(row)
    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data="menu_back")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def fight_kb(difficulty):
    kb = [
        [InlineKeyboardButton(text=f"Уровень опасности: {difficulty}", callback_data="fight_diff")],
        [InlineKeyboardButton(text="⚔️ Атаковать", callback_data="fight_start"), InlineKeyboardButton(text="🔙 Назад", callback_data="menu_back")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

# --- FSM STATES ---
class GameStates(StatesGroup):
    waiting_for_action = State()

# --- HANDLERS ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await db.connect()
    user = await db.get_user(message.from_user.id)
    lock_msg = check_lock(user)
    if lock_msg:
        await message.answer(f"🔒 {lock_msg}")
    else:
        await message.answer(f"👋 Добро пожаловать в RPG Бот!\nЗолото: {user['gold']}", reply_markup=main_menu_kb())

@dp.callback_query(F.data == "menu_back")
async def back_menu(call: types.CallbackQuery):
    user = await db.get_user(call.from_user.id)
    lock_msg = check_lock(user)
    text = f"📊 Золото: {user['gold']}\nHP: {user['stats']['hp']}"
    if lock_msg: text += f"\n⚠️ {lock_msg}"
    await call.message.edit_text(text, reply_markup=main_menu_kb())

@dp.callback_query(F.data == "menu_profile")
async def profile(call: types.CallbackQuery):
    user = await db.get_user(call.from_user.id)
    stats_text = "\n".join([f"{k}: {v}" for k, v in user['stats'].items()])
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
    await call.message.edit_text("Выберите характеристику для улучшения:", reply_markup=train_kb())

@dp.callback_query(F.data.startswith("train_"))
async def train_stat(call: types.CallbackQuery):
    user = await db.get_user(call.from_user.id)
    lock = check_lock(user)
    if lock:
        await call.answer(lock, show_alert=True)
        return

    stat = call.data.split("_")[1]
    cost = get_upgrade_cost(stat, user['stats'])
    
    if user['gold'] >= cost:
        # Списываем золото
        await db.update_user(user['user_id'], gold=user['gold'] - cost)
        # Увеличиваем стат
        new_val = user['stats'][stat] + STAT_GROWTH[stat]
        user['stats'][stat] = new_val
        await db.update_user(user['user_id'], stats=user['stats'])
        
        # Блокируем игрока
        lock_time = int(time.time()) + TRAINING_TIME_SECONDS
        await db.update_user(user['user_id'], lock_until=lock_time)
        
        await call.message.edit_text(f"✅ {stat.upper()} улучшен до {new_val:.1f}!\nСписано {cost} золота.\nТеперь вы тренируетесь 10 мин.")
        await asyncio.sleep(2)
        await back_menu(call)
    else:
        await call.answer(f"Недостаточно золота! Нужно {cost}", show_alert=True)

# --- БОЙ ---

@dp.callback_query(F.data == "menu_fight")
async def fight_menu(call: types.CallbackQuery, state: FSMContext):
    user = await db.get_user(call.from_user.id)
    lock = check_lock(user)
    if lock:
        await call.answer(lock, show_alert=True)
        return
    
    # Сохраняем текущую сложность в состоянии
    data = await state.get_data()
    diff = data.get("difficulty", 1)
    
    await call.message.edit_text(f"⚔️ Арена Боя\nОпасность: {diff}\nВыберите действие:", reply_markup=fight_kb(diff))

@dp.callback_query(F.data == "fight_diff")
async def fight_diff_change(call: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    diff = data.get("difficulty", 1)
    new_diff = diff + 1 if diff < 10 else 1
    await state.update_data(difficulty=new_diff)
    await fight_menu(call, state)

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
    
    # Блокируем на время боя (симуляция 30 сек)
    lock_time = int(time.time()) + 30
    await db.update_user(user['user_id'], lock_until=lock_time)
    
    await call.message.edit_text(f"⚔️ Бой начался!\nВраг: {enemy['name']} (HP: {enemy['hp']})\nИдет симуляция...")
    
    await asyncio.sleep(2) # Имитация задержки
    
    win, logs, hp_left = simulate_combat(user, enemy)
    
    if win:
        # Победа
        gold_gain = enemy['gold']
        await db.update_user(user['user_id'], gold=user['gold'] + gold_gain, stats={'hp': hp_left}) # Обновляем HP
        
        # Дроп
        drop_msg = f"🏆 Победа!\nПолучено золота: {gold_gain}\n"
        loot_roll = random.randint(1, 100) + user['stats']['luck']
        if loot_roll > 80:
            item = generate_item(user['stats']['rarity'])
            await db.add_item(user['user_id'], item)
            drop_msg += f"🎁 Выпал предмет: {item['name']}"
        
        # Шанс на навык
        skill_roll = random.randint(1, 100)
        if skill_roll > 90:
            drop_msg += "\n✨ Найден новый навык!"
            # Логика добавления навыка упрощена для примера
            
        await call.message.edit_text(drop_msg + "\n\n📜 Лог боя:\n" + "\n".join(logs[-5:]), reply_markup=main_menu_kb())
    else:
        # Смерть
        death_time = int(time.time()) + DEATH_LOCK_TIME
        await db.update_user(user['user_id'], death_until=death_time, lock_until=death_time)
        await call.message.edit_text(f"💀 Вы погибли!\nБлокировка на 1 час.\n\nЛог боя:\n" + "\n".join(logs[-5:]), reply_markup=main_menu_kb())

# --- МАГАЗИН ---

@dp.callback_query(F.data == "menu_shop")
async def shop_menu(call: types.CallbackQuery):
    user = await db.get_user(call.from_user.id)
    now = int(time.time())
    
    # Обновление ассортимента
    if now - user['last_shop_refresh'] > SHOP_REFRESH_TIME:
        new_items = [generate_item(user['stats']['rarity']) for _ in range(SHOP_SLOTS_COUNT)]
        await db.update_user(user['user_id'], shop_items=new_items, last_shop_refresh=now)
        user['shop_items'] = new_items
    
    if not user['shop_items']:
        await call.answer("Товары закончились", show_alert=True)
        return

    kb = []
    for i, item in enumerate(user['shop_items']):
        price = (item['stats'].get('dmg', 1) + item['stats'].get('def', 1) + item['stats'].get('hp', 0)) * 10
        kb.append([InlineKeyboardButton(text=f"{item['name']} - {price}G", callback_data=f"shop_buy_{i}")])
    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data="menu_back")])
    
    await call.message.edit_text("🏪 Магазин (Обновление через 10 мин)", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data.startswith("shop_buy_"))
async def shop_buy(call: types.CallbackQuery):
    user = await db.get_user(call.from_user.id)
    idx = int(call.data.split("_")[2])
    
    if idx >= len(user['shop_items']):
        await call.answer("Товар недоступен", show_alert=True)
        return
        
    item = user['shop_items'][idx]
    price = (item['stats'].get('dmg', 1) + item['stats'].get('def', 1) + item['stats'].get('hp', 0)) * 10
    
    if user['gold'] >= price:
        await db.update_user(user['user_id'], gold=user['gold'] - price)
        await db.add_item(user['user_id'], item)
        # Удаляем из магазина
        user['shop_items'].pop(idx)
        await db.update_user(user['user_id'], shop_items=user['shop_items'])
        await call.answer(f"Куплено: {item['name']}", show_alert=True)
        await shop_menu(call)
    else:
        await call.answer("Недостаточно золота", show_alert=True)

# --- ИНВЕНТАРЬ ---

@dp.callback_query(F.data == "menu_inv")
async def inv_menu(call: types.CallbackQuery):
    user = await db.get_user(call.from_user.id)
    items = await db.get_inventory(user['user_id'])
    
    kb = []
    if len(items) >= user['inventory_slots']:
        kb.append([InlineKeyboardButton(text="🔒 Слоты полны", callback_data="none")])
    else:
        kb.append([InlineKeyboardButton(text=f"Купить слот ({SLOT_UPGRADE_COST}G)", callback_data="inv_buy_slot")])

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
        await call.answer("Слот куплен!", show_alert=True)
        await inv_menu(call)
    else:
        await call.answer("Не хватает золота", show_alert=True)

@dp.callback_query(F.data.startswith("inv_item_"))
async def inv_item_action(call: types.CallbackQuery):
    item_id = int(call.data.split("_")[2])
    user = await db.get_user(call.from_user.id)
    items = await db.get_inventory(user['user_id'])
    
    # Поиск предмета
    target = None
    for db_id, item_json in items:
        if db_id == item_id:
            target = json.loads(item_json)
            break
            
    if not target:
        await call.answer("Предмет не найден", show_alert=True)
        return

    kb = [
        [InlineKeyboardButton(text="Надеть", callback_data=f"inv_equip_{item_id}")],
        [InlineKeyboardButton(text="Улучшить (100G)", callback_data=f"inv_up_{item_id}")],
        [InlineKeyboardButton(text="Удалить", callback_data=f"inv_del_{item_id}")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="menu_inv")]
    ]
    
    stats_str = ", ".join([f"{k}:{v}" for k,v in target['stats'].items()])
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
        slot = target['type'] # weapon, armor, accessory
        user['equipped'][slot] = target
        await db.update_user(user['user_id'], equipped=user['equipped'])
        await call.answer(f"Надето в слот {slot}", show_alert=True)
        await inv_menu(call)

@dp.callback_query(F.data.startswith("inv_up_"))
async def inv_upgrade(call: types.CallbackQuery):
    # Упрощенная логика улучшения предмета
    item_id = int(call.data.split("_")[2])
    user = await db.get_user(call.from_user.id)
    
    if user['gold'] < 100:
        await call.answer("Нужно 100 золота", show_alert=True)
        return

    # В реальности тут нужно парсить JSON, менять статы и сохранять обратно
    # Для краткости просто списываем золото и даем сообщение
    await db.update_user(user['user_id'], gold=user['gold'] - 100)
    await call.answer("Предмет улучшен! (Демо)", show_alert=True)
    await inv_item_action(call)

@dp.callback_query(F.data.startswith("inv_del_"))
async def inv_del(call: types.CallbackQuery):
    item_id = int(call.data.split("_")[2])
    await db.delete_item(item_id)
    await call.answer("Предмет удален", show_alert=True)
    await inv_menu(call)

# --- МЕДИТАЦИЯ (ДОП АКТИВНОСТЬ) ---

@dp.callback_query(F.data == "menu_meditate")
async def meditate(call: types.CallbackQuery):
    user = await db.get_user(call.from_user.id)
    lock = check_lock(user)
    if lock:
        await call.answer(lock, show_alert=True)
        return
    
    lock_time = int(time.time()) + MEDITATION_TIME
    await db.update_user(user['user_id'], lock_until=lock_time)
    # Бонус к манне временно не сохраняем в БД для простоты, но можно добавить бафф
    await call.message.edit_text(f"🧘‍♂️ Вы медитируете {MEDITATION_TIME//60} мин.\nМана восстановлена полностью (Демо).")
    await asyncio.sleep(MEDITATION_TIME)
    # После выхода из асинхронной паузы лучше не делать действий с БД, 
    # так как бот может быть перезапущен. В продакшене используйте Celery или задачи в БД.
    # Здесь просто уведомляем, что время вышло, при следующем действии.

# --- ЗАПУСК ---

async def main():
    await db.connect()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())