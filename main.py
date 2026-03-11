import asyncio
import json
import time
import random
import os
import logging
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters.callback_data import CallbackData
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# Логирование (исключаем спам об ошибке обновления сообщения)
logging.basicConfig(level=logging.INFO)

# ==========================================
# ПАПКА ДАННЫХ И ФАЙЛ
# ==========================================
DATA_DIR = 'data'
os.makedirs(DATA_DIR, exist_ok=True)
DB_FILE = os.path.join(DATA_DIR, 'database.json')

db_lock = asyncio.Lock()
db = {}

# ==========================================
# СЛОВАРЬ ЛОКАЛИЗАЦИИ СТАТОВ
# ==========================================
STAT_RU = {
    "max_hp": "Макс. Здоровье", "hp": "Здоровье", "max_mp": "Макс. Мана", "mp": "Мана",
    "atk": "Физ. Атака", "def": "Физ. Защита", "m_shield": "Магический Щит",
    "crit_chance": "Шанс Крита (%)", "evasion": "Уклонение (%)", "atk_spd": "Скор. Атаки",
    "hp_regen": "Реген Здоровья", "mp_regen": "Реген Маны",
    "drop_chance": "Множитель Дропа",
    "lifesteal": "Вампиризм (%)", "armor_pen": "Пробитие Брони",
    "magic_atk": "Маг. Атака", "magic_res": "Маг. Сопротивление", "thorns": "Шипы (%)"
}

# ==========================================
# ГЕНЕРАТОР НАЗВАНИЙ ПРЕДМЕТОВ
# ==========================================
PREFIXES = ["Свирепый", "Древний", "Пылающий", "Забытый", "Проклятый", "Святой", "Теневой", "Искрящийся", "Тяжелый", "Легкий"]
NOUNS = {
    "weapon": ["Меч", "Топор", "Кинжал", "Посох", "Лук", "Молот", "Копье"],
    "armor": ["Доспех", "Шлем", "Щит", "Нагрудник", "Плащ", "Мантия"],
    "accessory": ["Амулет", "Кольцо", "Талисман", "Оберег", "Браслет"]
}
SUFFIXES = ["Убийцы", "Короля", "Гоблина", "Дракона", "Света", "Тьмы", "Крови", "Ветров", "Пустоты", "Жизни"]

# ==========================================
# КОНФИГ БАЛАНСА И ИГРЫ
# ==========================================
CONFIG = {
    "time_train": 600,       
    "time_death": 3600,      
    "time_expedition": 1800, 
    "time_shop_update": 600, 

    "enemy_base_stats": {
        "hp": 50, "atk": 5, "def": 2, "atk_spd": 1.0, "evasion": 2.0, "magic_atk": 0, "magic_res": 0
    },
    "enemy_stat_scale": { 
        "hp": 15, "atk": 2.5, "def": 1, "atk_spd": 0.05, "evasion": 0.2, "magic_atk": 1.5, "magic_res": 0.5
    }
}

# ==========================================
# СОСТОЯНИЯ FSM (ДЛЯ ВВОДА ТЕКСТА)
# ==========================================
class Form(StatesGroup):
    waiting_for_difficulty = State()

# ==========================================
# ФАБРИКИ КОЛЛБЭКОВ (CALLBACK DATA)
# ==========================================
class MenuCB(CallbackData, prefix="menu"):
    action: str
    page: int = 0

class ActionCB(CallbackData, prefix="act"):
    action: str

class TrainCB(CallbackData, prefix="tr"):
    stat: str

class HuntCB(CallbackData, prefix="hunt"):
    action: str

class ItemCB(CallbackData, prefix="it"):
    action: str
    idx: int
    stat: str = ""

class ShopCB(CallbackData, prefix="sh"):
    action: str
    idx: int = 0

class SkillCB(CallbackData, prefix="sk"):
    action: str
    idx: int
    slot: int = 0

# ==========================================
# БАЗА ДАННЫХ И СОСТОЯНИЯ (АСИНХРОННАЯ)
# ==========================================
async def load_db():
    global db
    async with db_lock:
        if os.path.exists(DB_FILE):
            with open(DB_FILE, 'r', encoding='utf-8') as f:
                db = json.load(f)
        else:
            db = {"players": {}, "shop": {"assortment": [], "last_update": 0}}
            _save_db_unlocked()

async def save_db():
    async with db_lock:
        _save_db_unlocked()

def _save_db_unlocked():
    with open(DB_FILE, 'w', encoding='utf-8') as f:
        json.dump(db, f, ensure_ascii=False, indent=4)

# ==========================================
# КЛАСС ИГРОКА И ЛОГИКА
# ==========================================
class Player:
    def __init__(self, uid, name):
        self.uid = str(uid)
        self.name = name
        self.gold = 100
        
        self.stats = {
            "max_hp": 100, "hp": 100, "max_mp": 50, "mp": 50,
            "atk": 10, "def": 5, "m_shield": 0, 
            "crit_chance": 5.0, "evasion": 5.0, "atk_spd": 1.0, 
            "hp_regen": 1.0, "mp_regen": 1.0, "drop_chance": 1.0,
            "lifesteal": 0.0, "armor_pen": 0, "magic_atk": 0, "magic_res": 0, "thorns": 0.0
        }
        # Убраны уровни игрока, статы качаются напрямую (base stat tracking)
        self.stat_upgrades = {k: 0 for k in self.stats.keys()}
        
        self.inv_slots = 10
        self.inventory = [] 
        self.equip = {"weapon": None, "armor": None, "accessory": None}
        
        self.abilities = [] 
        self.active_abilities = [None, None] 
        
        self.state = 'idle'
        self.state_end_time = 0
        self.training_stat = None
        self.difficulty = 1
        self.last_regen_time = time.time()

    @classmethod
    def from_dict(cls, data):
        p = cls(data['uid'], data['name'])
        for k, v in data.items():
            if k == 'stats' or k == 'stat_upgrades':
                for stat_key in p.stats.keys():
                    if stat_key not in v:
                        v[stat_key] = 0.0 if 'chance' in stat_key or 'regen' in stat_key or 'steal' in stat_key or 'thorns' in stat_key else 0
            setattr(p, k, v)
        if not hasattr(p, 'difficulty'): p.difficulty = 1
        if not hasattr(p, 'last_regen_time'): p.last_regen_time = time.time()
        return p

async def get_player(user_id, name="Hero"):
    uid = str(user_id)
    async with db_lock:
        if uid not in db['players']:
            db['players'][uid] = Player(uid, name).__dict__
            _save_db_unlocked()
        data = db['players'][uid]
    return Player.from_dict(data)

async def save_player(player):
    async with db_lock:
        db['players'][player.uid] = player.__dict__
        _save_db_unlocked()

async def apply_passive_regen(player):
    now = time.time()
    delta = now - player.last_regen_time
    if delta >= 60:
        mins = int(delta / 60)
        t_stats = get_total_stats(player)
        
        player.stats['hp'] = min(t_stats['max_hp'], player.stats['hp'] + (t_stats['hp_regen'] * mins))
        player.stats['mp'] = min(t_stats['max_mp'], player.stats['mp'] + (t_stats['mp_regen'] * mins))
        
        player.last_regen_time = now - (delta % 60)
        await save_player(player)

# ==========================================
# ФОНОВЫЙ ПОТОК (АСИНХРОННАЯ ЗАДАЧА)
# ==========================================
async def background_worker():
    while True:
        await asyncio.sleep(10)
        now = time.time()
        changed = False
        
        async with db_lock:
            for uid, p_data in list(db['players'].items()):
                player = Player.from_dict(p_data)
                
                if player.state != 'idle' and now >= player.state_end_time:
                    if player.state == 'dead':
                        player.stats['hp'] = player.stats['max_hp']
                        try:
                            await bot.send_message(uid, "👼 Вы воскресли и готовы к новым битвам!")
                        except: pass
                    
                    elif player.state == 'training':
                        stat = player.training_stat
                        player.stats[stat] += (player.stats[stat] * 0.1) if player.stats[stat] > 0 else 1.0 # +10% или +1 базово
                        player.stat_upgrades[stat] += 1
                        if stat in ["max_hp", "max_mp"]:
                            player.stats[stat.replace("max_", "")] = player.stats[stat] 
                        try:
                            await bot.send_message(uid, f"🏋️‍♂️ Тренировка завершена! Характеристика <b>{STAT_RU.get(stat, stat)}</b> улучшена.")
                        except: pass
                    
                    elif player.state == 'expedition':
                        gold_found = random.randint(50, 150) + (player.difficulty * 20)
                        player.gold += gold_found
                        msg = f"🧭 Экспедиция завершена!\nВы нашли: 💰 {gold_found} золота."
                        
                        if random.random() < (0.3 * player.stats["drop_chance"]):
                            item = generate_item(player.difficulty)
                            if len(player.inventory) < player.inv_slots:
                                player.inventory.append(item)
                                msg += f"\nТакже вы нашли предмет: 📦 {item['name']}"
                            else:
                                msg += "\nВы нашли предмет, но в инвентаре нет места!"
                        try:
                            await bot.send_message(uid, msg)
                        except: pass

                    player.state = 'idle'
                    player.training_stat = None
                    db['players'][uid] = player.__dict__
                    changed = True
                    
        if changed:
            _save_db_unlocked()

# ==========================================
# ГЕНЕРАТОРЫ И МАГАЗИН (СИСТЕМА БЕЗ УРОВНЕЙ)
# ==========================================
def generate_item_name(i_type):
    prefix = random.choice(PREFIXES)
    noun = random.choice(NOUNS[i_type])
    suffix = random.choice(SUFFIXES)
    return f"{prefix} {noun} {suffix}"

def generate_item(difficulty):
    i_type = random.choice(["weapon", "armor", "accessory"])
    name = generate_item_name(i_type)
    
    # Количество статов в предмете (чаще 1, редко 3)
    stats_count = random.choices([1, 2, 3], weights=[70, 25, 5])[0]
    
    available_stats = {
        "weapon": ["atk", "magic_atk", "armor_pen", "crit_chance", "atk_spd"],
        "armor": ["def", "magic_res", "max_hp", "evasion", "thorns"],
        "accessory": ["hp_regen", "mp_regen", "lifesteal", "max_mp", "drop_chance"]
    }
    
    chosen_stats = random.sample(available_stats[i_type], min(stats_count, len(available_stats[i_type])))
    item_stats = {}
    
    base_price = 0
    for stat in chosen_stats:
        # Базовое значение зависит от сложности (абстрактного тира)
        # Для % статов (шанс, реген) значения меньше
        is_percent = stat in ["crit_chance", "evasion", "atk_spd", "drop_chance", "lifesteal", "thorns"]
        mult = 0.5 if is_percent else 2.0
        
        base_val = max(1, int((difficulty * random.uniform(0.8, 1.2)) * mult))
        if is_percent and base_val > 50: base_val = 50.0 # кап для процентов
        if stat == "atk_spd": base_val = round(base_val / 20.0, 2) # скорость атаки малая
        
        item_stats[stat] = {
            "base": base_val,
            "current": base_val,
            "upgrades": 0
        }
        base_price += int(base_val * (100 if is_percent else 10))

    return {
        "id": "i_" + str(time.time()).replace(".", "") + str(random.randint(10,99)),
        "name": name,
        "type": i_type,
        "stats": item_stats,
        "sell_price": max(10, int(base_price * 0.5))
    }

def generate_ability(difficulty):
    a_type = random.choice(["heal", "power_strike", "magic_blast"])
    
    base_val = int(difficulty * random.uniform(4.0, 6.0))
    mp_cost = int(10 + (difficulty * 2))
    
    names = {"heal": "Исцеление", "power_strike": "Мощный Удар", "magic_blast": "Взрыв Магии"}
    
    return {
        "id": "a_" + str(time.time()).replace(".", "") + str(random.randint(10,99)),
        "name": f"{names[a_type]} {random.choice(['Света', 'Тьмы', 'Жизни'])}",
        "type": a_type,
        "base_value": base_val,
        "current_value": base_val,
        "upgrades": 0,
        "mp_cost": mp_cost,
        "sell_price": max(20, int(base_val * 5))
    }

def generate_enemy(difficulty):
    # Рандомизация статов (разброс 30%)
    variance = lambda: random.uniform(0.7, 1.3)
    
    e_stats = {k: max(0, int((CONFIG["enemy_base_stats"][k] + (difficulty * CONFIG["enemy_stat_scale"].get(k, 0))) * variance())) 
               for k in ["hp", "atk", "def", "magic_atk", "magic_res"]}
               
    e_stats["atk_spd"] = max(0.2, (CONFIG["enemy_base_stats"]["atk_spd"] + (difficulty * CONFIG["enemy_stat_scale"]["atk_spd"])) * variance())
    e_stats["evasion"] = min(60.0, (CONFIG["enemy_base_stats"]["evasion"] + (difficulty * CONFIG["enemy_stat_scale"]["evasion"])) * variance())
    
    # Вычисляем "силу" врага относительно нормы для этого уровня, чтобы выдать награду
    norm_hp = CONFIG["enemy_base_stats"]["hp"] + (difficulty * CONFIG["enemy_stat_scale"]["hp"])
    power_multiplier = e_stats["hp"] / (norm_hp if norm_hp > 0 else 1)
    
    names = ["Гоблин", "Скелет", "Орк", "Разбойник", "Волк", "Голем", "Демон", "Дракон"]
    prefixes = ["Слабый", "Обычный", "Свирепый", "Древний", "Элитный", "Кошмарный"]
    
    return {
        "name": f"{random.choice(prefixes)} {random.choice(names)}",
        "difficulty": difficulty,
        "max_hp": e_stats["hp"],
        "hp": e_stats["hp"],
        "atk": e_stats["atk"],
        "def": e_stats["def"],
        "magic_atk": e_stats["magic_atk"],
        "magic_res": e_stats["magic_res"],
        "atk_spd": e_stats["atk_spd"],
        "evasion": e_stats["evasion"],
        "power_mult": power_multiplier
    }

async def update_shop(difficulty, force=False):
    now = time.time()
    async with db_lock:
        if force or now - db["shop"]["last_update"] > CONFIG["time_shop_update"]:
            db["shop"]["assortment"] = []
            shop_diff = max(1, difficulty + random.randint(0, 5))
            for _ in range(3):
                db["shop"]["assortment"].append({"item": generate_item(shop_diff), "sold": False})
            for _ in range(2):
                db["shop"]["assortment"].append({"ability": generate_ability(shop_diff), "sold": False})
                
            db["shop"]["last_update"] = now
            _save_db_unlocked()

# ==========================================
# БОЕВАЯ СИСТЕМА
# ==========================================
def get_total_stats(player):
    total = player.stats.copy()
    for eq_type, item in player.equip.items():
        if item:
            for stat_name, stat_data in item["stats"].items():
                if stat_name in total:
                    total[stat_name] += stat_data["current"]
    return total

def simulate_combat_realtime(player, enemy):
    p_stats = get_total_stats(player)
    e_stats = enemy.copy()
    
    log = [
        f"⚔️ <b>Бой начался! Угроза: {enemy['difficulty']}</b>",
        f"👤 <b>{player.name}</b>: ❤️ {p_stats['hp']:.1f}/{p_stats['max_hp']} | 🗡 АТК: {p_stats['atk']} | ⚡ Скор: {p_stats['atk_spd']:.2f}",
        f"👹 <b>{enemy['name']}</b>: ❤️ {enemy['hp']:.1f}/{enemy['max_hp']} | 🗡 АТК: {enemy['atk']} | ⚡ Скор: {enemy['atk_spd']:.2f}",
        "-"*20
    ]
    
    p_cooldown = 1.0 / max(0.1, p_stats["atk_spd"])
    e_cooldown = 1.0 / max(0.1, e_stats["atk_spd"])
    
    tick = 0.1 
    time_elapsed = 0.0
    max_time = 180.0 
    
    while p_stats["hp"] > 0 and e_stats["hp"] > 0 and time_elapsed < max_time:
        
        # Регенерация раз в 1 секунду (равна regen / 60)
        if abs((time_elapsed % 1.0) - 0.0) < 0.05:
            p_stats["hp"] = min(p_stats["max_hp"], p_stats["hp"] + p_stats["hp_regen"] / 60.0)
            p_stats["mp"] = min(p_stats["max_mp"], p_stats["mp"] + p_stats["mp_regen"] / 60.0)
            
        p_cooldown -= tick
        e_cooldown -= tick
        
        # --- УДАР ИГРОКА ---
        if p_cooldown <= 0 and p_stats["hp"] > 0:
            p_cooldown += 1.0 / max(0.1, p_stats["atk_spd"])
            
            ability_used = False
            for ab in player.active_abilities:
                if ab and p_stats["mp"] >= ab["mp_cost"]:
                    p_stats["mp"] -= ab["mp_cost"]
                    ability_used = True
                    if ab["type"] == "heal":
                        heal_amt = ab["current_value"]
                        p_stats["hp"] = min(p_stats["max_hp"], p_stats["hp"] + heal_amt)
                        log.append(f"[{time_elapsed:.1f}с] ✨ {ab['name']}: исцеление +{heal_amt:.1f} ХП! (Вы: {p_stats['hp']:.1f}/{p_stats['max_hp']})")
                    elif ab["type"] == "power_strike":
                        dmg = max(1, ab["current_value"] + p_stats["atk"] - e_stats["def"])
                        e_stats["hp"] -= dmg
                        log.append(f"[{time_elapsed:.1f}с] 💥 {ab['name']}: {dmg:.1f} урона! (Враг: {max(0, e_stats['hp']):.1f}/{e_stats['max_hp']})")
                    elif ab["type"] == "magic_blast":
                        dmg = max(1, ab["current_value"] + p_stats["magic_atk"] - e_stats["magic_res"])
                        e_stats["hp"] -= dmg
                        log.append(f"[{time_elapsed:.1f}с] 🔮 {ab['name']}: {dmg:.1f} урона! (Враг: {max(0, e_stats['hp']):.1f}/{e_stats['max_hp']})")
                    break 
            
            if not ability_used and e_stats["hp"] > 0:
                if random.random() * 100 > e_stats["evasion"]:
                    eff_def = max(0, e_stats["def"] - p_stats["armor_pen"])
                    dmg = max(0, p_stats["atk"] - eff_def)
                    magic_dmg = max(0, p_stats["magic_atk"] - e_stats["magic_res"])
                    total_dmg = dmg + magic_dmg
                    if total_dmg <= 0: total_dmg = 1
                    
                    if random.random() * 100 < p_stats["crit_chance"]:
                        total_dmg *= 2
                        e_stats["hp"] -= total_dmg
                        log.append(f"[{time_elapsed:.1f}с] 🔥 КРИТ! Вы нанесли {total_dmg:.1f} урона. (Враг: {max(0, e_stats['hp']):.1f}/{e_stats['max_hp']})")
                    else:
                        e_stats["hp"] -= total_dmg
                        log.append(f"[{time_elapsed:.1f}с] 🗡 Вы нанесли {total_dmg:.1f} урона. (Враг: {max(0, e_stats['hp']):.1f}/{e_stats['max_hp']})")
                        
                    if p_stats["lifesteal"] > 0:
                        ls_heal = total_dmg * (p_stats["lifesteal"] / 100.0)
                        p_stats["hp"] = min(p_stats["max_hp"], p_stats["hp"] + ls_heal)
                else:
                    log.append(f"[{time_elapsed:.1f}с] 💨 Враг уклонился!")

        # --- УДАР ВРАГА ---
        if e_stats["hp"] > 0 and e_cooldown <= 0:
            e_cooldown += 1.0 / max(0.1, e_stats["atk_spd"])
            
            if random.random() * 100 > p_stats["evasion"]:
                eff_def = p_stats["def"]
                dmg = max(0, e_stats["atk"] - eff_def)
                magic_dmg = max(0, e_stats["magic_atk"] - p_stats["magic_res"])
                total_dmg = dmg + magic_dmg
                if total_dmg <= 0: total_dmg = 1

                if p_stats["m_shield"] > 0:
                    absorbed = min(total_dmg, p_stats["m_shield"])
                    p_stats["m_shield"] -= absorbed
                    total_dmg -= absorbed
                
                p_stats["hp"] -= total_dmg
                log.append(f"[{time_elapsed:.1f}с] 🩸 Враг нанес {total_dmg:.1f} урона. (Вы: {max(0, p_stats['hp']):.1f}/{p_stats['max_hp']})")
                
                if p_stats["thorns"] > 0 and total_dmg > 0:
                    thorns_dmg = total_dmg * (p_stats["thorns"] / 100.0)
                    e_stats["hp"] -= thorns_dmg
                    log.append(f"[{time_elapsed:.1f}с] 🌵 Шипы вернули {thorns_dmg:.1f} урона. (Враг: {max(0, e_stats['hp']):.1f}/{e_stats['max_hp']})")
            else:
                log.append(f"[{time_elapsed:.1f}с] 🌀 Вы уклонились!")

        time_elapsed += tick

    player.stats["hp"] = max(0, p_stats["hp"]) 
    player.stats["mp"] = max(0, p_stats["mp"])
    
    if time_elapsed >= max_time:
        return False, log, "⏳ Время боя вышло! Враг сбежал, а вы истощены."
    elif player.stats["hp"] <= 0:
        return False, log, "💀 Вы погибли! Восстановление займет 1 час."
    else:
        return True, log, "🏆 Вы победили!"

# ==========================================
# UI КЛАВИАТУРЫ И ФУНКЦИИ
# ==========================================
def main_menu_kbd():
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    builder.button(text="🗡 Охота", callback_data=MenuCB(action="hunt").pack())
    builder.button(text="🏋️ Тренировка", callback_data=MenuCB(action="train").pack())
    builder.button(text="🎒 Инвентарь", callback_data=MenuCB(action="inv").pack())
    builder.button(text="✨ Навыки", callback_data=MenuCB(action="skills").pack())
    builder.button(text="🏪 Магазин", callback_data=MenuCB(action="shop").pack())
    builder.button(text="🧭 Экспедиция", callback_data=MenuCB(action="exped").pack())
    builder.button(text="👤 Герой", callback_data=MenuCB(action="profile").pack())
    builder.adjust(2, 2, 2, 1)
    return builder.as_markup()

def cancel_kbd():
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Отменить", callback_data=ActionCB(action="cancel").pack())
    return builder.as_markup()

async def safe_edit(message: Message, text: str, reply_markup: InlineKeyboardMarkup = None):
    try:
        await message.edit_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            raise

# ==========================================
# РОУТЕРЫ / ОБРАБОТЧИКИ
# ==========================================
@dp.message(CommandStart())
async def cmd_start(message: Message):
    await load_db()
    player = await get_player(message.from_user.id, message.from_user.first_name)
    await message.answer(
        f"Добро пожаловать, <b>{player.name}</b>!\nТвоя сила ограничивается только временем.",
        reply_markup=main_menu_kbd()
    )

@dp.message(F.text == "/relive")
async def cmd_relive(message: Message):
    await load_db()
    player = await get_player(message.from_user.id)
    if player.state == 'dead':
        player.state = 'idle'
        player.state_end_time = 0
        player.stats['hp'] = player.stats['max_hp']
        await save_player(player)
        await message.answer("✨ Вы мгновенно воскресли!", reply_markup=main_menu_kbd())
    else:
        await message.answer("Вы и так живы!")

@dp.callback_query(ActionCB.filter(F.action == "cancel"))
async def cb_cancel(query: CallbackQuery, callback_data: ActionCB):
    player = await get_player(query.from_user.id)
    if player.state in ['training', 'expedition']:
        player.state = 'idle'
        player.state_end_time = 0
        player.training_stat = None
        await save_player(player)
        await safe_edit(query.message, "Действие отменено.", reply_markup=main_menu_kbd())
    else:
        await query.answer("Отменять нечего.", show_alert=True)

# Глобальный фильтр на занятость
@dp.callback_query()
async def process_any_callback(query: CallbackQuery, bot: Bot):
    # Костыль для пропуска глобального фильтра, если это отмена
    if query.data and query.data.startswith("act:cancel"):
        return
        
    await load_db()
    player = await get_player(query.from_user.id)
    await apply_passive_regen(player)
    
    if player.state != 'idle':
        time_left = int((player.state_end_time - time.time()) / 60)
        if player.state == 'dead':
            await query.answer(f"Вы мертвы. Воскрешение через: ~{time_left} мин.", show_alert=True)
        else:
            state_rus = {"training": "Тренируетесь", "expedition": "В экспедиции"}.get(player.state, player.state)
            await query.answer(f"Вы заняты ({state_rus}). Осталось: ~{time_left} мин.", show_alert=True)
        return
    
    # Передаем управление дальше, если игрок свободен
    raise SkipHandler() # aiogram 3: need to pass to next handler. Actually, middleware is better, but this is a simple script.

# Замена для пропуска хендлера в простых функциях (эмулируем middleware)
from aiogram.dispatcher.event.bases import SkipHandler 

@dp.callback_query(MenuCB.filter(F.action == "profile"))
async def menu_profile(query: CallbackQuery, callback_data: MenuCB):
    player = await get_player(query.from_user.id)
    t_stats = get_total_stats(player)
    
    text = f"👤 <b>Профиль: {player.name}</b>\n💰 Золото: {player.gold}\n\n"
    text += f"❤️ {STAT_RU['hp']}: {player.stats['hp']:.1f}/{t_stats['max_hp']} (+{t_stats['hp_regen']}/мин)\n"
    text += f"💧 {STAT_RU['mp']}: {player.stats['mp']:.1f}/{t_stats['max_mp']} (+{t_stats['mp_regen']}/мин)\n"
    text += f"⚔️ {STAT_RU['atk']}: {t_stats['atk']} | 🔮 {STAT_RU['magic_atk']}: {t_stats['magic_atk']}\n"
    text += f"🛡 {STAT_RU['def']}: {t_stats['def']} | 💠 {STAT_RU['magic_res']}: {t_stats['magic_res']}\n"
    text += f"💥 {STAT_RU['crit_chance']}: {t_stats['crit_chance']}% | 💨 {STAT_RU['evasion']}: {t_stats['evasion']}%\n"
    text += f"🦇 {STAT_RU['lifesteal']}: {t_stats['lifesteal']}% | 🌵 {STAT_RU['thorns']}: {t_stats['thorns']}%\n"
    text += f"🪓 {STAT_RU['armor_pen']}: {t_stats['armor_pen']} | 🛡 {STAT_RU['m_shield']}: {t_stats['m_shield']}\n"
    text += f"⚡️ {STAT_RU['atk_spd']}: {t_stats['atk_spd']} | 🍀 {STAT_RU['drop_chance']}: x{t_stats['drop_chance']}\n"
    
    await safe_edit(query.message, text, reply_markup=main_menu_kbd())

# --- ТРЕНИРОВКА ---
@dp.callback_query(MenuCB.filter(F.action == "train"))
async def menu_train(query: CallbackQuery, callback_data: MenuCB):
    player = await get_player(query.from_user.id)
    page = callback_data.page
    stats = list(player.stat_upgrades.keys())
    
    per_page = 6
    start = page * per_page
    end = start + per_page
    
    text = "🏋️ <b>Тренировка (10 минут)</b>\nВыберите характеристику:\n\n"
    
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    
    for i, stat in enumerate(stats[start:end], start=1):
        upgrades = player.stat_upgrades[stat]
        cost = 50 + (upgrades * 20)
        stat_name = STAT_RU.get(stat, stat)
        text += f"{i}. <b>{stat_name}</b> (Улучшений: {upgrades}) - Стоимость: 💰 {cost}\n"
        builder.button(text=f"{i}", callback_data=TrainCB(stat=stat).pack())
        
    builder.adjust(3)
    
    # Навигация
    nav_row = []
    if page > 0: nav_row.append(InlineKeyboardButton(text="⬅️", callback_data=MenuCB(action="train", page=page-1).pack()))
    if end < len(stats): nav_row.append(InlineKeyboardButton(text="➡️", callback_data=MenuCB(action="train", page=page+1).pack()))
    if nav_row: builder.row(*nav_row)
    
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data=MenuCB(action="profile").pack()))
    
    await safe_edit(query.message, text, reply_markup=builder.as_markup())

@dp.callback_query(TrainCB.filter())
async def process_train(query: CallbackQuery, callback_data: TrainCB):
    player = await get_player(query.from_user.id)
    stat = callback_data.stat
    cost = 50 + (player.stat_upgrades[stat] * 20)
    
    if player.gold >= cost:
        player.gold -= cost
        player.state = 'training'
        player.training_stat = stat
        player.state_end_time = time.time() + CONFIG["time_train"]
        await save_player(player)
        await safe_edit(query.message, f"Вы начали тренировку <b>{STAT_RU.get(stat, stat)}</b>. Вернитесь через 10 минут.", reply_markup=cancel_kbd())
    else:
        await query.answer("Недостаточно золота!", show_alert=True)

# --- ОХОТА ---
@dp.callback_query(MenuCB.filter(F.action == "hunt"))
async def menu_hunt(query: CallbackQuery, callback_data: MenuCB):
    player = await get_player(query.from_user.id)
    
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    b = InlineKeyboardBuilder()
    b.button(text="◀️", callback_data=HuntCB(action="dec").pack())
    b.button(text=f"Угроза: {player.difficulty}", callback_data=HuntCB(action="set").pack())
    b.button(text="▶️", callback_data=HuntCB(action="inc").pack())
    b.button(text="⚔️ Начать поиск", callback_data=HuntCB(action="start").pack())
    b.button(text="🔙 Назад", callback_data=MenuCB(action="profile").pack())
    b.adjust(3, 1, 1)
    
    text = "⚔️ <b>Охота</b>\nУстановите уровень угрозы. Чем выше угроза, тем сильнее враги, но и награда больше."
    await safe_edit(query.message, text, reply_markup=b.as_markup())

@dp.callback_query(HuntCB.filter())
async def process_hunt(query: CallbackQuery, callback_data: HuntCB, state: FSMContext):
    player = await get_player(query.from_user.id)
    act = callback_data.action
    
    if act == "dec":
        if player.difficulty > 1:
            player.difficulty -= 1
            await save_player(player)
            await menu_hunt(query, MenuCB(action="hunt"))
        else:
            await query.answer("Минимум: 1")
    elif act == "inc":
        player.difficulty += 1
        await save_player(player)
        await menu_hunt(query, MenuCB(action="hunt"))
    elif act == "set":
        await query.message.answer("Отправьте числом желаемый уровень угрозы:")
        await state.set_state(Form.waiting_for_difficulty)
        await query.answer()
    elif act == "start":
        enemy = generate_enemy(player.difficulty)
        is_win, log, result_msg = simulate_combat_realtime(player, enemy)
        
        if is_win:
            # Награда скейлится от множителя силы врага
            base_gold = 10 + (player.difficulty * 5)
            actual_gold = int(base_gold * enemy['power_mult'] * player.stats["drop_chance"])
            player.gold += actual_gold
            result_msg += f"\n💰 Найдено золота: {actual_gold}."
            
            drop_chance_scaled = 0.2 * enemy['power_mult'] * player.stats["drop_chance"]
            if random.random() < drop_chance_scaled:
                if len(player.inventory) < player.inv_slots:
                    item = generate_item(player.difficulty)
                    player.inventory.append(item)
                    result_msg += f"\n📦 Выпал предмет: {item['name']}"
                else:
                    result_msg += "\n📦 Предмет выпал, но инвентарь полон!"
        elif "погибли" in result_msg:
            player.state = 'dead'
            player.state_end_time = time.time() + CONFIG["time_death"]
            
        await save_player(player)
        
        log_text = "\n".join(log)
        if len(log_text) > 3000:
            log_text = log_text[:1500] + "\n... [БОЙ СЛИШКОМ ДОЛГИЙ] ...\n" + log_text[-1500:]
            
        await safe_edit(query.message, f"{log_text}\n\n<b>{result_msg}</b>", reply_markup=main_menu_kbd() if is_win else cancel_kbd())

@dp.message(Form.waiting_for_difficulty)
async def hunt_diff_input(message: Message, state: FSMContext):
    try:
        lvl = int(message.text)
        if lvl > 0:
            player = await get_player(message.from_user.id)
            player.difficulty = lvl
            await save_player(player)
            await message.answer(f"Уровень угрозы установлен на {lvl}.", reply_markup=main_menu_kbd())
        else:
            await message.answer("Число должно быть больше нуля.", reply_markup=main_menu_kbd())
    except ValueError:
        await message.answer("Ошибка ввода. Ожидалось число.", reply_markup=main_menu_kbd())
    finally:
        await state.clear()

# --- ИНВЕНТАРЬ ---
@dp.callback_query(MenuCB.filter(F.action == "inv"))
async def menu_inv(query: CallbackQuery, callback_data: MenuCB):
    player = await get_player(query.from_user.id)
    text = f"🎒 <b>Инвентарь ({len(player.inventory)}/{player.inv_slots})</b>\n\nЭкипировано:\n"
    
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    b = InlineKeyboardBuilder()
    
    # Список для всех предметов (экипированных и в сумке)
    all_items = []
    btn_index = 0
    
    for slot, item in player.equip.items():
        slot_ru = {"weapon": "Оружие", "armor": "Броня", "accessory": "Амулет"}[slot]
        if item:
            text += f"{btn_index+1}. [{slot_ru}] {item['name']}\n"
            b.button(text=f"{btn_index+1}", callback_data=ItemCB(action="view", idx=btn_index).pack())
            all_items.append({"data": item, "is_equip": True, "slot": slot, "real_idx": -1})
            btn_index += 1
        else:
            text += f"- [{slot_ru}] Пусто\n"
            
    text += "\nВ сумке:\n"
    if not player.inventory:
        text += "Пусто\n"
    else:
        for real_idx, item in enumerate(player.inventory):
            text += f"{btn_index+1}. {item['name']}\n"
            b.button(text=f"{btn_index+1}", callback_data=ItemCB(action="view", idx=btn_index).pack())
            all_items.append({"data": item, "is_equip": False, "slot": item['type'], "real_idx": real_idx})
            btn_index += 1
            
    # Сохраняем временную мапу воркера в state не будем, просто пересчитаем индексы
    # Но для надежности лучше просто передавать real_idx и флаг is_equip.
    # Чтобы уместить в callback_data, у нас:
    # idx 0,1,2 - экипировка (weapon, armor, acc)
    # idx >= 10 - инвентарь (idx - 10 = real_idx)
    
    b.adjust(5)
    b.row(InlineKeyboardButton(text="🔙 Назад", callback_data=MenuCB(action="profile").pack()))
    
    await safe_edit(query.message, text, reply_markup=b.as_markup())

@dp.callback_query(ItemCB.filter(F.action == "view"))
async def view_item(query: CallbackQuery, callback_data: ItemCB):
    player = await get_player(query.from_user.id)
    idx = callback_data.idx
    
    is_equip = False
    real_idx = -1
    item = None
    slot_name = ""
    
    # Восстанавливаем логику поиска предмета по единому индексу
    btn_index = 0
    for slot, eq_item in player.equip.items():
        if eq_item:
            if btn_index == idx:
                item = eq_item
                is_equip = True
                slot_name = slot
                break
            btn_index += 1
    
    if not is_equip:
        for r_idx, inv_item in enumerate(player.inventory):
            if btn_index == idx:
                item = inv_item
                real_idx = r_idx
                break
            btn_index += 1

    if not item:
        await query.answer("Предмет не найден!")
        return

    type_ru = {"weapon": "Оружие", "armor": "Броня", "accessory": "Амулет"}[item['type']]
    text = f"📦 <b>{item['name']}</b> ({'Надето' if is_equip else 'В сумке'})\nТип: {type_ru}\n\nХарактеристики:\n"
    
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    b = InlineKeyboardBuilder()
    
    for stat_key, stat_data in item["stats"].items():
        upg_cost = int((stat_data['base'] * 10) + (stat_data['upgrades'] * stat_data['base'] * 5))
        s_ru = STAT_RU.get(stat_key, stat_key)
        val = stat_data['current']
        text += f"• {s_ru}: {val} (Улучшений: {stat_data['upgrades']}) - Улучшить: 💰 {upg_cost}\n"
        
        # Кнопка улучшения стата (передаем ключ стата)
        # Для cb_data: eq_0 (экипировка) или inv_5 (инвентарь)
        loc_idx = f"eq_{slot_name}" if is_equip else f"inv_{real_idx}"
        # cb data size limit is strict, we need to pack it tightly.
        # action="upg", idx=real_idx (или 999 для экип), stat=stat_key
        c_idx = 900 + ["weapon", "armor", "accessory"].index(slot_name) if is_equip else real_idx
        b.button(text=f"Улучшить {s_ru[:5]}.", callback_data=ItemCB(action="upg", idx=c_idx, stat=stat_key).pack())

    b.adjust(1)
    
    if is_equip:
        b.row(InlineKeyboardButton(text="Снять", callback_data=ItemCB(action="unequip", idx=c_idx).pack()))
    else:
        b.row(InlineKeyboardButton(text="Надеть", callback_data=ItemCB(action="equip", idx=real_idx).pack()))
        b.row(InlineKeyboardButton(text=f"Продать (💰 {item['sell_price']})", callback_data=ItemCB(action="sell", idx=real_idx).pack()))
        
    b.row(InlineKeyboardButton(text="🔙 Назад", callback_data=MenuCB(action="inv").pack()))
    
    await safe_edit(query.message, text, reply_markup=b.as_markup())

@dp.callback_query(ItemCB.filter(F.action == "equip"))
async def eq_item(query: CallbackQuery, callback_data: ItemCB):
    player = await get_player(query.from_user.id)
    idx = callback_data.idx
    if idx >= len(player.inventory): return
    
    item = player.inventory.pop(idx)
    old_equip = player.equip[item['type']]
    player.equip[item['type']] = item
    if old_equip:
        player.inventory.append(old_equip)
        
    await save_player(player)
    await query.answer(f"Экипировано: {item['name']}")
    await menu_inv(query, MenuCB(action="inv"))

@dp.callback_query(ItemCB.filter(F.action == "unequip"))
async def uneq_item(query: CallbackQuery, callback_data: ItemCB):
    player = await get_player(query.from_user.id)
    slot_idx = callback_data.idx - 900
    if slot_idx < 0 or slot_idx > 2: return
    slot_name = ["weapon", "armor", "accessory"][slot_idx]
    
    item = player.equip[slot_name]
    if item:
        if len(player.inventory) < player.inv_slots:
            player.inventory.append(item)
            player.equip[slot_name] = None
            await save_player(player)
            await query.answer("Предмет снят!")
            await menu_inv(query, MenuCB(action="inv"))
        else:
            await query.answer("В инвентаре нет места!", show_alert=True)

@dp.callback_query(ItemCB.filter(F.action == "sell"))
async def sell_item(query: CallbackQuery, callback_data: ItemCB):
    player = await get_player(query.from_user.id)
    idx = callback_data.idx
    if idx >= len(player.inventory): return
    
    item = player.inventory.pop(idx)
    earn = item.get("sell_price", 10)
    player.gold += earn
    await save_player(player)
    await query.answer(f"Продано за {earn} золота.")
    await menu_inv(query, MenuCB(action="inv"))

@dp.callback_query(ItemCB.filter(F.action == "upg"))
async def upg_item(query: CallbackQuery, callback_data: ItemCB):
    player = await get_player(query.from_user.id)
    idx = callback_data.idx
    stat_key = callback_data.stat
    
    is_equip = idx >= 900
    
    if is_equip:
        slot_name = ["weapon", "armor", "accessory"][idx - 900]
        item = player.equip[slot_name]
    else:
        if idx >= len(player.inventory): return
        item = player.inventory[idx]
        
    if not item or stat_key not in item["stats"]: return
    
    s_data = item["stats"][stat_key]
    upg_cost = int((s_data['base'] * 10) + (s_data['upgrades'] * s_data['base'] * 5))
    
    if player.gold >= upg_cost:
        player.gold -= upg_cost
        s_data['upgrades'] += 1
        
        # Прибавка = 20% от базового значения (но минимум 1, или 0.1 для %)
        is_percent = stat_key in ["crit_chance", "evasion", "atk_spd", "drop_chance", "lifesteal", "thorns"]
        min_inc = 0.1 if is_percent else 1.0
        inc = max(min_inc, s_data['base'] * 0.2)
        if stat_key == "atk_spd": inc = 0.05
        
        s_data['current'] = round(s_data['current'] + inc, 2)
        
        # Увеличиваем цену продажи
        item['sell_price'] += int(upg_cost * 0.3) 
        
        await save_player(player)
        await query.answer("Характеристика улучшена!")
        
        # Переотрисовываем меню предмета (нужно передать правильный изначальный btn_index, 
        # но так как мы его не сохранили, проще перекинуть в инвентарь или пересчитать)
        # Для простоты - кидаем обратно в инвентарь (или можно добавить логику восстановления)
        await menu_inv(query, MenuCB(action="inv"))
    else:
        await query.answer("Недостаточно золота!", show_alert=True)

# --- МАГАЗИН ---
@dp.callback_query(MenuCB.filter(F.action == "shop"))
async def menu_shop(query: CallbackQuery, callback_data: MenuCB):
    player = await get_player(query.from_user.id)
    await update_shop(player.difficulty)
    
    cost_slot = 500 + ( (player.inv_slots - 10) * 500 )
    
    text = "🏪 <b>Магазин (обновляется каждые 10 мин)</b>\nАссортимент:\n\n"
    
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    b = InlineKeyboardBuilder()
    
    idx = 1
    for i, entry in enumerate(db["shop"]["assortment"]):
        if entry["sold"]: continue
        if "item" in entry:
            it = entry["item"]
            stat_desc = ", ".join([STAT_RU.get(k, k) for k in it['stats'].keys()])
            price = it['sell_price'] * 2 # Цена покупки x2 от продажи
            text += f"{idx}. 📦 {it['name']} ({stat_desc})\n   Стоимость: 💰 {price}\n"
            b.button(text=f"{idx}", callback_data=ShopCB(action="buy_it", idx=i).pack())
            idx += 1
        elif "ability" in entry:
            ab = entry["ability"]
            text += f"{idx}. ✨ Навык: {ab['name']} (Урон/Хил: {ab['current_value']})\n   Стоимость: 💰 {ab['sell_price'] * 2}\n"
            b.button(text=f"{idx}", callback_data=ShopCB(action="buy_ab", idx=i).pack())
            idx += 1

    b.adjust(3)
    b.row(InlineKeyboardButton(text="Обновить товары (💰 100)", callback_data=ShopCB(action="refresh").pack()))
    b.row(InlineKeyboardButton(text=f"Слот инвентаря (💰 {cost_slot})", callback_data=ShopCB(action="slot").pack()))
    b.row(InlineKeyboardButton(text="Восстановить ХП/МП (💰 50)", callback_data=ShopCB(action="heal").pack()))
    b.row(InlineKeyboardButton(text="🔙 Назад", callback_data=MenuCB(action="profile").pack()))
    
    await safe_edit(query.message, text, reply_markup=b.as_markup())

@dp.callback_query(ShopCB.filter())
async def process_shop(query: CallbackQuery, callback_data: ShopCB):
    player = await get_player(query.from_user.id)
    act = callback_data.action
    
    if act == "refresh":
        if player.gold >= 100:
            player.gold -= 100
            await save_player(player)
            await update_shop(player.difficulty, force=True)
            await query.answer("Магазин обновлен!")
            await menu_shop(query, MenuCB(action="shop"))
        else:
            await query.answer("Недостаточно золота!", show_alert=True)
            
    elif act == "slot":
        cost = 500 + ( (player.inv_slots - 10) * 500 )
        if player.gold >= cost:
            player.gold -= cost
            player.inv_slots += 1
            await save_player(player)
            await query.answer("Слот инвентаря куплен!")
            await menu_shop(query, MenuCB(action="shop"))
        else:
            await query.answer("Недостаточно золота!", show_alert=True)
            
    elif act == "heal":
        if player.gold >= 50:
            player.gold -= 50
            player.stats['hp'] = get_total_stats(player)['max_hp']
            player.stats['mp'] = get_total_stats(player)['max_mp']
            await save_player(player)
            await query.answer("Здоровье и мана восстановлены!")
            await menu_shop(query, MenuCB(action="shop"))
        else:
            await query.answer("Недостаточно золота!", show_alert=True)
            
    elif act in ["buy_it", "buy_ab"]:
        idx = callback_data.idx
        entry = db["shop"]["assortment"][idx]
        if entry["sold"]: return await query.answer("Уже продано!")
        
        obj = entry.get("item") or entry.get("ability")
        price = obj.get("sell_price", 10) * 2
        
        if player.gold >= price:
            if act == "buy_it":
                if len(player.inventory) < player.inv_slots:
                    player.gold -= price
                    player.inventory.append(obj)
                    entry["sold"] = True
                    await save_player(player)
                    await query.answer("Предмет куплен!")
                else:
                    return await query.answer("Инвентарь полон!", show_alert=True)
            else:
                player.gold -= price
                player.abilities.append(obj)
                entry["sold"] = True
                await save_player(player)
                await query.answer("Навык куплен!")
                
            await menu_shop(query, MenuCB(action="shop"))
        else:
            await query.answer("Недостаточно золота!", show_alert=True)

# --- ЭКСПЕДИЦИЯ И НАВЫКИ ---
@dp.callback_query(MenuCB.filter(F.action == "exped"))
async def menu_exped(query: CallbackQuery, callback_data: MenuCB):
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    b = InlineKeyboardBuilder()
    b.button(text="Отправиться (30 мин)", callback_data=ActionCB(action="start_exped").pack())
    b.button(text="🔙 Назад", callback_data=MenuCB(action="profile").pack())
    b.adjust(1)
    await safe_edit(query.message, "🧭 <b>Экспедиция</b>\nБезопасный поиск золота и ресурсов. Вы не сможете сражаться или тренироваться 30 минут.", reply_markup=b.as_markup())

@dp.callback_query(ActionCB.filter(F.action == "start_exped"))
async def start_exped(query: CallbackQuery, callback_data: ActionCB):
    player = await get_player(query.from_user.id)
    player.state = 'expedition'
    player.state_end_time = time.time() + CONFIG["time_expedition"]
    await save_player(player)
    await safe_edit(query.message, "Вы отправились в экспедицию. Вернитесь через 30 минут.", reply_markup=cancel_kbd())

@dp.callback_query(MenuCB.filter(F.action == "skills"))
async def menu_skills(query: CallbackQuery, callback_data: MenuCB):
    player = await get_player(query.from_user.id)
    
    text = "✨ <b>Ваши Навыки</b>\n\nАктивные:\n"
    for i, ab in enumerate(player.active_abilities):
        text += f"Слот {i+1}: {ab['name'] if ab else 'Пусто'} (МП: {ab['mp_cost'] if ab else 0})\n"
        
    text += "\nДоступные навыки:\n"
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    b = InlineKeyboardBuilder()
    
    for i, ab in enumerate(player.abilities):
        upg_cost = int(ab['base_value'] * 10) + (ab['upgrades'] * int(ab['base_value'] * 5))
        text += f"{i+1}. {ab['name']} | Сила: {ab['current_value']} | МП: {ab['mp_cost']}\n"
        b.button(text=f"Слот 1: {i+1}", callback_data=SkillCB(action="eq", idx=i, slot=0).pack())
        b.button(text=f"Слот 2: {i+1}", callback_data=SkillCB(action="eq", idx=i, slot=1).pack())
        b.button(text=f"Улучшить {i+1} (💰 {upg_cost})", callback_data=SkillCB(action="upg", idx=i).pack())
        
    b.adjust(2, 1)
    b.row(InlineKeyboardButton(text="Снять все навыки", callback_data=SkillCB(action="uneq", idx=0).pack()))
    b.row(InlineKeyboardButton(text="🔙 Назад", callback_data=MenuCB(action="profile").pack()))
    
    await safe_edit(query.message, text, reply_markup=b.as_markup())

@dp.callback_query(SkillCB.filter())
async def process_skills(query: CallbackQuery, callback_data: SkillCB):
    player = await get_player(query.from_user.id)
    act = callback_data.action
    idx = callback_data.idx
    
    if act == "uneq":
        player.active_abilities = [None, None]
        await save_player(player)
        await query.answer("Навыки сняты.")
        await menu_skills(query, MenuCB(action="skills"))
        
    elif act == "eq":
        if idx >= len(player.abilities): return
        player.active_abilities[callback_data.slot] = player.abilities[idx]
        await save_player(player)
        await query.answer(f"Навык установлен в слот {callback_data.slot + 1}.")
        await menu_skills(query, MenuCB(action="skills"))
        
    elif act == "upg":
        if idx >= len(player.abilities): return
        ab = player.abilities[idx]
        upg_cost = int(ab['base_value'] * 10) + (ab['upgrades'] * int(ab['base_value'] * 5))
        
        if player.gold >= upg_cost:
            player.gold -= upg_cost
            ab['upgrades'] += 1
            ab['current_value'] += max(1, int(ab['base_value'] * 0.2))
            ab['sell_price'] += int(upg_cost * 0.3)
            await save_player(player)
            await query.answer("Навык улучшен!")
            await menu_skills(query, MenuCB(action="skills"))
        else:
            await query.answer("Недостаточно золота!", show_alert=True)

# ==========================================
# ЗАПУСК БОТА (AIOGRAM)
# ==========================================
async def main():
    print("Запуск бота на aiogram 3.x...")
    await load_db()
    
    # Запуск фоновой задачи
    asyncio.create_task(background_worker())
    
    # Запуск поллинга
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
