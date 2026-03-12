import asyncio
import json
import random
import time
import uuid
import os
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

# Вставь сюда токен своего бота
TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=TOKEN)
dp = Dispatcher()

DATA_FILE = "users_data.json"
users = {}

# Пункт 1: Словари для правильного отображения названий (чтобы текст не обрезался)
STAT_NAMES_RU = {
    "max_hp": "Макс. Здоровье",
    "max_mana": "Макс. Мана",
    "phys_atk": "Физ. Атаку",
    "mag_atk": "Маг. Атаку",
    "defense": "Защиту",
    "speed": "Скорость",
    "regen": "Регенерацию"
}

# --- РАБОТА С БАЗОЙ ДАННЫХ ---
def load_data():
    global users
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            users = json.load(f)

def save_users():
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False, indent=4)

def get_user(user_id):
    uid = str(user_id)
    if uid not in users:
        users[uid] = {
            "id": uid,
            "gold": 100,
            "stats": { # Базовые статы игрока
                "max_hp": 100, "hp": 100,
                "max_mana": 50, "mana": 50,
                "phys_atk": 10, "mag_atk": 10,
                "defense": 5, "speed": 10, "regen": 1
            },
            "inventory": [],
            "wait_until": 0,
            "wait_type": None,
            "potion_shop": {"next_refresh": 0, "potions": []}
        }
    return users[uid]

# --- ИГРОВЫЕ МЕХАНИКИ И ГЕНЕРАЦИЯ ---

def generate_item():
    """Генерация предмета с учетом пунктов 2, 6 и 12"""
    # Пункт 6: Шанс на статы: 1 стат = 100%, 2 стата = 25%, 3 = 6.25% и т.д. (до 5)
    num_stats = 1
    for _ in range(4): 
        if random.random() <= 0.25:
            num_stats += 1
        else:
            break

    stats_picked = random.sample(list(STAT_NAMES_RU.keys()), min(num_stats, len(STAT_NAMES_RU)))
    item_stats = {}
    
    for stat in stats_picked:
        # Пункт 12: Случайный тип прибавки (аддитивный или процентный)
        is_percent = random.choice([True, False])
        
        # Пункт 2: Рандомная базовая статистика и рандомный рост цены улучшения
        base_val = random.randint(1, 5) if not is_percent else random.randint(2, 10)
        item_stats[stat] = {
            "base": base_val,
            "level": 0,
            "type": "percent" if is_percent else "flat",
            "upgrade_cost": random.randint(10, 50),
            "cost_mult": round(random.uniform(1.1, 2.0), 2)
        }
        
    return {
        "id": str(uuid.uuid4()), 
        "name": f"Снаряжение {random.randint(100, 999)}", 
        "stats": item_stats
    }

def generate_potions():
    """Пункт 10: Генерация зелий для лавки"""
    potions = []
    for _ in range(5):
        stat = random.choice(list(STAT_NAMES_RU.keys()))
        value = random.randint(1, 5)
        price = random.randint(100, 1000)
        potions.append({"stat": stat, "value": value, "price": price})
    return potions

def calc_stat(user, stat_name):
    """Высчитывает итоговый стат игрока (База + Плоские предметы) * Процентные предметы"""
    base = user["stats"].get(stat_name, 0)
    total_flat = base
    total_percent = 1.0
    
    # Считаем, что все предметы в инвентаре надеты (для примера, можно добавить систему экипировки)
    for item in user["inventory"]:
        if stat_name in item["stats"]:
            s_data = item["stats"][stat_name]
            # Пункт 2: Прибавляется базовая характеристика за каждое улучшение (base + base*level)
            val = s_data["base"] * (s_data["level"] + 1)
            
            # Пункт 12: Обработка аддитивной и процентной прибавки
            if s_data["type"] == "flat":
                total_flat += val
            elif s_data["type"] == "percent":
                total_percent += (val / 100.0)
                
    return int(total_flat * total_percent)

# --- КЛАВИАТУРЫ (МЕНЮ) ---

def main_menu_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="⚔️ Охота", callback_data="menu_hunt")
    kb.button(text="🎒 Инвентарь", callback_data="menu_inventory")
    kb.button(text="🏋️ Тренировка", callback_data="menu_training")
    kb.button(text="🧪 Лавка Зелий", callback_data="menu_potions")
    kb.adjust(2, 2)
    return kb.as_markup()

def hunt_menu_kb():
    kb = InlineKeyboardBuilder()
    for i in range(1, 4):
        kb.button(text=f"Сложность {i}", callback_data=f"hunt_{i}")
    kb.button(text="🔙 Назад", callback_data="main_menu")
    kb.adjust(1)
    return kb.as_markup()

# --- ФОНОВЫЕ ЗАДАЧИ И ОЖИДАНИЕ ---

async def start_wait(user_id, duration, wait_type, msg_text="Ожидание..."):
    """Универсальная функция ожидания с асинхронной задержкой"""
    user = get_user(user_id)
    user["wait_until"] = time.time() + duration
    user["wait_type"] = wait_type
    save_users()

    # Пункт 5: Кнопка проверки времени и отсутствие отмены у смерти
    kb = InlineKeyboardBuilder()
    kb.button(text="⏳ Проверить время", callback_data="wait_check")
    if wait_type != "death":
        kb.button(text="❌ Отменить", callback_data="wait_cancel")
    kb.adjust(1)

    await bot.send_message(user_id, msg_text, reply_markup=kb.as_markup())
    
    await asyncio.sleep(duration)
    
    # Проверяем, не отменил ли игрок ожидание раньше времени
    user = get_user(user_id)
    if user["wait_until"] > 0 and user["wait_until"] <= time.time():
        user["wait_until"] = 0
        user["wait_type"] = None
        if wait_type == "death":
            user["stats"]["hp"] = calc_stat(user, "max_hp") # Воскрешение
        save_users()
        # Пункт 5: Открывать главное меню после завершения ожидания
        await bot.send_message(user_id, "✅ Ожидание завершено!", reply_markup=main_menu_kb())

def is_waiting(user):
    return user["wait_until"] > time.time()

# --- ОБРАБОТЧИКИ СООБЩЕНИЙ ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    get_user(message.from_user.id)
    await message.answer("Добро пожаловать в текстовую RPG!", reply_markup=main_menu_kb())

# Пункт 13: Команды удаления сохранений и выдачи золота
@dp.message(Command("destroysave"))
async def cmd_destroysave(message: types.Message):
    uid = str(message.from_user.id)
    if uid in users:
        del users[uid]
        save_users()
        await message.answer("🗑 Ваше сохранение удалено. Нажмите /start для новой игры.")

@dp.message(Command("givegold"))
async def cmd_givegold(message: types.Message):
    user = get_user(message.from_user.id)
    user["gold"] += 10000
    save_users()
    await message.answer("💰 Вам выдано 10000 золота!")

# --- ОБРАБОТЧИКИ CALLBACK (КНОПОК) ---

@dp.callback_query(F.data == "wait_check")
async def wait_check(callback: types.CallbackQuery):
    user = get_user(callback.from_user.id)
    if user["wait_until"] > time.time():
        left = int(user["wait_until"] - time.time())
        await callback.answer(f"Осталось ждать: {left} сек.", show_alert=True)
    else:
        await callback.answer("Ожидание окончено!", show_alert=True)

@dp.callback_query(F.data == "wait_cancel")
async def wait_cancel(callback: types.CallbackQuery):
    user = get_user(callback.from_user.id)
    if user["wait_type"] == "death":
        await callback.answer("Смерть нельзя отменить!", show_alert=True)
        return
    user["wait_until"] = 0
    user["wait_type"] = None
    save_users()
    await callback.message.edit_text("❌ Ожидание отменено.", reply_markup=main_menu_kb())

@dp.callback_query(F.data == "main_menu")
async def go_main_menu(callback: types.CallbackQuery):
    if is_waiting(get_user(callback.from_user.id)): return await callback.answer("Вы заняты!")
    await callback.message.edit_text("Главное меню", reply_markup=main_menu_kb())

# --- БОЕВКА (ОХОТА) ---

@dp.callback_query(F.data == "menu_hunt")
async def menu_hunt(callback: types.CallbackQuery):
    if is_waiting(get_user(callback.from_user.id)): return await callback.answer("Вы заняты!")
    await callback.message.edit_text("Выбери сложность охоты:", reply_markup=hunt_menu_kb())

@dp.callback_query(F.data.startswith("hunt_"))
async def process_hunt(callback: types.CallbackQuery):
    user = get_user(callback.from_user.id)
    if is_waiting(user): return await callback.answer("Вы заняты!")
    
    diff = int(callback.data.split("_")[1])
    
    player_max_hp = calc_stat(user, "max_hp")
    player_hp = user["stats"]["hp"]
    player_mana = user["stats"]["mana"]
    player_max_mana = calc_stat(user, "max_mana")
    player_atk = calc_stat(user, "phys_atk")
    
    enemy_hp = 30 * diff
    enemy_atk = 5 * diff
    
    log = f"⚔️ Вы отправились на охоту (Сложность: {diff})\n"
    # Пункт 3: Отображение маны в начале битвы
    log += f"🧙‍♂️ Ваша Мана: {player_mana}/{player_max_mana}\n\n"
    
    while player_hp > 0 and enemy_hp > 0:
        # Пункт 14: Рандомизация физ урона в 20%
        actual_dmg = int(player_atk * random.uniform(0.8, 1.2))
        enemy_hp -= actual_dmg
        log += f"🗡 Вы нанесли {actual_dmg} урона. (У врага {max(0, enemy_hp)} ХП)\n"
        if enemy_hp <= 0: break
        
        player_hp -= enemy_atk
        log += f"👹 Враг нанес {enemy_atk} урона.\n"
        
    user["stats"]["hp"] = max(0, player_hp)
    
    log += "\n"
    if player_hp > 0:
        # Пункт 11: Увеличенная награда золота в зависимости от сложности
        reward = 10 + (diff * 5)
        user["gold"] += reward
        log += f"🏆 Вы победили! Награда: {reward} золота.\n"
        
        if random.random() < 0.6: # 60% шанс дропа
            item = generate_item()
            user["inventory"].append(item)
            log += f"🎁 Получен предмет: {item['name']}\n"
            
        # Пункт 3: Здоровье и мана после логов битвы
        log += f"\n❤️ Осталось здоровья: {player_hp}/{player_max_hp}\n"
        log += f"🧙‍♂️ Осталось маны: {player_mana}/{player_max_mana}\n"
        save_users()
        
        # Пункт 4: Оставление игрока на меню выбора сложности после победы
        await callback.message.edit_text(log, reply_markup=hunt_menu_kb())
    else:
        log += f"💀 Вы погибли.\n"
        log += f"❤️ Осталось здоровья: 0/{player_max_hp}\n"
        log += f"🧙‍♂️ Осталось маны: {player_mana}/{player_max_mana}\n"
        await callback.message.edit_text(log)
        asyncio.create_task(start_wait(callback.from_user.id, 60, "death", "💀 Вы мертвы. Воскрешение 60 секунд."))

# --- ИНВЕНТАРЬ И УЛУЧШЕНИЕ ---

@dp.callback_query(F.data == "menu_inventory")
async def menu_inv(callback: types.CallbackQuery):
    user = get_user(callback.from_user.id)
    if is_waiting(user): return await callback.answer("Вы заняты!")
    
    kb = InlineKeyboardBuilder()
    for item in user["inventory"]:
        kb.button(text=item["name"], callback_data=f"item_{item['id']}")
    kb.button(text="🔙 Назад", callback_data="main_menu")
    kb.adjust(1)
    
    await callback.message.edit_text(f"🎒 Ваш инвентарь:\n💰 Золото: {user['gold']}", reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("item_"))
async def view_item(callback: types.CallbackQuery):
    user = get_user(callback.from_user.id)
    item_id = callback.data.split("_")[1]
    item = next((i for i in user["inventory"] if i["id"] == item_id), None)
    if not item: return await callback.answer("Предмет не найден!")

    # Пункт 7: Отображение золота в меню предмета
    text = f"🗡 **{item['name']}**\n💰 Ваше золото: {user['gold']}\n\n📊 Статистика:\n"
    
    kb = InlineKeyboardBuilder()
    for stat_key, stat_data in item["stats"].items():
        # Пункт 1: Правильное форматирование текста (без обрезаний)
        stat_name = STAT_NAMES_RU.get(stat_key, stat_key)
        
        # Пункт 2: Показ базовой статистики и текущей силы
        cur_val = stat_data["base"] * (stat_data["level"] + 1)
        type_sym = "%" if stat_data["type"] == "percent" else ""
        text += f"🔸 {stat_name}: {cur_val}{type_sym} (База: {stat_data['base']}{type_sym}, Ур. {stat_data['level']})\n"
        
        # Пункт 9: Отображение роста цены и прибавки характеристики
        cost = int(stat_data["upgrade_cost"])
        growth = stat_data["cost_mult"]
        btn_text = f"Улучшить {stat_name} (+{stat_data['base']}{type_sym}) | {cost} з. (Рост: x{growth})"
        kb.button(text=btn_text, callback_data=f"upg_{item_id}_{stat_key}")
        
    kb.button(text="🔙 В инвентарь", callback_data="menu_inventory")
    kb.adjust(1)
    
    await callback.message.edit_text(text, reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("upg_"))
async def upgrade_item(callback: types.CallbackQuery):
    user = get_user(callback.from_user.id)
    _, item_id, stat_key = callback.data.split("_", 2)
    item = next((i for i in user["inventory"] if i["id"] == item_id), None)
    if not item: return

    stat_data = item["stats"][stat_key]
    cost = int(stat_data["upgrade_cost"])

    if user["gold"] >= cost:
        user["gold"] -= cost
        stat_data["level"] += 1
        stat_data["upgrade_cost"] = int(cost * stat_data["cost_mult"])
        save_users()
        
        # Пункт 8: Обновление сообщения на месте (не перекидываем в инвентарь)
        await view_item(callback) # Просто вызываем функцию перерисовки текущего меню предмета
    else:
        await callback.answer("Недостаточно золота!", show_alert=True)

# --- ТРЕНИРОВКИ И ЛАВКА (Пункт 10 и 15) ---

@dp.callback_query(F.data == "menu_training")
async def menu_training(callback: types.CallbackQuery):
    user = get_user(callback.from_user.id)
    if is_waiting(user): return await callback.answer("Вы заняты!")
    
    # Пункт 10: Тренировки стали бесплатными
    text = "🏋️ **Тренировочный лагерь**\nТренировки бесплатны, но занимают 30 секунд. Выберите стат для улучшения:"
    
    kb = InlineKeyboardBuilder()
    # Пункт 15: Убраны hp и mana, оставлены только max_hp и max_mana
    trainable_stats = ["max_hp", "max_mana", "phys_atk", "mag_atk", "defense"]
    for stat in trainable_stats:
        kb.button(text=f"Тренировать {STAT_NAMES_RU[stat]}", callback_data=f"train_{stat}")
    kb.button(text="🔙 Назад", callback_data="main_menu")
    kb.adjust(1)
    
    await callback.message.edit_text(text, reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("train_"))
async def process_train(callback: types.CallbackQuery):
    stat = callback.data.split("_", 1)[1]
    user = get_user(callback.from_user.id)
    
    user["stats"][stat] += 1
    save_users()
    
    asyncio.create_task(start_wait(callback.from_user.id, 30, "train", f"🏋️ Вы тренируете {STAT_NAMES_RU[stat]}..."))
    await callback.message.delete()

@dp.callback_query(F.data == "menu_potions")
async def menu_potions(callback: types.CallbackQuery):
    user = get_user(callback.from_user.id)
    if is_waiting(user): return await callback.answer("Вы заняты!")
    
    shop = user["potion_shop"]
    # Пункт 10: Обновление лавки каждые 10 минут
    if time.time() >= shop["next_refresh"] or not shop["potions"]:
        shop["potions"] = generate_potions()
        shop["next_refresh"] = time.time() + 600
        save_users()

    text = f"🧪 **Лавка Зелий**\n💰 Ваше золото: {user['gold']}\nОбновление через: {int(shop['next_refresh'] - time.time())} сек.\n\nЗелья навсегда повышают ваши базовые характеристики!"

    kb = InlineKeyboardBuilder()
    for i, pot in enumerate(shop["potions"]):
        stat_name = STAT_NAMES_RU.get(pot["stat"])
        kb.button(text=f"+{pot['value']} {stat_name} | {pot['price']} з.", callback_data=f"buy_pot_{i}")

    kb.button(text="🔄 Обновить ассортимент (500 з.)", callback_data="refresh_potions")
    kb.button(text="🔙 Назад", callback_data="main_menu")
    kb.adjust(1)

    await callback.message.edit_text(text, reply_markup=kb.as_markup())

@dp.callback_query(F.data == "refresh_potions")
async def refresh_potions(callback: types.CallbackQuery):
    user = get_user(callback.from_user.id)
    if user["gold"] >= 500:
        user["gold"] -= 500
        user["potion_shop"]["potions"] = generate_potions()
        user["potion_shop"]["next_refresh"] = time.time() + 600
        save_users()
        await menu_potions(callback)
    else:
        await callback.answer("Недостаточно золота для обновления!", show_alert=True)

@dp.callback_query(F.data.startswith("buy_pot_"))
async def buy_potion(callback: types.CallbackQuery):
    user = get_user(callback.from_user.id)
    pot_idx = int(callback.data.split("_")[2])
    potions = user["potion_shop"]["potions"]
    
    if pot_idx >= len(potions): return await callback.answer("Зелье уже куплено!")
    
    pot = potions[pot_idx]
    if user["gold"] >= pot["price"]:
        user["gold"] -= pot["price"]
        user["stats"][pot["stat"]] += pot["value"]
        potions.pop(pot_idx) # Удаляем купленное зелье
        save_users()
        await callback.answer(f"Вы выпили зелье! {STAT_NAMES_RU[pot['stat']]} +{pot['value']}", show_alert=True)
        await menu_potions(callback)
    else:
        await callback.answer("Недостаточно золота!", show_alert=True)


async def main():
    load_data()
    print("Бот запущен. Нажмите Ctrl+C для остановки.")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

