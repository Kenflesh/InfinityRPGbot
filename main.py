import asyncio
import json
import time
import random
import os
import logging
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters.callback_data import CallbackData
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.dispatcher.event.bases import SkipHandler

TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

logging.basicConfig(level=logging.INFO)

DATA_DIR = 'data'
os.makedirs(DATA_DIR, exist_ok=True)
DB_FILE = os.path.join(DATA_DIR, 'database.json')

db_lock = asyncio.Lock()
db = {}

STAT_RU = {
    "max_hp": "Макс. Здоровье", "hp": "Здоровье", "max_mp": "Макс. Мана", "mp": "Мана",
    "atk": "Физ. Атака", "def": "Физ. Защита", "m_shield": "Магический Щит",
    "crit_chance": "Шанс Крита", "crit_damage": "Крит. Урон", "accuracy": "Точность",
    "evasion_rating": "Уклонение", "atk_spd": "Скор. Атаки",
    "hp_regen": "Реген Здоровья", "mp_regen": "Реген Маны",
    "drop_chance": "Множитель Дропа",
    "lifesteal": "Вампиризм", "armor_pen": "Пробитие Брони",
    "magic_atk": "Маг. Атака", "magic_res": "Маг. Сопротивление", "thorns": "Шипы"
}

STAT_EMOJI = {
    "max_hp": "❤️", "hp": "❤️", "max_mp": "💧", "mp": "💧",
    "atk": "🗡️", "def": "🛡️", "m_shield": "✨",
    "crit_chance": "💥", "crit_damage": "💢", "accuracy": "🎯", "evasion_rating": "💨",
    "atk_spd": "⚡", "hp_regen": "🩹", "mp_regen": "🔮",
    "drop_chance": "🍀", "lifesteal": "🦇", "armor_pen": "🪓",
    "magic_atk": "🔮", "magic_res": "🌀", "thorns": "🌵"
}

TRAINING_INCREMENTS = {
    "max_hp": 1.0,
    "max_mp": 1.0,
    "atk": 0.1,
    "def": 0.1,
    "m_shield": 0.5,
    "crit_chance": 0.02,
    "crit_damage": 0.5,
    "accuracy": 0.05,
    "evasion_rating": 0.05,
    "atk_spd": 0.005,
    "hp_regen": 0.02,
    "mp_regen": 0.02,
    "drop_chance": 0.002,
    "lifesteal": 0.002,
    "armor_pen": 0.05,
    "magic_atk": 0.1,
    "magic_res": 0.1,
    "thorns": 0.02
}

PREFIXES = ["Свирепый", "Древний", "Пылающий", "Забытый", "Проклятый", "Святой", "Теневой", "Искрящийся", "Тяжелый", "Легкий"]
NOUNS = {
    "weapon": ["Меч", "Топор", "Кинжал", "Посох", "Лук", "Молот", "Копье"],
    "armor": ["Доспех", "Шлем", "Щит", "Нагрудник", "Плащ", "Мантия"],
    "accessory": ["Амулет", "Кольцо", "Талисман", "Оберег", "Браслет"]
}
SUFFIXES = ["Убийцы", "Короля", "Гоблина", "Дракона", "Света", "Тьмы", "Крови", "Ветров", "Пустоты", "Жизни"]

CONFIG = {
    "time_train": 10,
    "time_death": 600,
    "time_expedition": 300,
    "time_shop_update": 300,
    "time_potion_update": 300,

    "enemy_base_stats": {
        "hp": 10, "atk": 5, "def": 2, "atk_spd": 0.1, "accuracy": 20, "evasion_rating": 10,
        "magic_atk": 0, "magic_res": 0
    },
    "enemy_stat_scale": {
        "hp": 25, "atk": 5, "def": 1, "atk_spd": 0.02, "accuracy": 1.0, "evasion_rating": 0.05,
        "magic_atk": 1.5, "magic_res": 0.5
    }
}

KILLS_TO_UNLOCK_NEXT = 5

class Form(StatesGroup):
    waiting_for_difficulty = State()
    waiting_for_shop_rarity = State()
    waiting_for_sell_price = State()   # для массовой продажи по цене

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

class PotionCB(CallbackData, prefix="pot"):
    action: str
    idx: int = 0

class SellMassCB(CallbackData, prefix="sellmass"):
    action: str   # "all", "price", "menu"

async def load_db():
    global db
    async with db_lock:
        if os.path.exists(DB_FILE):
            with open(DB_FILE, 'r', encoding='utf-8') as f:
                db = json.load(f)
        else:
            db = {
                "players": {}
            }
            _save_db_unlocked()

async def save_db():
    async with db_lock:
        _save_db_unlocked()

def _save_db_unlocked():
    with open(DB_FILE, 'w', encoding='utf-8') as f:
        json.dump(db, f, ensure_ascii=False, indent=4)

class Player:
    def __init__(self, uid, name):
        self.uid = str(uid)
        self.name = name
        self.gold = 100
        self.shop_rarity = 1
        self.shop_assortment = []
        self.shop_last_update = 0
        self.potion_shop_level = 0
        self.potion_shop_assortment = []
        self.potion_shop_last_update = 0

        self.stats = {
            "max_hp": 100, "hp": 100, "max_mp": 50, "mp": 50,
            "atk": 10, "def": 5, "m_shield": 0,
            "crit_chance": 5.0, "crit_damage": 200.0, "accuracy": 20.0, "evasion_rating": 5.0,
            "atk_spd": 0.15,
            "hp_regen": 1.0, "mp_regen": 1.0, "drop_chance": 1.0,
            "lifesteal": 0.0, "armor_pen": 0, "magic_atk": 0, "magic_res": 0, "thorns": 0.0
        }
        self.stat_upgrades = {k: 0 for k in self.stats.keys()}

        self.inv_slots = 10
        self.inventory = []
        self.equip = {"weapon": None, "armor": None, "accessory": None}

        self.abilities = []
        self.active_abilities = [None, None]

        self.state = 'idle'
        self.state_end_time = 0
        self.training_stat = None

        self.max_unlocked_difficulty = 1
        self.kills_per_difficulty = {}
        self.current_difficulty = 1

        self.last_regen_time = time.time()
        self.percent_bonuses = {}

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
        if not hasattr(p, 'percent_bonuses'): p.percent_bonuses = {}
        if not hasattr(p, 'shop_rarity'):
            if hasattr(p, 'shop_difficulty'):
                p.shop_rarity = p.shop_difficulty
            else:
                p.shop_rarity = 1
        if hasattr(p, 'shop_difficulty'):
            del p.shop_difficulty
        if not hasattr(p, 'shop_assortment'): p.shop_assortment = []
        if not hasattr(p, 'shop_last_update'): p.shop_last_update = 0
        if not hasattr(p, 'potion_shop_level'): p.potion_shop_level = 0
        if not hasattr(p, 'potion_shop_assortment'): p.potion_shop_assortment = []
        if not hasattr(p, 'potion_shop_last_update'): p.potion_shop_last_update = 0
        if not hasattr(p, 'max_unlocked_difficulty'): p.max_unlocked_difficulty = 1
        if not hasattr(p, 'kills_per_difficulty'): p.kills_per_difficulty = {}
        if not hasattr(p, 'current_difficulty'): p.current_difficulty = 1
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
                        player.state = 'idle'
                        try:
                            await bot.send_message(uid,
                                                   "👼 Вы воскресли и готовы к новым битвам!",
                                                   reply_markup=main_menu_kbd())
                        except:
                            pass

                    elif player.state == 'training':
                        stat = player.training_stat

                        increment = TRAINING_INCREMENTS.get(stat, 0.01)
                        player.stats[stat] += increment
                        player.stat_upgrades[stat] += 1
                        player.state = 'idle'
                        player.training_stat = None
                        try:
                            await bot.send_message(uid,
                                                   f"🏋️‍♂️ Тренировка завершена! Характеристика <b>{STAT_RU.get(stat, stat)}</b> улучшена.",
                                                   reply_markup=main_menu_kbd())
                        except:
                            pass

                    elif player.state == 'expedition':
                        gold_found = random.randint(100, 300) + (player.difficulty * 30)
                        player.gold += gold_found
                        msg = f"🧭 Экспедиция завершена!\nВы нашли: 💰 {gold_found} золота."

                        drop_chance = 0.4
                        items_found = 0
                        while random.random() < drop_chance and items_found < 3:
                            eff_diff = max(1, int(player.difficulty * player.stats["drop_chance"]))
                            item = generate_item(eff_diff)
                            if len(player.inventory) < player.inv_slots:
                                player.inventory.append(item)
                                items_found += 1
                                msg += f"\n📦 Найден предмет: {item['name']}"
                            else:
                                msg += "\n📦 Инвентарь полон, предмет потерян!"
                                break
                            drop_chance *= 0.5

                        player.state = 'idle'
                        try:
                            await bot.send_message(uid, msg, reply_markup=main_menu_kbd())
                        except:
                            pass

                    db['players'][uid] = player.__dict__
                    changed = True

        if changed:
            _save_db_unlocked()

def generate_item_name(i_type):
    prefix = random.choice(PREFIXES)
    noun = random.choice(NOUNS[i_type])
    suffix = random.choice(SUFFIXES)
    return f"{prefix} {noun} {suffix}"

def generate_item(rarity):
    i_type = random.choice(["weapon", "armor", "accessory"])
    name = generate_item_name(i_type)

    base_stats_count = 1
    extra_chance = min(0.8, 0.2 * rarity)
    stats_count = base_stats_count
    while random.random() < extra_chance and stats_count < 5:
        stats_count += 1
        extra_chance *= 0.5

    available_stats = {
        "weapon": ["atk", "magic_atk", "armor_pen", "crit_chance", "crit_damage", "atk_spd", "accuracy"],
        "armor": ["def", "magic_res", "max_hp", "evasion_rating", "thorns", "accuracy"],
        "accessory": ["hp_regen", "mp_regen", "lifesteal", "max_mp", "drop_chance", "crit_damage", "evasion_rating"]
    }

    chosen_stats = random.sample(available_stats[i_type], min(stats_count, len(available_stats[i_type])))
    item_stats = {}

    stat_mult = {
        "atk": 0.2, "magic_atk": 0.2, "def": 0.2, "magic_res": 0.2,
        "max_hp": 0.5, "max_mp": 0.5, "hp_regen": 0.1, "mp_regen": 0.1,
        "armor_pen": 0.5, "crit_chance": 0.2, "crit_damage": 0.2,
        "accuracy": 0.5, "evasion_rating": 0.25,
        "atk_spd": 0.01, "drop_chance": 0.01, "lifesteal": 0.01, "thorns": 0.01
    }

    base_price = 0
    for stat in chosen_stats:
        is_percent = stat in ["crit_chance", "crit_damage", "atk_spd", "drop_chance", "lifesteal", "thorns", "accuracy", "evasion_rating"]
        mult = stat_mult.get(stat, 1.0)

        raw = (rarity * 0.25 * random.uniform(0.8, 1.2)) * mult
        integer_stats = ["atk", "def", "max_hp", "max_mp", "magic_atk", "magic_res", "armor_pen"]
        if stat in integer_stats:
            base_val = max(1, int(raw))
        else:
            base_val = max(0.01, round(raw, 2))
        if stat == "atk_spd":
            base_val = round(base_val / 20.0, 2)

        bonus_type = "flat"
        if stat in ["atk", "def", "max_hp", "max_mp", "magic_atk", "magic_res", "hp_regen", "mp_regen", "accuracy", "evasion_rating"]:
            bonus_type = random.choice(["flat", "percent"])

        upgrade_price_mult = random.uniform(0.8, 2.0)

        item_stats[stat] = {
            "base": base_val,
            "current": base_val,
            "upgrades": 0,
            "bonus_type": bonus_type,
            "upgrade_price_mult": upgrade_price_mult
        }
        base_price += int(base_val * (100 if is_percent else 10))

    return {
        "id": "i_" + str(time.time()).replace(".", "") + str(random.randint(10, 99)),
        "name": name,
        "type": i_type,
        "stats": item_stats,
        "sell_price": max(10, int(base_price * 0.25))
    }

def generate_ability(difficulty):
    a_type = random.choice(["heal", "power_strike", "magic_blast"])
    base_val = int(difficulty * random.uniform(4.0, 6.0))
    mp_cost = int(10 + (difficulty * 2))
    names = {"heal": "Исцеление", "power_strike": "Мощный Удар", "magic_blast": "Взрыв Магии"}
    return {
        "id": "a_" + str(time.time()).replace(".", "") + str(random.randint(10, 99)),
        "name": f"{names[a_type]} {random.choice(['Света', 'Тьмы', 'Жизни'])}",
        "type": a_type,
        "base_value": base_val,
        "current_value": base_val,
        "upgrades": 0,
        "mp_cost": mp_cost,
        "sell_price": max(20, int(base_val * 5))
    }

def generate_potion(level):
    potion_stats = [s for s in STAT_RU.keys() if s not in ["hp", "mp"]]
    stat = random.choice(potion_stats)
    potion_type = random.choice(["flat", "percent"])
    is_percent = potion_type == "percent"

    strong_stats = ["atk_spd", "lifesteal", "thorns", "crit_chance", "crit_damage", "accuracy", "evasion_rating"]

    if stat in strong_stats:
        if is_percent:
            base_value = round(random.uniform(0.1, 1.0), 1)
        else:
            base_value = round(random.uniform(0.02, 0.5), 2)
    else:
        if is_percent:
            base_value = round(random.uniform(0.2, 2.0), 1)
        else:
            base_value = random.randint(1, 3)

    multiplier = 1 + level
    value = base_value * multiplier
    if not is_percent and stat not in strong_stats:
        value = int(value)
    else:
        value = round(value, 2)

    base_price = int(base_value * random.uniform(20, 50) + 50)
    price = int(base_price * multiplier * (1 + 0.7 * level))
    price = max(50, min(5000, price))

    name = f"Зелье {STAT_RU[stat]} +{value}{'%' if is_percent else ''} (ур.{level})"
    return {
        "stat": stat,
        "value": value,
        "price": price,
        "type": potion_type,
        "name": name
    }

def get_evasion_chance(acc, eva):
    if acc + eva == 0:
        return 0
    return eva / (acc + eva) * 100

def generate_enemy(difficulty):
    variance = lambda: random.uniform(0.6, 1.2)
    e_stats = {}
    for k in ["hp", "atk", "def", "magic_atk", "magic_res", "accuracy", "evasion_rating"]:
        base = CONFIG["enemy_base_stats"].get(k, 0)
        scale = CONFIG["enemy_stat_scale"].get(k, 0)
        val = (base + difficulty * scale) * variance()
        if k in ["hp", "atk", "def", "magic_atk", "magic_res"]:
            e_stats[k] = max(0, int(val))
        else:
            e_stats[k] = max(0, val)

    e_stats["atk_spd"] = max(0.05, (CONFIG["enemy_base_stats"]["atk_spd"] + difficulty * CONFIG["enemy_stat_scale"]["atk_spd"]) * variance())

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
        "accuracy": e_stats["accuracy"],
        "evasion_rating": e_stats["evasion_rating"],
        "power_mult": power_multiplier
    }

async def update_shop(player, force=False):
    now = time.time()
    if force or now - player.shop_last_update > CONFIG["time_shop_update"]:
        player.shop_assortment = []
        # Предметы
        for _ in range(5):
            item = generate_item(player.shop_rarity)
            price = int(item['sell_price'] * 3 * (1 + player.shop_rarity / 5))
            player.shop_assortment.append({"item": item, "price": price, "sold": False})
        player.shop_last_update = now
        await save_player(player)

async def update_potion_shop(player, force=False):
    now = time.time()
    if force or now - player.potion_shop_last_update > CONFIG["time_potion_update"]:
        player.potion_shop_assortment = []
        for _ in range(5):
            player.potion_shop_assortment.append({"potion": generate_potion(player.potion_shop_level), "sold": False})
        player.potion_shop_last_update = now
        await save_player(player)

def get_total_stats(player):
    total = player.stats.copy()
    flat_items = {k: 0 for k in total.keys()}
    percent_items = {k: 0 for k in total.keys()}
    for eq_type, item in player.equip.items():
        if item:
            for stat_name, stat_data in item["stats"].items():
                if stat_name in total:
                    current_val = stat_data['base'] * (stat_data['upgrades'] + 1)
                    if stat_data.get('bonus_type') == 'percent':
                        percent_items[stat_name] += current_val
                    else:
                        flat_items[stat_name] += current_val
    percent_potions = player.percent_bonuses.copy()
    for stat in total.keys():
        base = total[stat]
        flat = flat_items.get(stat, 0)
        percent_sum = percent_items.get(stat, 0) + percent_potions.get(stat, 0)
        total[stat] = (base + flat) * (1 + percent_sum / 100.0)
    total['hp'] = min(total['hp'], total['max_hp'])
    total['mp'] = min(total['mp'], total['max_mp'])
    return total

def simulate_combat_realtime(player, enemy):
    p_stats = get_total_stats(player)
    e_stats = enemy.copy()

    current_shield = p_stats['m_shield']
    log = [
        f"⚔️ <b>Бой начался!\n\nУгроза: {enemy['difficulty']}</b>\n",
        f"\n👤 <b>Вы:\n{player.name}</b>:\n❤️ {p_stats['hp']:.1f}/{p_stats['max_hp']:.1f} | 🛡 {current_shield:.1f} | 💧 {p_stats['mp']:.1f}/{p_stats['max_mp']:.1f}\n🗡 АТК: {p_stats['atk']:.2f} | ⚡ Скор: {p_stats['atk_spd']:.2f}",
        f"   🎯 Точность: {p_stats['accuracy']:.2f} | 💨 Уклонение: {p_stats['evasion_rating']:.2f}",
        f"\n👹 <b>Враг:\n{enemy['name']}</b>: ❤️ {enemy['hp']:.1f}/{enemy['max_hp']:.1f} | 🗡 АТК: {enemy['atk']:.2f} | ⚡ Скор: {enemy['atk_spd']:.2f}",
        f"   🎯 Точность: {e_stats['accuracy']:.2f} | 💨 Уклонение: {e_stats['evasion_rating']:.2f}",
        f"\n\n 🎯 Шанс вашего уклонения: {get_evasion_chance(e_stats['accuracy'], p_stats['evasion_rating']):.1f}% | Шанс уклонения врага: {get_evasion_chance(p_stats['accuracy'], e_stats['evasion_rating']):.1f}%",
        "=" * 40
    ]

    p_cooldown = 1.0 / max(0.05, p_stats["atk_spd"])
    e_cooldown = 1.0 / max(0.05, e_stats["atk_spd"])

    tick = 0.1
    time_elapsed = 0.0
    max_time = 300.0

    while p_stats["hp"] > 0 and e_stats["hp"] > 0 and time_elapsed < max_time:
        if abs((time_elapsed % 1.0) - 0.0) < 0.05:
            p_stats["hp"] = min(p_stats["max_hp"], p_stats["hp"] + p_stats["hp_regen"] / 60.0)
            p_stats["mp"] = min(p_stats["max_mp"], p_stats["mp"] + p_stats["mp_regen"] / 60.0)

        p_cooldown -= tick
        e_cooldown -= tick

        if p_cooldown <= 0 and p_stats["hp"] > 0:
            p_cooldown += 1.0 / max(0.05, p_stats["atk_spd"])
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
                if random.random() * 100 > get_evasion_chance(p_stats["accuracy"], e_stats["evasion_rating"]):
                    eff_def = max(0, e_stats["def"] - p_stats["armor_pen"])
                    dmg = max(0, p_stats["atk"] - eff_def)
                    magic_dmg = max(0, p_stats["magic_atk"] - e_stats["magic_res"])
                    total_dmg = dmg + magic_dmg
                    if total_dmg <= 0: total_dmg = 1

                    dmg_mult = random.uniform(0.8, 1.2)
                    total_dmg = int(total_dmg * dmg_mult)

                    crit_chance = p_stats["crit_chance"]
                    crit_damage = p_stats.get("crit_damage", 200) / 100.0
                    num_crits = int(crit_chance // 100)
                    extra_chance = crit_chance % 100
                    crit_mult = 1.0
                    for _ in range(num_crits):
                        crit_mult *= crit_damage
                    if random.random() * 100 < extra_chance:
                        crit_mult *= crit_damage
                    total_dmg = int(total_dmg * crit_mult)

                    if crit_mult > 1.0:
                        log.append(f"[{time_elapsed:.1f}с] 🔥 КРИТ(x{crit_mult:.2f})! Вы нанесли {total_dmg} урона. (Враг: {max(0, e_stats['hp']):.1f}/{e_stats['max_hp']})")
                    else:
                        log.append(f"[{time_elapsed:.1f}с] 🗡 Вы нанесли {total_dmg} урона. (Враг: {max(0, e_stats['hp']):.1f}/{e_stats['max_hp']})")

                    e_stats["hp"] -= total_dmg

                    if p_stats["lifesteal"] > 0:
                        ls_heal = total_dmg * (p_stats["lifesteal"] / 100.0)
                        p_stats["hp"] = min(p_stats["max_hp"], p_stats["hp"] + ls_heal)
                        log.append(f"[{time_elapsed:.1f}с] 🩸 Вампиризм восстановил {ls_heal:.1f} ХП!")
                else:
                    log.append(f"[{time_elapsed:.1f}с] 💨 Враг уклонился!")

        if e_stats["hp"] > 0 and e_cooldown <= 0:
            e_cooldown += 1.0 / max(0.05, e_stats["atk_spd"])
            if random.random() * 100 > get_evasion_chance(e_stats["accuracy"], p_stats["evasion_rating"]):
                eff_def = p_stats["def"]
                dmg = max(0, e_stats["atk"] - eff_def)
                magic_dmg = max(0, e_stats["magic_atk"] - p_stats["magic_res"])
                total_dmg = dmg + magic_dmg
                if total_dmg <= 0: total_dmg = 1

                if current_shield > 0:
                    absorbed = min(total_dmg, current_shield)
                    current_shield -= absorbed
                    total_dmg -= absorbed
                    log.append(f"[{time_elapsed:.1f}с] 🛡 Щит поглотил {absorbed:.1f} урона. Осталось щита: {current_shield:.1f}")

                if total_dmg > 0:
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
        return False, log, "💀 Вы погибли! Восстановление займет 15 минут."
    else:
        return True, log, "🏆 Вы победили!"

def main_menu_kbd():
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    builder.button(text="🗡 Охота", callback_data=MenuCB(action="hunt").pack())
    builder.button(text="🏋️ Тренировка", callback_data=MenuCB(action="train").pack())
    builder.button(text="🎒 Инвентарь", callback_data=MenuCB(action="inv").pack())
    builder.button(text="✨ Навыки", callback_data=MenuCB(action="skills").pack())
    builder.button(text="🏪 Магазин", callback_data=MenuCB(action="shop").pack())
    builder.button(text="🧪 Зелья", callback_data=MenuCB(action="potions").pack())
    builder.button(text="🧭 Экспедиция", callback_data=MenuCB(action="exped").pack())
    builder.button(text="👤 Герой", callback_data=MenuCB(action="profile").pack())
    builder.adjust(2, 2, 2, 2)
    return builder.as_markup()

def waiting_kbd(state_end_time):
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Отменить", callback_data=ActionCB(action="cancel").pack())
    builder.button(text="⏳ Осталось времени", callback_data=ActionCB(action="check_time").pack())
    builder.adjust(1)
    return builder.as_markup()

def dead_kbd():
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 В главное меню", callback_data=MenuCB(action="profile").pack())
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

async def get_item_view_data(player: Player, idx: int):
    is_equip = False
    real_idx = -1
    item = None
    slot_name = ""

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
        return None, None

    type_ru = {"weapon": "Оружие", "armor": "Броня", "accessory": "Амулет"}[item['type']]
    text = f"💰 Золото: {player.gold}\n📦 <b>{item['name']}</b> ({'Надето' if is_equip else 'В сумке'})\nТип: {type_ru}\n\nХарактеристики:\n"

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    b = InlineKeyboardBuilder()

    for stat_key, stat_data in item["stats"].items():
        is_percent = stat_key in ["crit_chance", "crit_damage", "atk_spd", "drop_chance", "lifesteal", "thorns", "accuracy", "evasion_rating"]
        raw_cost = (stat_data['base'] * 50 + stat_data['upgrades'] * stat_data['base'] * 20) * stat_data.get('upgrade_price_mult', 1.0)
        upg_cost = max(250, int(raw_cost))
        s_ru = f"{STAT_EMOJI.get(stat_key, '')} {STAT_RU.get(stat_key, stat_key)}"
        bonus_type = stat_data.get('bonus_type', 'flat')
        bonus_symbol = '%' if bonus_type == 'percent' else ''
        text += f"• {s_ru}: {stat_data['current']:.2f}{bonus_symbol} (база {stat_data['base']:.2f}{bonus_symbol}, улучшений: {stat_data['upgrades']}) - Улучшить: 💰 {upg_cost} (+{stat_data['base']:.2f}{bonus_symbol})\n"
        c_idx = 900 + ["weapon", "armor", "accessory"].index(slot_name) if is_equip else real_idx
        b.button(text=f"Улучшить {s_ru}", callback_data=ItemCB(action="upg", idx=c_idx, stat=stat_key).pack())

    b.adjust(1)

    if is_equip:
        b.row(InlineKeyboardButton(text="Снять", callback_data=ItemCB(action="unequip", idx=c_idx).pack()))
    else:
        b.row(InlineKeyboardButton(text="Надеть", callback_data=ItemCB(action="equip", idx=real_idx).pack()))
        b.row(InlineKeyboardButton(text=f"Продать (💰 {item['sell_price']})", callback_data=ItemCB(action="sell", idx=real_idx).pack()))

    b.row(InlineKeyboardButton(text="🔙 Назад", callback_data=MenuCB(action="inv").pack()))

    return text, b.as_markup()

# ==========================================
# ОБРАБОТЧИКИ
# ==========================================
@dp.message(CommandStart())
async def cmd_start(message: Message):
    await load_db()
    player = await get_player(message.from_user.id, message.from_user.first_name)
    await message.answer(
        f"Добро пожаловать, <b>{player.name}</b>!\nТвоя сила ограничивается только временем.",
        reply_markup=main_menu_kbd()
    )

@dp.message(Command("relive"))
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

@dp.message(Command("destroysave"))
async def cmd_destroy_save(message: Message):
    uid = str(message.from_user.id)
    async with db_lock:
        if uid in db['players']:
            del db['players'][uid]
            _save_db_unlocked()
    await message.answer("🗑 Ваше сохранение удалено. Напишите /start для нового начала.")

@dp.message(Command("givegold"))
async def cmd_give_gold(message: Message):
    args = message.text.split()
    if len(args) != 2:
        await message.answer("Использование: /givegold <сумма>")
        return
    try:
        amount = int(args[1])
        if amount <= 0:
            raise ValueError
    except:
        await message.answer("Сумма должна быть положительным числом.")
        return
    player = await get_player(message.from_user.id)
    player.gold += amount
    await save_player(player)
    await message.answer(f"💰 Вам начислено {amount} золота. Теперь у вас {player.gold} золота.")

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

@dp.callback_query(ActionCB.filter(F.action == "check_time"))
async def cb_check_time(query: CallbackQuery, callback_data: ActionCB):
    player = await get_player(query.from_user.id)
    if player.state != 'idle':
        remaining = player.state_end_time - time.time()
        minutes = int(remaining // 60)
        seconds = int(remaining % 60)
        state_rus = {"training": "тренируетесь", "expedition": "в экспедиции", "dead": "мертвы"}.get(player.state, player.state)
        await query.answer(f"Вы {state_rus}. Осталось: {minutes} мин {seconds} сек.", show_alert=True)
    else:
        await query.answer("Вы сейчас не заняты.", show_alert=True)

@dp.callback_query()
async def process_any_callback(query: CallbackQuery, bot: Bot):
    if query.data and (query.data.startswith("act:cancel") or query.data.startswith("act:check_time")):
        return
    await load_db()
    player = await get_player(query.from_user.id)
    await apply_passive_regen(player)

    if player.state != 'idle':
        remaining = player.state_end_time - time.time()
        minutes = int(remaining // 60)
        seconds = int(remaining % 60)
        if player.state == 'dead':
            await query.answer(f"Вы мертвы. Воскрешение через: {minutes} мин {seconds} сек.", show_alert=True)
        else:
            state_rus = {"training": "Тренируетесь", "expedition": "В экспедиции"}.get(player.state, player.state)
            await query.answer(f"Вы заняты ({state_rus}). Осталось: {minutes} мин {seconds} сек.", show_alert=True)
        return

    raise SkipHandler()

@dp.callback_query(MenuCB.filter(F.action == "profile"))
async def menu_profile(query: CallbackQuery, callback_data: MenuCB):
    player = await get_player(query.from_user.id)
    t_stats = get_total_stats(player)

    text = f"👤 <b>Профиль: {player.name}</b>\n💰 Золото: {player.gold}\n🏪 Редкость магазина: {player.shop_rarity}\n🧪 Уровень лавки зелий: {player.potion_shop_level}\n"
    text += f"🔓 Доступная угроза: {player.max_unlocked_difficulty}\n\n"
    text += f"{STAT_EMOJI['hp']} {STAT_RU['hp']}: {player.stats['hp']:.1f}/{t_stats['max_hp']:.1f} (+{t_stats['hp_regen']:.2f}/мин)\n"
    text += f"{STAT_EMOJI['m_shield']} {STAT_RU['m_shield']}: {t_stats['m_shield']:.1f} (восстанавливается каждый бой)\n"
    text += f"{STAT_EMOJI['mp']} {STAT_RU['mp']}: {player.stats['mp']:.1f}/{t_stats['max_mp']:.1f} (+{t_stats['mp_regen']:.2f}/мин)\n"
    text += f"{STAT_EMOJI['atk']} {STAT_RU['atk']}: {t_stats['atk']:.2f} | {STAT_EMOJI['magic_atk']} {STAT_RU['magic_atk']}: {t_stats['magic_atk']:.2f}\n"
    text += f"{STAT_EMOJI['def']} {STAT_RU['def']}: {t_stats['def']:.2f} | {STAT_EMOJI['magic_res']} {STAT_RU['magic_res']}: {t_stats['magic_res']:.2f}\n"
    text += f"{STAT_EMOJI['crit_chance']} {STAT_RU['crit_chance']}: {t_stats['crit_chance']:.2f}% | {STAT_EMOJI['crit_damage']} {STAT_RU['crit_damage']}: {t_stats['crit_damage']:.2f}%\n"
    text += f"{STAT_EMOJI['accuracy']} {STAT_RU['accuracy']}: {t_stats['accuracy']:.2f} | {STAT_EMOJI['evasion_rating']} {STAT_RU['evasion_rating']}: {t_stats['evasion_rating']:.2f}\n"
    text += f"{STAT_EMOJI['lifesteal']} {STAT_RU['lifesteal']}: {t_stats['lifesteal']:.2f}% | {STAT_EMOJI['thorns']} {STAT_RU['thorns']}: {t_stats['thorns']:.2f}%\n"
    text += f"{STAT_EMOJI['armor_pen']} {STAT_RU['armor_pen']}: {t_stats['armor_pen']} | {STAT_EMOJI['m_shield']} {STAT_RU['m_shield']}: {t_stats['m_shield']}\n"
    text += f"{STAT_EMOJI['atk_spd']} {STAT_RU['atk_spd']}: {t_stats['atk_spd']:.2f} | {STAT_EMOJI['drop_chance']} {STAT_RU['drop_chance']}: x{t_stats['drop_chance']:.2f}\n"

    await safe_edit(query.message, text, reply_markup=main_menu_kbd())

@dp.callback_query(MenuCB.filter(F.action == "train"))
async def menu_train(query: CallbackQuery, callback_data: MenuCB):
    player = await get_player(query.from_user.id)
    page = callback_data.page
    stats = [s for s in player.stat_upgrades.keys() if s not in ["hp", "mp"]]

    per_page = 6
    start = page * per_page
    end = start + per_page

    text = f"💰 Золото: {player.gold}\n🏋️ <b>Тренировка (1 минута)</b>\nВыберите характеристику:\n\n"

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()

    for i, stat in enumerate(stats[start:end], start=1):
        upgrades = player.stat_upgrades[stat]
        stat_name = f"{STAT_EMOJI.get(stat, '')} {STAT_RU.get(stat, stat)}"
        increment_value = TRAINING_INCREMENTS.get(stat, 0.01)
        text += f"{i}. <b>{stat_name}</b> (+{increment_value})\n"
        builder.button(text=f"{i}", callback_data=TrainCB(stat=stat).pack())

    builder.adjust(3)

    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(text="⬅️", callback_data=MenuCB(action="train", page=page-1).pack()))
    if end < len(stats):
        nav_row.append(InlineKeyboardButton(text="➡️", callback_data=MenuCB(action="train", page=page+1).pack()))
    if nav_row:
        builder.row(*nav_row)

    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data=MenuCB(action="profile").pack()))

    await safe_edit(query.message, text, reply_markup=builder.as_markup())

@dp.callback_query(TrainCB.filter())
async def process_train(query: CallbackQuery, callback_data: TrainCB):
    player = await get_player(query.from_user.id)
    stat = callback_data.stat
    player.state = 'training'
    player.training_stat = stat
    player.state_end_time = time.time() + CONFIG["time_train"]
    await save_player(player)
    await safe_edit(query.message,
                    f"Вы начали тренировку <b>{STAT_RU.get(stat, stat)}</b>. Вернитесь через 1 минуту.",
                    reply_markup=waiting_kbd(player.state_end_time))

@dp.callback_query(MenuCB.filter(F.action == "hunt"))
async def menu_hunt(query: CallbackQuery, callback_data: MenuCB):
    player = await get_player(query.from_user.id)
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    b = InlineKeyboardBuilder()

    kills_on_current = player.kills_per_difficulty.get(str(player.current_difficulty), 0)
    kills_needed = KILLS_TO_UNLOCK_NEXT - kills_on_current if player.current_difficulty == player.max_unlocked_difficulty else 0
    next_unlock_info = ""
    if player.current_difficulty == player.max_unlocked_difficulty and kills_needed > 0:
        next_unlock_info = f"\n⚔️ До следующей угрозы осталось убить: {kills_needed} врагов"
    elif player.current_difficulty < player.max_unlocked_difficulty:
        next_unlock_info = f"\n✅ Угроза {player.max_unlocked_difficulty} уже открыта"

    b.button(text="◀️", callback_data=HuntCB(action="dec").pack())
    b.button(text=f"Угроза: {player.current_difficulty}", callback_data=HuntCB(action="set").pack())
    b.button(text="▶️", callback_data=HuntCB(action="inc").pack())
    b.button(text="⚔️ Начать поиск", callback_data=HuntCB(action="start").pack())
    b.button(text="🔙 Назад", callback_data=MenuCB(action="profile").pack())
    b.adjust(3, 1, 1)

    text = f"💰 Золото: {player.gold}\n⚔️ <b>Охота</b>\nМакс. доступная угроза: {player.max_unlocked_difficulty}\n"
    text += f"Убито на текущей угрозе: {kills_on_current}/{KILLS_TO_UNLOCK_NEXT}"
    text += next_unlock_info
    text += "\n\nУстановите уровень угрозы для поиска."

    await safe_edit(query.message, text, reply_markup=b.as_markup())

@dp.callback_query(HuntCB.filter())
async def process_hunt(query: CallbackQuery, callback_data: HuntCB, state: FSMContext):
    player = await get_player(query.from_user.id)
    act = callback_data.action

    if act == "dec":
        if player.current_difficulty > 1:
            player.current_difficulty -= 1
            await save_player(player)
            await menu_hunt(query, MenuCB(action="hunt"))
        else:
            await query.answer("Минимум: 1")
    elif act == "inc":
        if player.current_difficulty < player.max_unlocked_difficulty:
            player.current_difficulty += 1
            await save_player(player)
            await menu_hunt(query, MenuCB(action="hunt"))
        else:
            await query.answer("Это максимальная доступная угроза. Убивайте врагов, чтобы открыть следующую!")
    elif act == "set":
        await query.message.answer("Отправьте числом желаемый уровень угрозы (не выше максимальной):")
        await state.set_state(Form.waiting_for_difficulty)
        await query.answer()
    elif act == "start":
        enemy = generate_enemy(player.current_difficulty)
        is_win, log, result_msg = simulate_combat_realtime(player, enemy)

        t_stats = get_total_stats(player)
        result_msg += f"\n❤️ Осталось здоровья: {player.stats['hp']:.1f}/{t_stats['max_hp']:.1f}, 💧 маны: {player.stats['mp']:.1f}/{t_stats['max_mp']:.1f}"

        if is_win:
            diff_str = str(player.current_difficulty)
            kills = player.kills_per_difficulty.get(diff_str, 0)
            player.kills_per_difficulty[diff_str] = kills + 1

            base_gold = 10 * player.current_difficulty
            actual_gold = int(base_gold * enemy['power_mult'] * player.stats["drop_chance"])
            player.gold += actual_gold
            result_msg += f"\n💰 Найдено золота: {actual_gold}."

            drop_chance_scaled = 0.2 * enemy['power_mult']
            if random.random() < drop_chance_scaled:
                eff_diff = max(1, int(player.current_difficulty * player.stats["drop_chance"]))
                item = generate_item(eff_diff)
                if len(player.inventory) < player.inv_slots:
                    player.inventory.append(item)
                    result_msg += f"\n📦 Выпал предмет: {item['name']}"
                else:
                    result_msg += "\n📦 Предмет выпал, но инвентарь полон!"

            if player.current_difficulty == player.max_unlocked_difficulty and kills + 1 >= KILLS_TO_UNLOCK_NEXT:
                player.max_unlocked_difficulty += 1
                result_msg += f"\n✨ Поздравляем! Открыта угроза уровня {player.max_unlocked_difficulty}!"

        elif "погибли" in result_msg:
            player.state = 'dead'
            player.state_end_time = time.time() + CONFIG["time_death"]

        await save_player(player)

        log_text = "\n".join(log)
        if len(log_text) > 3000:
            log_text = log_text[:1500] + "\n\n..... [БОЙ ДОЛГИЙ, ПРОПУСК ТЕКСТА] .....\n\n" + log_text[-1500:]

        if player.state == 'dead':
            await safe_edit(query.message, f"{log_text}\n\n<b>{result_msg}</b>", reply_markup=main_menu_kbd())
        else:
            from aiogram.utils.keyboard import InlineKeyboardBuilder
            back_builder = InlineKeyboardBuilder()
            back_builder.button(text="🔙 К охоте", callback_data=MenuCB(action="hunt").pack())
            await safe_edit(query.message, f"{log_text}\n\n<b>{result_msg}</b>", reply_markup=back_builder.as_markup())

@dp.message(Form.waiting_for_difficulty)
async def hunt_diff_input(message: Message, state: FSMContext):
    try:
        lvl = int(message.text)
        if lvl > 0:
            player = await get_player(message.from_user.id)
            if lvl <= player.max_unlocked_difficulty:
                player.current_difficulty = lvl
                await save_player(player)
                await message.answer(f"Уровень угрозы установлен на {lvl}.", reply_markup=main_menu_kbd())
            else:
                await message.answer(f"Максимальная доступная угроза: {player.max_unlocked_difficulty}.\nУбивайте врагов, чтобы открыть новые уровни.", reply_markup=main_menu_kbd())
        else:
            await message.answer("Число должно быть больше нуля.", reply_markup=main_menu_kbd())
    except ValueError:
        await message.answer("Ошибка ввода. Ожидалось число.", reply_markup=main_menu_kbd())
    finally:
        await state.clear()

@dp.callback_query(MenuCB.filter(F.action == "inv"))
async def menu_inv(query: CallbackQuery, callback_data: MenuCB):
    player = await get_player(query.from_user.id)
    text = f"💰 Золото: {player.gold}\n\n🎒 <b>Инвентарь ({len(player.inventory)}/{player.inv_slots})</b>\n\nЭкипировано:\n"

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    b = InlineKeyboardBuilder()

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

    b.adjust(5)
    b.row(InlineKeyboardButton(text="💰 Массовая продажа", callback_data=SellMassCB(action="menu").pack()))
    b.row(InlineKeyboardButton(text="🔙 Назад", callback_data=MenuCB(action="profile").pack()))

    await safe_edit(query.message, text, reply_markup=b.as_markup())

@dp.callback_query(SellMassCB.filter(F.action == "menu"))
async def sell_mass_menu(query: CallbackQuery, callback_data: SellMassCB):
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    builder.button(text="Продать всё", callback_data=SellMassCB(action="all").pack())
    builder.button(text="Продать по цене", callback_data=SellMassCB(action="price").pack())
    builder.button(text="🔙 Назад", callback_data=MenuCB(action="inv").pack())
    builder.adjust(1)
    await safe_edit(query.message, "Выберите тип массовой продажи:", reply_markup=builder.as_markup())

@dp.callback_query(SellMassCB.filter(F.action == "all"))
async def sell_mass_all(query: CallbackQuery, callback_data: SellMassCB):
    player = await get_player(query.from_user.id)
    if not player.inventory:
        await query.answer("Инвентарь пуст!", show_alert=True)
        return
    total = 0
    sold_items = []
    for item in player.inventory[:]:  # копия для безопасного удаления
        total += item['sell_price']
        sold_items.append(item['name'])
        player.inventory.remove(item)
    player.gold += total
    await save_player(player)
    sold_list = "\n".join(sold_items) if sold_items else "ничего"
    await safe_edit(query.message,
                    f"💰 Продано:\n{sold_list}\n\nПолучено: {total} золота.\nТеперь у вас {player.gold} золота.",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="🔙 В инвентарь", callback_data=MenuCB(action="inv").pack())]
                    ]))

@dp.callback_query(SellMassCB.filter(F.action == "price"))
async def sell_mass_price(query: CallbackQuery, callback_data: SellMassCB, state: FSMContext):
    await query.message.answer("Введите максимальную цену предмета (число):")
    await state.set_state(Form.waiting_for_sell_price)
    await query.answer()

@dp.message(Form.waiting_for_sell_price)
async def sell_mass_price_input(message: Message, state: FSMContext):
    try:
        max_price = int(message.text)
        if max_price < 0:
            raise ValueError
    except ValueError:
        await message.answer("Пожалуйста, введите положительное целое число.")
        return
    player = await get_player(message.from_user.id)
    if not player.inventory:
        await message.answer("Инвентарь пуст.")
        await state.clear()
        return
    total = 0
    sold_items = []
    # проходим по копии списка
    for item in player.inventory[:]:
        if item['sell_price'] <= max_price:
            total += item['sell_price']
            sold_items.append(item['name'])
            player.inventory.remove(item)
    if not sold_items:
        await message.answer(f"Нет предметов с ценой <= {max_price}.")
    else:
        player.gold += total
        await save_player(player)
        sold_list = "\n".join(sold_items)
        await message.answer(f"💰 Продано:\n{sold_list}\n\nПолучено: {total} золота.\nТеперь у вас {player.gold} золота.")
    await state.clear()

@dp.callback_query(ItemCB.filter(F.action == "view"))
async def view_item(query: CallbackQuery, callback_data: ItemCB):
    player = await get_player(query.from_user.id)
    idx = callback_data.idx

    text, reply_markup = await get_item_view_data(player, idx)
    if text is None:
        await query.answer("Предмет не найден!")
        return

    await safe_edit(query.message, text, reply_markup)

@dp.callback_query(ItemCB.filter(F.action == "equip"))
async def eq_item(query: CallbackQuery, callback_data: ItemCB):
    player = await get_player(query.from_user.id)
    idx = callback_data.idx
    if idx >= len(player.inventory):
        return
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
    if slot_idx < 0 or slot_idx > 2:
        return
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
    if idx >= len(player.inventory):
        return
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
        if idx >= len(player.inventory):
            return
        item = player.inventory[idx]

    if not item or stat_key not in item["stats"]:
        return

    s_data = item["stats"][stat_key]
    raw_cost = (s_data['base'] * 50 + s_data['upgrades'] * s_data['base'] * 20) * s_data.get('upgrade_price_mult', 1.0)
    upg_cost = max(250, int(raw_cost))

    if player.gold >= upg_cost:
        player.gold -= upg_cost
        s_data['upgrades'] += 1
        s_data['current'] = s_data['base'] * (s_data['upgrades'] + 1)
        item['sell_price'] += int(upg_cost * 0.3)

        await save_player(player)
        await query.answer("Характеристика улучшена!")

        updated_player = await get_player(query.from_user.id)
        text, reply_markup = await get_item_view_data(updated_player, callback_data.idx)
        if text:
            await safe_edit(query.message, text, reply_markup)
        else:
            await menu_inv(query, MenuCB(action="inv"))
    else:
        await query.answer("Недостаточно золота!", show_alert=True)

@dp.callback_query(MenuCB.filter(F.action == "shop"))
async def menu_shop(query: CallbackQuery, callback_data: MenuCB):
    player = await get_player(query.from_user.id)
    await update_shop(player)

    cost_slot = 1000 + ((player.inv_slots - 10) * 2000)

    text = f"💰 Золото: {player.gold}\n🏪 <b>Магазин (обновляется каждые 10 мин)</b>\nРедкость: {player.shop_rarity} (влияет на новые товары)\n\nАссортимент:\n"

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    b = InlineKeyboardBuilder()

    b.row(
        InlineKeyboardButton(text="◀️", callback_data=ShopCB(action="dec_rarity").pack()),
        InlineKeyboardButton(text=f"Редкость: {player.shop_rarity}", callback_data=ShopCB(action="set_rarity").pack()),
        InlineKeyboardButton(text="▶️", callback_data=ShopCB(action="inc_rarity").pack())
    )

    idx = 1
    for i, entry in enumerate(player.shop_assortment):
        if entry["sold"]:
            continue
        if "item" in entry:
            it = entry["item"]
            stat_desc = ", ".join([f"{STAT_EMOJI.get(k, '')}{STAT_RU.get(k,k)}:{v['base']:.2f}" for k, v in it['stats'].items()])
            price = entry["price"]
            text += f"\n{idx}. 📦 {it['name']} ({stat_desc})\n   Стоимость: 💰 {price}\n"
            b.button(text=f"{idx}", callback_data=ShopCB(action="buy_it", idx=i).pack())
            idx += 1
        elif "ability" in entry:
            ab = entry["ability"]
            price = entry["price"]
            text += f"\n{idx}. ✨ {ab['name']} (Сила: {ab['current_value']}, база {ab['base_value']})\n   Стоимость: 💰 {price}\n"
            b.button(text=f"{idx}", callback_data=ShopCB(action="buy_ab", idx=i).pack())
            idx += 1

    b.adjust(3)
    b.row(InlineKeyboardButton(text="Обновить товары (💰 500)", callback_data=ShopCB(action="refresh").pack()))
    b.row(InlineKeyboardButton(text=f"Слот инвентаря (💰 {cost_slot})", callback_data=ShopCB(action="slot").pack()))
    b.row(InlineKeyboardButton(text="Восстановить ХП/МП (💰 25)", callback_data=ShopCB(action="heal").pack()))
    b.row(InlineKeyboardButton(text="🔙 Назад", callback_data=MenuCB(action="profile").pack()))

    await safe_edit(query.message, text, reply_markup=b.as_markup())

@dp.callback_query(ShopCB.filter())
async def process_shop(query: CallbackQuery, callback_data: ShopCB, state: FSMContext):
    player = await get_player(query.from_user.id)
    act = callback_data.action

    if act == "dec_rarity":
        if player.shop_rarity > 1:
            player.shop_rarity -= 1
            await save_player(player)
            await menu_shop(query, MenuCB(action="shop"))
        else:
            await query.answer("Минимум: 1")
    elif act == "inc_rarity":
        player.shop_rarity += 1
        await save_player(player)
        await menu_shop(query, MenuCB(action="shop"))
    elif act == "set_rarity":
        await query.message.answer("Отправьте числом желаемую редкость магазина:")
        await state.set_state(Form.waiting_for_shop_rarity)
        await query.answer()
    elif act == "refresh":
        if player.gold >= 500:
            player.gold -= 500
            await save_player(player)
            await update_shop(player, force=True)
            await query.answer("Магазин обновлен!")
            await menu_shop(query, MenuCB(action="shop"))
        else:
            await query.answer("Недостаточно золота!", show_alert=True)
    elif act == "slot":
        cost = 1000 + ((player.inv_slots - 10) * 2000)
        if player.gold >= cost:
            player.gold -= cost
            player.inv_slots += 1
            await save_player(player)
            await query.answer("Слот инвентаря куплен!")
            await menu_shop(query, MenuCB(action="shop"))
        else:
            await query.answer("Недостаточно золота!", show_alert=True)
    elif act == "heal":
        if player.gold >= 25:
            player.gold -= 25
            player.stats['hp'] = get_total_stats(player)['max_hp']
            player.stats['mp'] = get_total_stats(player)['max_mp']
            await save_player(player)
            await query.answer("Здоровье и мана восстановлены!")
            await menu_shop(query, MenuCB(action="shop"))
        else:
            await query.answer("Недостаточно золота!", show_alert=True)
    elif act in ["buy_it", "buy_ab"]:
        idx = callback_data.idx
        entry = player.shop_assortment[idx]
        if entry["sold"]:
            await query.answer("Уже продано!")
            return
        obj = entry.get("item") or entry.get("ability")
        price = entry["price"]

        if player.gold >= price:
            if act == "buy_it":
                if len(player.inventory) < player.inv_slots:
                    player.gold -= price
                    player.inventory.append(obj)
                    entry["sold"] = True
                    await save_player(player)
                    await query.answer("Предмет куплен!")
                else:
                    await query.answer("Инвентарь полон!", show_alert=True)
                    return
            else:
                player.gold -= price
                player.abilities.append(obj)
                entry["sold"] = True
                await save_player(player)
                await query.answer("Навык куплен!")
            await menu_shop(query, MenuCB(action="shop"))
        else:
            await query.answer("Недостаточно золота!", show_alert=True)

@dp.message(Form.waiting_for_shop_rarity)
async def shop_rarity_input(message: Message, state: FSMContext):
    try:
        lvl = int(message.text)
        if lvl > 0:
            player = await get_player(message.from_user.id)
            player.shop_rarity = lvl
            await save_player(player)
            await message.answer(f"Редкость магазина установлена на {lvl}.", reply_markup=main_menu_kbd())
        else:
            await message.answer("Число должно быть больше нуля.", reply_markup=main_menu_kbd())
    except ValueError:
        await message.answer("Ошибка ввода. Ожидалось число.", reply_markup=main_menu_kbd())
    finally:
        await state.clear()

@dp.callback_query(MenuCB.filter(F.action == "potions"))
async def menu_potions(query: CallbackQuery, callback_data: MenuCB):
    player = await get_player(query.from_user.id)
    await update_potion_shop(player)

    next_upgrade_cost = 12500 * (player.potion_shop_level + 1)

    text = f"💰 Золото: {player.gold}\n🧪 <b>Лавка зелий (обновляется каждые 10 мин)</b>\nУровень лавки: {player.potion_shop_level}\n"
    text += f"Следующее улучшение: 💰 {next_upgrade_cost}\n\nАссортимент:\n"

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    b = InlineKeyboardBuilder()

    idx = 1
    for i, entry in enumerate(player.potion_shop_assortment):
        if entry["sold"]:
            continue
        pot = entry["potion"]
        text += f"{idx}. {pot['name']} — 💰 {pot['price']}\n"
        b.button(text=f"{idx}", callback_data=PotionCB(action="buy", idx=i).pack())
        idx += 1

    b.adjust(3)
    b.row(InlineKeyboardButton(text="Обновить зелья (💰 500)", callback_data=PotionCB(action="refresh").pack()))
    b.row(InlineKeyboardButton(text=f"Улучшить лавку (💰 {next_upgrade_cost})", callback_data=PotionCB(action="upgrade").pack()))
    b.row(InlineKeyboardButton(text="🔙 Назад", callback_data=MenuCB(action="profile").pack()))

    await safe_edit(query.message, text, reply_markup=b.as_markup())

@dp.callback_query(PotionCB.filter())
async def process_potions(query: CallbackQuery, callback_data: PotionCB):
    player = await get_player(query.from_user.id)
    act = callback_data.action

    if act == "refresh":
        if player.gold >= 500:
            player.gold -= 500
            await update_potion_shop(player, force=True)
            await query.answer("Зелья обновлены!")
            await menu_potions(query, MenuCB(action="potions"))
        else:
            await query.answer("Недостаточно золота!", show_alert=True)
    elif act == "upgrade":
        cost = 12500 * (player.potion_shop_level + 1)
        if player.gold >= cost:
            player.gold -= cost
            player.potion_shop_level += 1
            await update_potion_shop(player, force=True)
            await query.answer(f"Лавка улучшена до уровня {player.potion_shop_level}!")
            await menu_potions(query, MenuCB(action="potions"))
        else:
            await query.answer("Недостаточно золота!", show_alert=True)
    elif act == "buy":
        idx = callback_data.idx
        if idx >= len(player.potion_shop_assortment):
            return
        entry = player.potion_shop_assortment[idx]
        if entry["sold"]:
            await query.answer("Зелье уже куплено!")
            return
        pot = entry["potion"]
        if player.gold >= pot["price"]:
            player.gold -= pot["price"]
            if pot["type"] == "flat":
                player.stats[pot["stat"]] += pot["value"]
            else:
                player.percent_bonuses[pot["stat"]] = player.percent_bonuses.get(pot["stat"], 0) + pot["value"]
            entry["sold"] = True
            await save_player(player)
            await query.answer(f"Вы выпили зелье! {STAT_RU[pot['stat']]} увеличен на {pot['value']}{'%' if pot['type']=='percent' else ''}.")
            await menu_potions(query, MenuCB(action="potions"))
        else:
            await query.answer("Недостаточно золота!", show_alert=True)

@dp.callback_query(MenuCB.filter(F.action == "exped"))
async def menu_exped(query: CallbackQuery, callback_data: MenuCB):
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    b = InlineKeyboardBuilder()
    b.button(text="Отправиться (10 мин)", callback_data=ActionCB(action="start_exped").pack())
    b.button(text="🔙 Назад", callback_data=MenuCB(action="profile").pack())
    b.adjust(1)
    await safe_edit(query.message,
                    f"💰 Золото: {(await get_player(query.from_user.id)).gold}\n🧭 <b>Экспедиция</b>\nБезопасный поиск золота и ресурсов. Вы не сможете сражаться или тренироваться 10 минут.\n"
                    "Шанс найти несколько предметов!",
                    reply_markup=b.as_markup())

@dp.callback_query(ActionCB.filter(F.action == "start_exped"))
async def start_exped(query: CallbackQuery, callback_data: ActionCB):
    player = await get_player(query.from_user.id)
    player.state = 'expedition'
    player.state_end_time = time.time() + CONFIG["time_expedition"]
    await save_player(player)
    await safe_edit(query.message,
                    "Вы отправились в экспедицию. Вернитесь через 10 минут.",
                    reply_markup=waiting_kbd(player.state_end_time))

@dp.callback_query(MenuCB.filter(F.action == "skills"))
async def menu_skills(query: CallbackQuery, callback_data: MenuCB):
    player = await get_player(query.from_user.id)

    text = f"💰 Золото: {player.gold}\n✨ <b>Ваши Навыки</b>\n\nАктивные:\n"
    for i, ab in enumerate(player.active_abilities):
        text += f"Слот {i+1}: {ab['name'] if ab else 'Пусто'} (МП: {ab['mp_cost'] if ab else 0})\n"

    text += "\nДоступные навыки:\n"
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    b = InlineKeyboardBuilder()

    for i, ab in enumerate(player.abilities):
        upg_cost = int(ab['base_value'] * 10) + (ab['upgrades'] * int(ab['base_value'] * 5))
        text += f"{i+1}. {ab['name']} | Сила: {ab['current_value']} (база {ab['base_value']}) | МП: {ab['mp_cost']}\n"
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
        if idx >= len(player.abilities):
            return
        player.active_abilities[callback_data.slot] = player.abilities[idx]
        await save_player(player)
        await query.answer(f"Навык установлен в слот {callback_data.slot + 1}.")
        await menu_skills(query, MenuCB(action="skills"))
    elif act == "upg":
        if idx >= len(player.abilities):
            return
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

async def main():
    print("Запуск бота на aiogram 3.x...")
    await load_db()
    asyncio.create_task(background_worker())
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
