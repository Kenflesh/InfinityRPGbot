import asyncio
import json
import time
import random
import os
import base64
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
enemy_cache = {}

# ===================== СТАТЫ =====================
STAT_RU = {
    "max_hp": "Макс. Здоровье", "hp": "Здоровье", "max_mp": "Макс. Мана", "mp": "Мана",
    "atk": "Физ. Атака", "def": "Физ. Защита", "m_shield": "Магический Щит",
    "crit_chance": "Шанс Крита", "crit_damage": "Крит. Урон", "accuracy": "Точность",
    "evasion_rating": "Уклонение", "atk_spd": "Скор. Атаки",
    "hp_regen": "Реген Здоровья", "mp_regen": "Реген Маны",
    "drop_chance": "Множитель Дропа",
    "lifesteal": "Вампиризм", "armor_pen": "Пробитие Брони",
    "magic_atk": "Маг. Атака", "magic_res": "Маг. Сопротивление", "thorns": "Шипы",
    "adaptability": "Адаптивность",
    "magic_crit_chance": "Маг. шанс крита",
    "magic_crit_damage": "Маг. крит урон",
    "magic_shield_drain": "Истощение энергии"
}

STAT_EMOJI = {
    "max_hp": "❤️", "hp": "❤️", "max_mp": "💧", "mp": "💧",
    "atk": "🗡️", "def": "🛡️", "m_shield": "✨",
    "crit_chance": "💥", "crit_damage": "💢", "accuracy": "🎯", "evasion_rating": "💨",
    "atk_spd": "⚡", "hp_regen": "🩹", "mp_regen": "🔮",
    "drop_chance": "🍀", "lifesteal": "🦇", "armor_pen": "🪓",
    "magic_atk": "🔮", "magic_res": "🌀", "thorns": "🌵",
    "adaptability": "🌟",
    "magic_crit_chance": "✨", "magic_crit_damage": "💫", "magic_shield_drain": "🔋"
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
    "thorns": 0.02,
    "adaptability": 0.001,
    "magic_crit_chance": 0.02,
    "magic_crit_damage": 0.5,
    "magic_shield_drain": 0.002
}

# ===================== СЛОТЫ И ПРЕДМЕТЫ =====================
EQUIP_SLOTS = [
    "right_hand", "left_hand", "boots", "belt", "robe", "helmet", "amulet", "ring1", "ring2"
]

ITEM_TYPES = [
    "weapon1h_physical", "weapon1h_magical", "weapon2h_physical", "weapon2h_magical",
    "shield", "tome", "boots", "belt", "robe", "helmet", "amulet", "ring"
]

ITEM_TYPE_TO_SLOTS = {
    "weapon1h_physical": ["right_hand", "left_hand"],
    "weapon1h_magical": ["right_hand", "left_hand"],
    "weapon2h_physical": ["right_hand", "left_hand"],
    "weapon2h_magical": ["right_hand", "left_hand"],
    "shield": ["right_hand", "left_hand"],
    "tome": ["right_hand", "left_hand"],
    "boots": ["boots"],
    "belt": ["belt"],
    "robe": ["robe"],
    "helmet": ["helmet"],
    "amulet": ["amulet"],
    "ring": ["ring1", "ring2"]
}

ITEM_HANDS_USED = {
    "weapon1h_physical": 1,
    "weapon1h_magical": 1,
    "weapon2h_physical": 2,
    "weapon2h_magical": 2,
    "shield": 1,
    "tome": 1,
    "boots": 0,
    "belt": 0,
    "robe": 0,
    "helmet": 0,
    "amulet": 0,
    "ring": 0
}

ITEM_ALLOWED_STATS = {
    "weapon1h_physical": ["atk", "atk_spd", "crit_chance", "crit_damage", "armor_pen", "accuracy", "lifesteal"],
    "weapon1h_magical": ["magic_atk", "atk_spd", "crit_chance", "crit_damage", "accuracy", "lifesteal", "magic_crit_chance", "magic_crit_damage", "magic_shield_drain"],
    "weapon2h_physical": ["atk", "atk_spd", "crit_chance", "crit_damage", "armor_pen", "accuracy", "lifesteal"],
    "weapon2h_magical": ["magic_atk", "atk_spd", "crit_chance", "crit_damage", "accuracy", "lifesteal", "magic_crit_chance", "magic_crit_damage", "magic_shield_drain"],
    "shield": ["def", "magic_res", "max_hp", "m_shield", "thorns", "evasion_rating"],
    "tome": ["magic_atk", "max_mp", "mp_regen", "crit_chance", "crit_damage", "accuracy", "magic_crit_chance", "magic_crit_damage", "magic_shield_drain"],
    "boots": ["def", "evasion_rating", "hp_regen", "max_hp"],
    "belt": ["def", "max_hp", "hp_regen", "armor_pen"],
    "robe": ["def", "magic_res", "max_hp", "hp_regen", "mp_regen", "thorns"],
    "helmet": ["def", "max_hp", "accuracy", "evasion_rating", "thorns"],
    "amulet": ["magic_atk", "max_mp", "mp_regen", "crit_chance", "crit_damage", "accuracy", "evasion_rating", "lifesteal", "m_shield", "thorns", "hp_regen", "magic_crit_chance", "magic_crit_damage", "magic_shield_drain"],
    "ring": ["atk", "magic_atk", "def", "magic_res", "max_hp", "max_mp", "hp_regen", "mp_regen",
             "crit_chance", "crit_damage", "accuracy", "evasion_rating", "lifesteal", "armor_pen", "thorns", "m_shield",
             "magic_crit_chance", "magic_crit_damage", "magic_shield_drain"]
}

MAX_STATS_PER_ITEM = {"ring": 10}
TWOHAND_MULTIPLIER = 2.0

PREFIXES = [
    "Свирепый", "Древний", "Пылающий", "Забытый", "Проклятый", "Святой", "Теневой", "Искрящийся",
    "Тяжелый", "Легкий", "Мистический", "Рунический", "Кровавый", "Ледяной", "Грозовой", "Каменный"
]

NOUNS = {
    "weapon1h_physical": ["Меч", "Топор", "Кинжал", "Булава", "Рапира", "Катана", "Молот"],
    "weapon1h_magical": ["Посох", "Жезл", "Скипетр", "Кристалл"],
    "weapon2h_physical": ["Двуручный меч", "Секира", "Копьё", "Алебарда", "Глефа"],
    "weapon2h_magical": ["Посох магии", "Гримуар", "Фолиант"],
    "shield": ["Щит", "Баклер", "Эгида", "Башенный щит"],
    "tome": ["Фолиант", "Гримуар", "Книга заклинаний", "Манускрипт"],
    "boots": ["Сапоги", "Ботинки", "Кеды", "Сандалии"],
    "belt": ["Пояс", "Ремень", "Кушак"],
    "robe": ["Мантия", "Роба", "Плащ", "Одеяние"],
    "helmet": ["Шлем", "Корона", "Капюшон", "Тиара"],
    "amulet": ["Амулет", "Кулон", "Ожерелье", "Подвеска"],
    "ring": ["Кольцо", "Перстень"]
}

SUFFIXES = [
    "Убийцы", "Короля", "Гоблина", "Дракона", "Света", "Тьмы", "Крови", "Ветров", "Пустоты", "Жизни",
    "Стойкости", "Могущества", "Проклятия", "Благословения", "Тайны"
]

# ===================== КЛАССЫ ВРАГОВ =====================
ENEMY_CLASSES = {
    "warrior": {
        "name": "Воин",
        "mult": {
            "hp": 1.2,
            "m_shield": 0.0,
            "atk": 1.0,
            "magic_atk": 0.2,
            "def": 1.2,
            "magic_res": 0.8,
            "atk_spd": 1.0,
            "accuracy": 1.0,
            "evasion_rating": 0.8,
            "crit_chance": 0.5,
            "crit_damage": 1.0,
            "lifesteal": 0.0,
            "thorns": 0.2,
            "magic_crit_chance": 0.2,
            "magic_crit_damage": 1.0,
            "magic_shield_drain": 0.0
        }
    },
    "mage": {
        "name": "Маг",
        "mult": {
            "hp": 0.8,
            "m_shield": 2.0,
            "atk": 0.2,
            "magic_atk": 1.5,
            "def": 0.5,
            "magic_res": 1.3,
            "atk_spd": 0.8,
            "accuracy": 1.2,
            "evasion_rating": 1.0,
            "crit_chance": 1.5,
            "crit_damage": 1.2,
            "lifesteal": 0.0,
            "thorns": 0.0,
            "magic_crit_chance": 3.0,
            "magic_crit_damage": 2.5,
            "magic_shield_drain": 0.5
        }
    },
    "berserker": {
        "name": "Берсерк",
        "mult": {
            "hp": 0.6,
            "m_shield": 0.0,
            "atk": 3.5,
            "magic_atk": 0.0,
            "def": 0.6,
            "magic_res": 0.5,
            "atk_spd": 1.7,
            "accuracy": 1.1,
            "evasion_rating": 0.2,
            "crit_chance": 1.0,
            "crit_damage": 1.5,
            "lifesteal": 0.1,
            "thorns": 0.0,
            "magic_crit_chance": 0.2,
            "magic_crit_damage": 0.5,
            "magic_shield_drain": 0.0
        }
    },
    "tank": {
        "name": "Танк",
        "mult": {
            "hp": 3.0,
            "m_shield": 0.0,
            "atk": 0.5,
            "magic_atk": 0.0,
            "def": 3.0,
            "magic_res": 1.5,
            "atk_spd": 0.2,
            "accuracy": 0.8,
            "evasion_rating": 0.0,
            "crit_chance": 0.2,
            "crit_damage": 1.0,
            "lifesteal": 0.0,
            "thorns": 0.0,
            "magic_crit_chance": 0.1,
            "magic_crit_damage": 1.0,
            "magic_shield_drain": 0.0
        }
    },
    "assassin": {
        "name": "Ассасин",
        "mult": {
            "hp": 0.2,
            "m_shield": 0.0,
            "atk": 1.2,
            "magic_atk": 0.0,
            "def": 0.4,
            "magic_res": 0.4,
            "atk_spd": 3.0,
            "accuracy": 2.0,
            "evasion_rating": 2.0,
            "crit_chance": 3.0,
            "crit_damage": 2.0,
            "lifesteal": 0.3,
            "thorns": 0.0,
            "magic_crit_chance": 0.0,
            "magic_crit_damage": 1.0,
            "magic_shield_drain": 0.0
        }
    },
    "vampire": {
        "name": "Вампир",
        "mult": {
            "hp": 1.1,
            "m_shield": 0.5,
            "atk": 1.1,
            "magic_atk": 0.5,
            "def": 0.9,
            "magic_res": 0.9,
            "atk_spd": 1.0,
            "accuracy": 1.0,
            "evasion_rating": 1.0,
            "crit_chance": 1.0,
            "crit_damage": 1.0,
            "lifesteal": 1.0,
            "thorns": 0.0,
            "magic_crit_chance": 0.5,
            "magic_crit_damage": 1.2,
            "magic_shield_drain": 0.2
        }
    },
    "thorn": {
        "name": "Шипастый",
        "mult": {
            "hp": 2.0,
            "m_shield": 0.0,
            "atk": 0.1,
            "magic_atk": 0.0,
            "def": 1.5,
            "magic_res": 0.5,
            "atk_spd": 0.1,
            "accuracy": 0.8,
            "evasion_rating": 0.0,
            "crit_chance": 0.0,
            "crit_damage": 0.0,
            "lifesteal": 0.0,
            "thorns": 3.0,
            "magic_crit_chance": 0.0,
            "magic_crit_damage": 0.0,
            "magic_shield_drain": 0.0
        }
    }
}

# ===================== КОНФИГ БАЛАНСА =====================
CONFIG = {
    "time_train": 10,
    "time_death": 600,
    "time_expedition": 300,
    "time_shop_update": 300,
    "time_potion_update": 300,

    "enemy_base_stats": {
        "hp": 10,
        "atk": 5,
        "def": 2,
        "m_shield": 5, 
        "magic_atk": 1,
        "magic_res": 1,
        "atk_spd": 0.1,
        "accuracy": 10,
        "evasion_rating": 10,
        "crit_chance": 2.0,
        "crit_damage": 150.0,
        "lifesteal": 0.0,
        "thorns": 1.0,
        "magic_crit_chance": 1.0,
        "magic_crit_damage": 150.0,
        "magic_shield_drain": 1.0
    },
    "enemy_stat_scale": {
        "hp": 25,
        "atk": 5,
        "def": 1,
        "m_shield": 10,
        "magic_atk": 1.5,
        "magic_res": 0.5,
        "atk_spd": 0.02,
        "accuracy": 0.5,
        "evasion_rating": 0.1,
        "crit_chance": 0.5,
        "crit_damage": 5.0,
        "lifesteal": 0.1,
        "thorns": 0.05,
        "magic_crit_chance": 0.5,
        "magic_crit_damage": 5.0,
        "magic_shield_drain": 0.1
    }
}

KILLS_TO_UNLOCK_NEXT = 5

# ===================== КОНСТАНТЫ МАГИИ =====================
SPELL_EFFECT_TYPES = [
    "damage", "heal", "dot", "hot", "buff", "debuff", "shield",
    "time_stop", "mp_restore", "mp_burn"
]
TARGET_SELF = "self"
TARGET_ENEMY = "enemy"
PASSIVE_TRIGGERS = ["on_hit", "on_attack", "low_hp", "low_mp", "on_spell_cast"]
BASE_SPELL_COOLDOWN = 5.0
MAX_EFFECTS_PER_SPELL = 5
EFFECT_CHANCE_CHAIN = [1.0, 0.1, 0.01, 0.001, 0.0001]  # для генерации нескольких эффектов

# ===================== FSM СОСТОЯНИЯ =====================
class Form(StatesGroup):
    waiting_for_difficulty = State()
    waiting_for_shop_rarity = State()
    waiting_for_sell_price = State()
    waiting_for_equip_choice = State()
    waiting_for_spell_slot = State()  # для выбора слота при экипировке заклинания

# ===================== CALLBACK DATA =====================
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

class PotionCB(CallbackData, prefix="pot"):
    action: str
    idx: int = 0

class SellMassCB(CallbackData, prefix="sellmass"):
    action: str

class CombatStatsCB(CallbackData, prefix="cbtstats"):
    action: str
    enemy_data: str

class EquipChoiceCB(CallbackData, prefix="eqchoice"):
    item_idx: int
    slot: str

# НОВЫЕ CALLBACK ДЛЯ МАГИИ
class SpellCB(CallbackData, prefix="spell"):
    action: str          # view, equip, unequip, upgrade, discard
    idx: int = 0          # индекс в spell_inventory или в active_spells (для unequip)
    slot: int = -1        # слот для экипировки (0-4) или -1

def fmt_float(num, max_precision=3):
    # Форматирует число, убирая лишние нули в конце
    s = f"{num:.{max_precision}f}".rstrip('0').rstrip('.')
    return s

# ===================== БАЗА ДАННЫХ =====================
async def load_db():
    global db
    async with db_lock:
        if os.path.exists(DB_FILE):
            with open(DB_FILE, 'r', encoding='utf-8') as f:
                db = json.load(f)
        else:
            db = {"players": {}}
            _save_db_unlocked()

async def save_db():
    async with db_lock:
        _save_db_unlocked()

def _save_db_unlocked():
    with open(DB_FILE, 'w', encoding='utf-8') as f:
        json.dump(db, f, ensure_ascii=False, indent=4)

async def clear_enemy_cache(key: str, delay: int):
    await asyncio.sleep(delay)
    enemy_cache.pop(key, None)

# ===================== КЛАСС ИГРОКА =====================
class Player:
    def __init__(self, uid, name):
        self.uid = str(uid)
        self.name = name
        self.gold = 100
        self.shop_rarity = 1
        self.shop_assortment = []
        self.shop_last_update = 0
        self.potion_shop_assortment = []
        self.potion_shop_last_update = 0

        self.stats = {
            "max_hp": 100, "hp": 100, "max_mp": 50, "mp": 50,
            "atk": 10, "def": 5, "m_shield": 0,
            "crit_chance": 5.0, "crit_damage": 150.0, "accuracy": 20.0, "evasion_rating": 5.0,
            "atk_spd": 0.15,
            "hp_regen": 5.0, "mp_regen": 5.0, "drop_chance": 1.0,
            "lifesteal": 0.0, "armor_pen": 0, "magic_atk": 0, "magic_res": 0, "thorns": 0.0,
            "adaptability": 1.0,
            "magic_crit_chance": 5.0,
            "magic_crit_damage": 150.0,
            "magic_shield_drain": 0.0
        }
        self.stat_upgrades = {k: 0 for k in self.stats.keys()}

        self.inv_slots = 20
        self.inventory = []
        self.equip = {slot: None for slot in EQUIP_SLOTS}

        # Магия
        self.spell_inventory = []
        self.active_spells = [None] * 5

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
            setattr(p, k, v)
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
                        base_increment = TRAINING_INCREMENTS.get(stat, 0.01)
                        if stat == 'adaptability':
                            increment = base_increment
                        else:
                            increment = base_increment * player.stats['adaptability']
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
                        base_gold = random.randint(100, 300) + (player.max_unlocked_difficulty * 30)
                        gold_found = int(base_gold * player.stats["drop_chance"])
                        player.gold += gold_found
                        msg = f"🧭 Экспедиция завершена!\nВы нашли: 💰 {gold_found} золота."

                        drop_chance = 0.4
                        items_found = 0
                        while random.random() < drop_chance and items_found < 3:
                            item_type = random.choice(ITEM_TYPES)
                            eff_diff = max(1, int(player.max_unlocked_difficulty * player.stats["drop_chance"]))
                            item = generate_item(item_type, eff_diff)
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

# ===================== ГЕНЕРАЦИЯ ПРЕДМЕТОВ =====================
def generate_item_name(item_type):
    prefix = random.choice(PREFIXES)
    noun = random.choice(NOUNS.get(item_type, ["Предмет"]))
    suffix = random.choice(SUFFIXES)
    return f"{prefix} {noun} {suffix}"

def generate_item(item_type, rarity):
    name = generate_item_name(item_type)

    max_stats = MAX_STATS_PER_ITEM.get(item_type, 5)
    stats_count = 1
    extra_chance = min(0.8, 0.2 * rarity)
    while random.random() < extra_chance and stats_count < max_stats:
        stats_count += 1
        extra_chance *= 0.5

    allowed = ITEM_ALLOWED_STATS.get(item_type, [])
    if not allowed:
        allowed = list(STAT_RU.keys())
    chosen_stats = random.sample(allowed, min(stats_count, len(allowed)))
    item_stats = {}

    stat_mult = {
        "atk": 0.1, "magic_atk": 0.1, "def": 0.2, "magic_res": 0.2,
        "max_hp": 0.5, "max_mp": 0.5, "hp_regen": 0.05, "mp_regen": 0.05,
        "armor_pen": 0.5, "crit_chance": 0.2, "crit_damage": 0.2,
        "accuracy": 0.5, "evasion_rating": 0.25,
        "atk_spd": 0.005, "drop_chance": 0.002, "lifesteal": 0.005, "thorns": 0.005,
        "m_shield": 0.5,
        "magic_crit_chance": 0.2, "magic_crit_damage": 0.2, "magic_shield_drain": 0.005
    }

    base_price = 0
    for stat in chosen_stats:
        is_percent = stat in ["crit_chance", "crit_damage", "atk_spd", "drop_chance", "lifesteal", "thorns", "accuracy", "evasion_rating", "magic_crit_chance", "magic_crit_damage", "magic_shield_drain"]
        mult = stat_mult.get(stat, 1.0)

        raw = (rarity * 0.25 * random.uniform(0.8, 1.2)) * mult
        if "weapon2h" in item_type:
            raw *= TWOHAND_MULTIPLIER

        integer_stats = ["atk", "def", "max_hp", "max_mp", "magic_atk", "magic_res", "armor_pen", "m_shield"]
        if stat in integer_stats:
            base_val = max(1, int(raw))
        else:
            base_val = max(0.01, round(raw, 2))
        if stat == "atk_spd":
            base_val = round(base_val / 20.0, 2)

        bonus_type = "flat"
        if stat in ["atk", "def", "max_hp", "max_mp", "magic_atk", "magic_res", "hp_regen", "mp_regen", "accuracy", "evasion_rating", "magic_crit_chance", "magic_crit_damage", "magic_shield_drain"]:
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
        "item_type": item_type,
        "stats": item_stats,
        "sell_price": max(10, int(base_price * 0.25))
    }

def generate_potion():
    potion_stats = [s for s in STAT_RU.keys() if s not in ["hp", "mp"]]
    all_potion_stats = potion_stats + ["adaptability"]
    stat = random.choice(all_potion_stats)

    potion_type = random.choice(["flat", "percent"]) if stat != "adaptability" else "flat"
    is_percent = potion_type == "percent"

    if stat == "adaptability":
        base_value = round(random.uniform(0.001, 0.005), 3)
        value = base_value
    else:
        strong_stats = ["atk_spd", "lifesteal", "thorns", "crit_chance", "crit_damage", "accuracy", "evasion_rating", "magic_crit_chance", "magic_crit_damage", "magic_shield_drain"]
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
        value = base_value

    base_price = int(base_value * random.uniform(20, 50) + 50)
    price = max(50, min(5000, base_price))

    name = f"Зелье {STAT_RU[stat]} +{value}{'%' if is_percent else ''}"
    return {
        "stat": stat,
        "value": value,
        "price": price,
        "type": potion_type,
        "name": name
    }

# ===================== ГЕНЕРАЦИЯ ЗАКЛИНАНИЙ =====================
def generate_effect(effect_type, power, target=None):
    effect = {
        "type": effect_type,
        "target": target if target else (TARGET_ENEMY if effect_type in ["damage","dot","debuff","time_stop","mp_burn"] else TARGET_SELF),
        "base_value": 0,
        "duration": 0,
        "interval": 0,
        "chance": 1.0,
        "stat": None  # для buff/debuff
    }
    if effect_type in ["damage","heal","shield","mp_restore","mp_burn"]:
        if effect_type == "heal":
            base = power * random.uniform(2, 6)  # уменьшено
        else:
            base = power * random.uniform(5, 15)
        effect["base_value"] = int(base) if effect_type in ["shield","mp_restore","mp_burn"] else round(base,1)
    elif effect_type in ["dot","hot"]:
        base = power * random.uniform(2, 8)
        effect["base_value"] = round(base,1)
        effect["duration"] = random.randint(5,15)
        effect["interval"] = random.choice([1,2,3])
    elif effect_type in ["buff","debuff"]:
        stat = random.choice(["atk","def","magic_atk","magic_res","atk_spd","crit_chance","crit_damage","magic_crit_chance","magic_crit_damage"])
        base = power * random.uniform(0.1, 0.5)
        effect["stat"] = stat
        effect["base_value"] = round(base,2)
        effect["duration"] = random.randint(5,15)
    elif effect_type == "time_stop":
        effect["duration"] = random.randint(2,6)
    return effect

def generate_spell(enemy_class_key, power, force_min_effects=1):
    prefixes = ["Огненный","Ледяной","Теневой","Святой","Древний","Проклятый","Молниеносный","Кровавый"]
    nouns = ["Шар","Взрыв","Копьё","Сфера","Поток","Клинок","Щит","Благословение","Проклятие"]
    suffix = random.choice([""," Мага"," Тьмы"," Света"," Разрушения"," Защиты"])
    name = f"{random.choice(prefixes)} {random.choice(nouns)}{suffix}"

    possible_effects = ["damage","heal","dot","hot","buff","debuff","shield","time_stop","mp_restore","mp_burn"]
    effects = []
    chance_index = 0
    while chance_index < MAX_EFFECTS_PER_SPELL and (len(effects) < force_min_effects or random.random() < EFFECT_CHANCE_CHAIN[chance_index]):
        effect_type = random.choice(possible_effects)
        target = TARGET_ENEMY if effect_type in ["damage","dot","debuff","time_stop","mp_burn"] else TARGET_SELF
        eff = generate_effect(effect_type, power, target)
        effects.append(eff)
        chance_index += 1
        if chance_index == 1 and force_min_effects==1:
            # после первого эффекта дальше по вероятности
            continue

    base_cooldown = BASE_SPELL_COOLDOWN * random.uniform(0.8, 1.5)
    is_passive = random.random() < 0.2
    trigger = random.choice(PASSIVE_TRIGGERS) if is_passive else None

    spell = {
        "id": "s_" + str(time.time()).replace(".", "") + str(random.randint(10,99)),
        "name": name,
        "effects": effects,
        "mp_cost": int(power * random.uniform(5,20)),
        "base_cooldown": base_cooldown,
        "current_cooldown": 0,
        "cooldown_reduction_per_upgrade": 0.1,
        "is_passive": is_passive,
        "trigger": trigger,
        "upgrades": 0,
        "sell_price": int(power * random.uniform(20,50))
    }
    return spell

# ===================== ГЕНЕРАЦИЯ ВРАГА =====================
def generate_enemy(difficulty):
    variance = lambda: random.uniform(0.8, 1.2)
    class_key = random.choice(list(ENEMY_CLASSES.keys()))
    enemy_class = ENEMY_CLASSES[class_key]
    class_mult = enemy_class["mult"]

    e_stats = {}
    for stat in ["hp","atk","def","magic_atk","magic_res","accuracy","evasion_rating",
                 "crit_chance","crit_damage","lifesteal","thorns",
                 "magic_crit_chance","magic_crit_damage","magic_shield_drain", "m_shield"]:
        base = CONFIG["enemy_base_stats"].get(stat,0)
        scale = CONFIG["enemy_stat_scale"].get(stat,0)
        val = (base + difficulty * scale) * variance() * class_mult.get(stat,1.0)
        if stat in ["hp","atk","def","magic_atk","magic_res","magic_crit_chance","magic_crit_damage"]:
            e_stats[stat] = max(0, int(val)) if stat not in ["magic_crit_chance","magic_crit_damage"] else max(0, val)
        else:
            e_stats[stat] = max(0, val)

    e_stats["atk_spd"] = max(0.05, (CONFIG["enemy_base_stats"]["atk_spd"] + difficulty * CONFIG["enemy_stat_scale"]["atk_spd"]) * variance() * class_mult.get("atk_spd",1.0))
    e_stats["max_mp"] = max(20, int(difficulty * 15))  # базовая мана
    e_stats["mp"] = e_stats["max_mp"]

    # Генерация заклинаний
    spells = []
    if class_key == "mage":
        spell_count = 1
        if random.random() < 0.25:
            spell_count = 2
            if random.random() < 0.25:
                spell_count = 3
    else:
        if random.random() < 0.25:
            spell_count = 1
            if random.random() < 0.25:
                spell_count = 2
                if random.random() < 0.25:
                    spell_count = 3
        else:
            spell_count = 0

    for _ in range(spell_count):
        spell = generate_spell(class_key, difficulty, force_min_effects=1)
        spells.append(spell)

    norm_hp = CONFIG["enemy_base_stats"]["hp"] + (difficulty * CONFIG["enemy_stat_scale"]["hp"])
    power_multiplier = e_stats["hp"] / (norm_hp if norm_hp>0 else 1)

    names = {
        "warrior": ["Воин","Рыцарь","Латинец", "Паладин"],
        "mage": ["Маг","Чародей","Волшебник", "Заклинатель"],
        "berserker": ["Берсерк","Дикарь","Варвар"],
        "tank": ["Страж","Защитник","Гладиатор"],
        "assassin": ["Ассасин","Убийца","Ниндзя", "Разбойник"],
        "vampire": ["Вампир","Кровопийца","Носферату", "Комар"],
        "thorn": ["Шипастый","Колючий","Остряк"]
    }
    name_choices = names.get(class_key, ["Монстр"])
    name = f"{random.choice(name_choices)} {random.choice(['Слабый','Обычный','Свирепый','Древний','Элитный','Кошмарный'])}"

    return {
        "name": name,
        "class": enemy_class["name"],
        "class_key": class_key,
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
        "crit_chance": e_stats["crit_chance"],
        "crit_damage": e_stats["crit_damage"],
        "lifesteal": e_stats["lifesteal"],
        "thorns": e_stats["thorns"],
        "magic_crit_chance": e_stats.get("magic_crit_chance",0),
        "magic_crit_damage": e_stats.get("magic_crit_damage",150),
        "magic_shield_drain": e_stats.get("magic_shield_drain",0),
        "spells": spells,
        "power_mult": power_multiplier
    }

def get_evasion_chance(acc, eva):
    if acc+eva==0:
        return 0
    return eva/(acc+eva)*100

# ===================== ОБНОВЛЕНИЕ МАГАЗИНОВ =====================
async def update_shop(player, force=False):
    now = time.time()
    if force or now - player.shop_last_update > CONFIG["time_shop_update"]:
        player.shop_assortment = []
        for _ in range(5):
            item_type = random.choice(ITEM_TYPES)
            item = generate_item(item_type, player.shop_rarity)
            price = int(item['sell_price'] * 3 * (1 + player.shop_rarity / 5))
            player.shop_assortment.append({"item": item, "price": price, "sold": False})
        player.shop_last_update = now
        await save_player(player)

async def update_potion_shop(player, force=False):
    now = time.time()
    if force or now - player.potion_shop_last_update > CONFIG["time_potion_update"]:
        player.potion_shop_assortment = []
        for _ in range(5):
            player.potion_shop_assortment.append({"potion": generate_potion(), "sold": False})
        player.potion_shop_last_update = now
        await save_player(player)

# ===================== РАСЧЁТ СУММАРНЫХ СТАТОВ =====================
def get_total_stats(player):
    total = player.stats.copy()
    flat_items = {k:0 for k in total.keys()}
    percent_items = {k:0 for k in total.keys()}
    for slot, item in player.equip.items():
        if item:
            for stat_name, stat_data in item["stats"].items():
                if stat_name in total:
                    current_val = stat_data['base'] * (stat_data['upgrades']+1)
                    if stat_data.get('bonus_type') == 'percent':
                        percent_items[stat_name] += current_val
                    else:
                        flat_items[stat_name] += current_val
    percent_potions = player.percent_bonuses.copy()
    for stat in total.keys():
        base = total[stat]
        flat = flat_items.get(stat,0)
        percent_sum = percent_items.get(stat,0) + percent_potions.get(stat,0)
        total[stat] = (base + flat) * (1 + percent_sum/100.0)
    total['hp'] = min(total['hp'], total['max_hp'])
    total['mp'] = min(total['mp'], total['max_mp'])
    return total

# ===================== НОВАЯ СИМУЛЯЦИЯ БОЯ =====================
def simulate_combat_realtime(player, enemy):
    p_stats = get_total_stats(player)
    e_stats = enemy.copy()

    current_shield = p_stats['m_shield']
    enemy_shield = e_stats.get('m_shield', 0)

    p_effects = []  # эффекты на игроке
    e_effects = []  # эффекты на враге

    # Перезарядки заклинаний игрока (5 слотов)
    spell_cooldowns = [0.0] * 5
    enemy_spells = e_stats.get('spells', [])
    enemy_cooldowns = [0.0] * len(enemy_spells)

    # Определяем наличие оружия в руках
    has_phys_weapon = False
    has_magic_weapon = False
    for slot in ['right_hand', 'left_hand']:
        item = player.equip.get(slot)
        if item:
            typ = item['item_type']
            if typ in ['weapon1h_physical', 'weapon2h_physical']:
                has_phys_weapon = True
            elif typ in ['weapon1h_magical', 'weapon2h_magical']:
                has_magic_weapon = True
    # Хотя бы одна рука свободна (не занята никаким предметом)
    has_free_hand = player.equip.get('right_hand') is None or player.equip.get('left_hand') is None

    log = [
        f"⚔️ <b>Бой начался!</b>\nУгроза: {enemy['difficulty']}",
        f"👤 <b>Вы:</b> ❤️ {p_stats['hp']:.1f}/{p_stats['max_hp']:.1f} | ✨ {p_stats['m_shield']} | 💧 {p_stats['mp']:.1f}/{p_stats['max_mp']:.1f}",
        f"😡 <b>{enemy['name']} [{enemy.get('class','')}]</b>: ❤️ {enemy['hp']:.1f}/{enemy['max_hp']:.1f}",
        f"🎯 Шанс вашего уклонения: {get_evasion_chance(e_stats['accuracy'], p_stats['evasion_rating']):.1f}%\nШанс уклонения врага: {get_evasion_chance(p_stats['accuracy'], e_stats['evasion_rating']):.1f}%",
    ]

    tick = 0.1
    time_elapsed = 0.0
    max_time = 300.0

    p_cooldown = 1.0 / max(0.05, p_stats["atk_spd"])
    e_cooldown = 1.0 / max(0.05, e_stats["atk_spd"])

    # Вспомогательные функции
    def apply_effect(effect, caster_stats, target_stats, is_player_caster, target_effects_list):
        # Применяет эффект к цели (добавляет в список эффектов или мгновенно)
        nonlocal current_shield, enemy_shield, time_elapsed
        msg = ""
        eff_type = effect["type"]
        base = effect["base_value"]
        duration = effect.get("duration",0)
        interval = effect.get("interval",0)
        stat = effect.get("stat")
        target = effect.get("target", TARGET_ENEMY)

        if eff_type in ["damage","mp_burn"]:
            # мгновенный урон (магический)
            dmg = base
            # магический крит
            if random.random()*100 < caster_stats.get("magic_crit_chance",0):
                dmg *= caster_stats.get("magic_crit_damage",200)/100.0
            # сопротивление
            res = target_stats.get("magic_res",0)
            dmg = max(1, dmg - res)
            if eff_type=="damage":
                remaining_dmg = dmg
                if target_stats is e_stats:
                    # цель — враг
                    if enemy_shield > 0:
                        absorbed = min(remaining_dmg, enemy_shield)
                        enemy_shield -= absorbed
                        remaining_dmg -= absorbed
                    if remaining_dmg > 0:
                        target_stats["hp"] -= remaining_dmg
                else:
                    # цель — игрок
                    if current_shield > 0:
                        absorbed = min(remaining_dmg, current_shield)
                        current_shield -= absorbed
                        remaining_dmg -= absorbed
                    if remaining_dmg > 0:
                        target_stats["hp"] -= remaining_dmg

                drain = caster_stats.get("magic_shield_drain",0)
                if drain>0:
                    shield_gain = dmg * (drain/100.0)
                    if is_player_caster:
                        current_shield = min(current_shield + shield_gain, p_stats["max_hp"]*0.5)
                    else:
                        enemy_shield = min(enemy_shield + shield_gain, e_stats["max_hp"]*0.5)
                    msg += f"🔋 +{shield_gain:.1f} щита "
                if target_stats is e_stats:
                    msg += f"🔥 Вы нанесли {dmg:.1f} урона"
                else:
                    msg += f"🔥 Вам нанесли {dmg:.1f} урона"
            else: # mp_burn
                if "max_mp" in target_stats:
                    target_stats["mp"] = max(0, target_stats["mp"] - dmg)
                    if target_stats is e_stats:
                        msg += f"💧 Вы сожгли {dmg} маны"
                    else:
                        msg += f"💧 Вы потеряли {dmg} маны"

        elif eff_type in ["heal","mp_restore"]:
            if eff_type=="heal":
                target_stats["hp"] = min(target_stats["max_hp"], target_stats["hp"] + base)
                msg += f"💚 +{base} HP"
            else:  # mp_restore
                if "max_mp" in target_stats:
                    target_stats["mp"] = min(target_stats["max_mp"], target_stats["mp"] + base)
                    msg += f"💧 +{base} MP"

        elif eff_type in ["dot","hot","buff","debuff","time_stop"]:
            # Добавляем эффект в список с продолжительностью
            effect_copy = effect.copy()
            effect_copy["last_tick"] = time_elapsed  # для отслеживания интервалов
            target_effects_list.append(effect_copy)
            if eff_type=="time_stop":
                msg += f"⏸ Остановка времени на {duration}с"
            else:
                msg += f"✨ Эффект {STAT_RU.get(stat,eff_type)}"

        elif eff_type=="shield":
            if is_player_caster:
                current_shield = min(current_shield + base, p_stats["max_hp"]*0.5)
                msg += f"✨ Вы получили +{base} щита"
            else:
                enemy_shield = min(enemy_shield + base, e_stats["max_hp"]*0.5)
                msg += f"✨ Враг получил +{base} щита"

        return msg

    def tick_effects(effects_list, target_stats, is_player_target):
        nonlocal current_shield, enemy_shield, time_elapsed
        for eff in effects_list[:]:
            eff_type = eff["type"]
            duration = eff.get("duration",0)
            interval = eff.get("interval",0)
            last = eff.get("last_tick", time_elapsed)
            if time_elapsed - last >= interval and interval>0:
                # срабатывание по интервалу
                if eff_type=="dot":
                    dmg = eff["base_value"]
                    remaining_dmg = dmg
                    if is_player_target:
                        # игрок
                        if current_shield > 0:
                            absorbed = min(remaining_dmg, current_shield)
                            current_shield -= absorbed
                            remaining_dmg -= absorbed
                        if remaining_dmg > 0:
                            target_stats["hp"] -= remaining_dmg
                        log.append(f"[{time_elapsed:.1f}с] 🌡 Вы получили {dmg:.1f} урона от горения")
                    else:
                        # враг
                        if enemy_shield > 0:
                            absorbed = min(remaining_dmg, enemy_shield)
                            enemy_shield -= absorbed
                            remaining_dmg -= absorbed
                        if remaining_dmg > 0:
                            target_stats["hp"] -= remaining_dmg
                        log.append(f"[{time_elapsed:.1f}с] 🌡 Враг получил {dmg:.1f} урона от горения")
                elif eff_type=="hot":
                    heal = eff["base_value"]
                    target_stats["hp"] = min(target_stats["max_hp"], target_stats["hp"] + heal)
                    if is_player_target:
                        log.append(f"[{time_elapsed:.1f}с] 💚 Вы восстановили {heal:.1f} HP")
                    else:
                        log.append(f"[{time_elapsed:.1f}с] 💚 Враг восстановил {heal:.1f} HP")
                eff["last_tick"] = time_elapsed

            # Уменьшение длительности
            if duration>0:
                eff["duration"] -= tick
                if eff["duration"] <= 0:
                    effects_list.remove(eff)
                    if eff["type"]=="time_stop":
                        log.append(f"[{time_elapsed:.1f}с] ⏸ Время возобновилось")

    while p_stats["hp"]>0 and e_stats["hp"]>0 and time_elapsed<max_time:
        # Реген раз в секунду
        if abs((time_elapsed % 1.0)-0.0)<0.05:
            p_stats["hp"] = min(p_stats["max_hp"], p_stats["hp"] + p_stats["hp_regen"]/60.0)
            p_stats["mp"] = min(p_stats["max_mp"], p_stats["mp"] + p_stats["mp_regen"]/60.0)

        tick_effects(p_effects, p_stats, is_player_target=True)
        tick_effects(e_effects, e_stats, is_player_target=False)

        # Уменьшение перезарядок
        for i in range(5):
            if spell_cooldowns[i]>0:
                spell_cooldowns[i] -= tick
        for i in range(len(enemy_cooldowns)):
            if enemy_cooldowns[i]>0:
                enemy_cooldowns[i] -= tick

        # Проверка контроля
        enemy_stopped = any(eff['type']=='time_stop' and eff['duration']>0 for eff in e_effects)
        player_stopped = any(eff['type']=='time_stop' and eff['duration']>0 for eff in p_effects)

        # Ход игрока
        if not player_stopped:
            p_cooldown -= tick
            if p_cooldown <= 0 and p_stats["hp"]>0:
                p_cooldown += 1.0 / max(0.05, p_stats["atk_spd"])
                spell_used = False
                # Проверка пассивных заклинаний (упрощённо: не реализуем все триггеры)
                # Активные заклинания
                for i, spell in enumerate(player.active_spells):
                    if spell and not spell.get('is_passive', False):
                        if spell_cooldowns[i]<=0 and p_stats["mp"]>=spell["mp_cost"]:
                            p_stats["mp"] -= spell["mp_cost"]
                            cd = spell["base_cooldown"] / (1 + spell["upgrades"] * spell.get("cooldown_reduction_per_upgrade",0.1))
                            spell_cooldowns[i] = cd
                            # Применяем все эффекты заклинания
                            msg = f"[{time_elapsed:.1f}с] ✨ {spell['name']}: "
                            for eff in spell["effects"]:
                                if eff["target"] == TARGET_ENEMY:
                                    msg += apply_effect(eff, p_stats, e_stats, True, e_effects)
                                else:
                                    msg += apply_effect(eff, p_stats, p_stats, True, p_effects)
                            log.append(msg)
                            spell_used = True
                            break
                if not spell_used:
                    # Определяем, может ли игрок совершить обычную атаку
                    can_phys = has_phys_weapon or (not has_phys_weapon and has_free_hand)
                    can_magic = has_magic_weapon

                    if can_phys or can_magic:
                        phys_dmg = 0
                        magic_dmg = 0

                        if can_phys:
                            phys_dmg = max(0, p_stats["atk"] - e_stats["def"])
                        if can_magic:
                            magic_dmg = max(0, p_stats["magic_atk"] - e_stats["magic_res"])

                        hit = random.random()*100 > get_evasion_chance(p_stats["accuracy"], e_stats["evasion_rating"])
                        if hit:
                            if can_phys:
                                # Физ крит
                                if random.random()*100 < p_stats["crit_chance"]:
                                    phys_dmg *= p_stats["crit_damage"]/100.0
                        else:
                            phys_dmg = 0  # промах по физической части

                        # Маг крит (не зависит от уклонения)
                        if can_magic:
                            if random.random()*100 < p_stats["magic_crit_chance"]:
                                magic_dmg *= p_stats["magic_crit_damage"]/100.0

                        total_dmg = int(phys_dmg + magic_dmg)

                        if total_dmg > 0:
                            remaining_dmg = total_dmg
                            if enemy_shield > 0:
                                absorbed = min(remaining_dmg, enemy_shield)
                                enemy_shield -= absorbed
                                remaining_dmg -= absorbed
                            if remaining_dmg > 0:
                                e_stats["hp"] -= remaining_dmg

                            msg = f"[{time_elapsed:.1f}с] 🗡 Вы атаковали и нанесли {total_dmg} урона"
                            if phys_dmg>0:
                                # Вампиризм только от физ
                                if p_stats["lifesteal"]>0:
                                    ls = phys_dmg * (p_stats["lifesteal"]/100.0)
                                    p_stats["hp"] = min(p_stats["max_hp"], p_stats["hp"]+ls)
                                    msg += f" 🩸 +{ls:.1f} HP"
                                # Шипы врага от физ
                                if e_stats["thorns"]>0:
                                    th = phys_dmg * (e_stats["thorns"]/100.0)
                                    if current_shield>0:
                                        absorbed = min(th, current_shield)
                                        current_shield -= absorbed
                                        th -= absorbed
                                    if th>0:
                                        # Округляем до 1, если th меньше 1
                                        if th < 1:
                                            th = 1
                                        p_stats["hp"] -= th
                                        msg += f" 🌵 -{th:.1f} HP"
                            if magic_dmg>0:
                                # Истощение энергии от маг
                                if p_stats["magic_shield_drain"]>0:
                                    drain = magic_dmg * (p_stats["magic_shield_drain"]/100.0)
                                    current_shield = min(current_shield + drain, p_stats["max_hp"]*0.5)
                                    msg += f" 🔋 +{drain:.1f} щита"
                            log.append(msg)

        # Ход врага
        if e_stats["hp"]>0 and not enemy_stopped:
            e_cooldown -= tick
            if e_cooldown <= 0:
                e_cooldown += 1.0 / max(0.05, e_stats["atk_spd"])
                spell_used = False
                if enemy_spells:
                    # Ищем заклинание, на которое хватит маны
                    available = [i for i,cd in enumerate(enemy_cooldowns) if cd<=0]
                    # Перемешаем, чтобы не было предвзятости
                    random.shuffle(available)
                    for idx in available:
                        spell = enemy_spells[idx]
                        if "mp" in e_stats and spell["mp_cost"] <= e_stats["mp"]:
                            e_stats["mp"] -= spell["mp_cost"]
                            cd = spell["base_cooldown"] / (1 + spell["upgrades"]*0.1)
                            enemy_cooldowns[idx] = cd
                            msg = f"[{time_elapsed:.1f}с] Враг использует заклинание:✨ {spell['name']}: "
                            for eff in spell["effects"]:
                                if eff["target"] == TARGET_ENEMY:
                                    msg += apply_effect(eff, e_stats, p_stats, False, p_effects)
                                else:
                                    msg += apply_effect(eff, e_stats, e_stats, False, e_effects)
                            log.append(msg)
                            spell_used = True
                            break
                if not spell_used:
                    # Обычная атака врага (упрощённо)
                    dmg = max(1, e_stats["atk"] - p_stats["def"])
                    if random.random()*100 > get_evasion_chance(e_stats["accuracy"], p_stats["evasion_rating"]):
                        if random.random()*100 < e_stats["crit_chance"]:
                            dmg = int(dmg * (e_stats["crit_damage"]/100.0))
                        if current_shield>0:
                            absorbed = min(dmg, current_shield)
                            current_shield -= absorbed
                            dmg -= absorbed
                        if dmg>0:
                            p_stats["hp"] -= dmg
                            log.append(f"[{time_elapsed:.1f}с] 😡 Враг нанёс вам {dmg} урона")
                    else:
                        log.append(f"[{time_elapsed:.1f}с] 🌀 Вы уклонились")

        time_elapsed += tick

    player.stats["hp"] = max(0, p_stats["hp"])
    player.stats["mp"] = max(0, p_stats["mp"])

    if time_elapsed>=max_time:
        return False, log, "⏳ Вы поняли, что это будет длиться вечно, поэтому решили разойтись..."
    elif player.stats["hp"]<=0:
        return False, log, "💀 Вы погибли!"
    else:
        return True, log, "🏆 Вы победили!"

# ===================== КЛАВИАТУРЫ =====================
def main_menu_kbd():
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    builder.button(text="🗡 Охота", callback_data=MenuCB(action="hunt").pack())
    builder.button(text="🏋️ Тренировка", callback_data=MenuCB(action="train").pack())
    builder.button(text="🎒 Инвентарь", callback_data=MenuCB(action="inv").pack())
    builder.button(text="🔮 Магия", callback_data=MenuCB(action="spells").pack())  # заменили "Навыки"
    builder.button(text="🏪 Магазин", callback_data=MenuCB(action="shop").pack())
    builder.button(text="🧪 Зелья", callback_data=MenuCB(action="potions").pack())
    builder.button(text="🧭 Экспедиция", callback_data=MenuCB(action="exped").pack())
    builder.button(text="👤 Герой", callback_data=MenuCB(action="profile").pack())
    builder.adjust(2,2,2,2)
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

# ===================== ПРОСМОТР ПРЕДМЕТА (без изменений, но добавим новые статы в описание) =====================
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

    type_ru = {
        "weapon1h_physical": "Одноручное физ. оружие",
        "weapon1h_magical": "Одноручное маг. оружие",
        "weapon2h_physical": "Двуручное физ. оружие",
        "weapon2h_magical": "Двуручное маг. оружие",
        "shield": "Щит",
        "tome": "Фолиант",
        "boots": "Обувь",
        "belt": "Пояс",
        "robe": "Одежда",
        "helmet": "Головной убор",
        "amulet": "Амулет",
        "ring": "Кольцо"
    }.get(item['item_type'], item['item_type'])

    text = f"💰 Золото: {player.gold}\n📦 <b>{item['name']}</b> ({'Надето' if is_equip else 'В сумке'})\nТип: {type_ru}\n\nХарактеристики:\n"

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    b = InlineKeyboardBuilder()

    for stat_key, stat_data in item["stats"].items():
        is_percent = stat_key in ["crit_chance","crit_damage","atk_spd","drop_chance","lifesteal","thorns","accuracy","evasion_rating","magic_crit_chance","magic_crit_damage","magic_shield_drain"]
        raw_cost = (stat_data['base']*50 + stat_data['upgrades']*stat_data['base']*20) * stat_data.get('upgrade_price_mult',1.0)
        upg_cost = max(250, int(raw_cost))
        s_ru = f"{STAT_EMOJI.get(stat_key,'')} {STAT_RU.get(stat_key,stat_key)}"
        bonus_type = stat_data.get('bonus_type','flat')
        bonus_symbol = '%' if bonus_type=='percent' else ''
        text += f"• {s_ru}: {stat_data['current']:.2f}{bonus_symbol} (база {stat_data['base']:.2f}{bonus_symbol}, улучшений: {stat_data['upgrades']}) - Улучшить: 💰 {upg_cost} (+{stat_data['base']:.2f}{bonus_symbol})\n"
        c_idx = 900 + list(player.equip.keys()).index(slot_name) if is_equip else real_idx
        b.button(text=f"Улучшить {s_ru}", callback_data=ItemCB(action="upg", idx=c_idx, stat=stat_key).pack())

    b.adjust(1)

    if is_equip:
        b.row(InlineKeyboardButton(text="Снять", callback_data=ItemCB(action="unequip", idx=c_idx).pack()))
    else:
        allowed_slots = ITEM_TYPE_TO_SLOTS.get(item['item_type'], [])
        if len(allowed_slots)==1:
            b.row(InlineKeyboardButton(text="Надеть", callback_data=ItemCB(action="equip", idx=real_idx).pack()))
        elif len(allowed_slots)>1:
            b.row(InlineKeyboardButton(text="🔧 Выбрать слот", callback_data=ItemCB(action="choose_slot", idx=real_idx).pack()))
        b.row(InlineKeyboardButton(text=f"Продать (💰 {item['sell_price']})", callback_data=ItemCB(action="sell", idx=real_idx).pack()))

    b.row(InlineKeyboardButton(text="🔙 Назад", callback_data=MenuCB(action="inv").pack()))

    return text, b.as_markup()

# ===================== ОБРАБОТЧИКИ КОМАНД =====================
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
    if len(args)!=2:
        await message.answer("Использование: /givegold <сумма>")
        return
    try:
        amount = int(args[1])
        if amount<=0: raise ValueError
    except:
        await message.answer("Сумма должна быть положительным числом.")
        return
    player = await get_player(message.from_user.id)
    player.gold += amount
    await save_player(player)
    await message.answer(f"💰 Вам начислено {amount} золота. Теперь у вас {player.gold} золота.")

@dp.callback_query(ActionCB.filter(F.action=="cancel"))
async def cb_cancel(query: CallbackQuery, callback_data: ActionCB):
    player = await get_player(query.from_user.id)
    if player.state in ['training','expedition']:
        player.state = 'idle'
        player.state_end_time = 0
        player.training_stat = None
        await save_player(player)
        await safe_edit(query.message, "Действие отменено.", reply_markup=main_menu_kbd())
    else:
        await query.answer("Отменять нечего.", show_alert=True)

@dp.callback_query(ActionCB.filter(F.action=="check_time"))
async def cb_check_time(query: CallbackQuery, callback_data: ActionCB):
    player = await get_player(query.from_user.id)
    if player.state != 'idle':
        remaining = player.state_end_time - time.time()
        minutes = int(remaining//60)
        seconds = int(remaining%60)
        state_rus = {"training":"тренируетесь","expedition":"в экспедиции","dead":"мертвы"}.get(player.state,player.state)
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
        minutes = int(remaining//60)
        seconds = int(remaining%60)
        if player.state == 'dead':
            await query.answer(f"Вы мертвы. Воскрешение через: {minutes} мин {seconds} сек.", show_alert=True)
        else:
            state_rus = {"training":"Тренируетесь","expedition":"В экспедиции"}.get(player.state,player.state)
            await query.answer(f"Вы заняты ({state_rus}). Осталось: {minutes} мин {seconds} сек.", show_alert=True)
        return

    raise SkipHandler()

@dp.callback_query(MenuCB.filter(F.action=="profile"))
async def menu_profile(query: CallbackQuery, callback_data: MenuCB):
    player = await get_player(query.from_user.id)
    t_stats = get_total_stats(player)

    text = f"👤 <b>Профиль: {player.name}</b>\n💰 Золото: {player.gold}\n🏪 Редкость магазина: {player.shop_rarity}\n🌟 Адаптивность: {t_stats['adaptability']:.3f}\n"
    text += f"🔓 Доступная угроза: {player.max_unlocked_difficulty}\n\n"
    text += f"{STAT_EMOJI['hp']} {STAT_RU['hp']}: {player.stats['hp']:.1f}/{t_stats['max_hp']:.1f} (+{t_stats['hp_regen']:.2f}/мин)\n"
    text += f"{STAT_EMOJI['m_shield']} {STAT_RU['m_shield']}: {t_stats['m_shield']:.1f} (восстанавливается каждый бой)\n"
    text += f"{STAT_EMOJI['mp']} {STAT_RU['mp']}: {player.stats['mp']:.1f}/{t_stats['max_mp']:.1f} (+{t_stats['mp_regen']:.2f}/мин)\n"
    text += f"{STAT_EMOJI['atk']} {STAT_RU['atk']}: {t_stats['atk']:.2f} | {STAT_EMOJI['magic_atk']} {STAT_RU['magic_atk']}: {t_stats['magic_atk']:.2f}\n"
    text += f"{STAT_EMOJI['def']} {STAT_RU['def']}: {t_stats['def']:.2f} | {STAT_EMOJI['magic_res']} {STAT_RU['magic_res']}: {t_stats['magic_res']:.2f}\n"
    text += f"{STAT_EMOJI['crit_chance']} {STAT_RU['crit_chance']}: {t_stats['crit_chance']:.2f}% | {STAT_EMOJI['crit_damage']} {STAT_RU['crit_damage']}: {t_stats['crit_damage']:.2f}%\n"
    text += f"{STAT_EMOJI['magic_crit_chance']} {STAT_RU['magic_crit_chance']}: {t_stats['magic_crit_chance']:.2f}% | {STAT_EMOJI['magic_crit_damage']} {STAT_RU['magic_crit_damage']}: {t_stats['magic_crit_damage']:.2f}%\n"
    text += f"{STAT_EMOJI['accuracy']} {STAT_RU['accuracy']}: {t_stats['accuracy']:.2f} | {STAT_EMOJI['evasion_rating']} {STAT_RU['evasion_rating']}: {t_stats['evasion_rating']:.2f}\n"
    text += f"{STAT_EMOJI['lifesteal']} {STAT_RU['lifesteal']}: {t_stats['lifesteal']:.2f}% | {STAT_EMOJI['thorns']} {STAT_RU['thorns']}: {t_stats['thorns']:.2f}%\n"
    text += f"{STAT_EMOJI['magic_shield_drain']} {STAT_RU['magic_shield_drain']}: {t_stats['magic_shield_drain']:.2f}%\n"
    text += f"{STAT_EMOJI['armor_pen']} {STAT_RU['armor_pen']}: {t_stats['armor_pen']} | {STAT_EMOJI['atk_spd']} {STAT_RU['atk_spd']}: {t_stats['atk_spd']:.2f} | {STAT_EMOJI['drop_chance']} {STAT_RU['drop_chance']}: x{t_stats['drop_chance']:.2f}\n"

    await safe_edit(query.message, text, reply_markup=main_menu_kbd())

@dp.callback_query(MenuCB.filter(F.action=="train"))
async def menu_train(query: CallbackQuery, callback_data: MenuCB):
    player = await get_player(query.from_user.id)
    page = callback_data.page
    stats = [s for s in player.stat_upgrades.keys() if s not in ["hp","mp"]]

    per_page = 6
    start = page * per_page
    end = start + per_page

    text = f"💰 Золото: {player.gold}\n🏋️ <b>Тренировка (10 секунд)</b>\nВыберите характеристику:\n\n"

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()

    for i, stat in enumerate(stats[start:end], start=1):
        upgrades = player.stat_upgrades[stat]
        stat_name = f"{STAT_EMOJI.get(stat,'')} {STAT_RU.get(stat,stat)}"
        base_inc = TRAINING_INCREMENTS.get(stat,0.01)
        if stat=='adaptability':
            increment = base_inc
        else:
            increment = base_inc * player.stats['adaptability']
        text += f"{i}. <b>{stat_name}</b> (+{fmt_float(increment)})\n"
        builder.button(text=f"{i}", callback_data=TrainCB(stat=stat).pack())

    builder.adjust(3)

    nav_row = []
    if page>0:
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
                    f"Вы начали тренировку <b>{STAT_RU.get(stat,stat)}</b>. Вернитесь через 10 секунд.",
                    reply_markup=waiting_kbd(player.state_end_time))

@dp.callback_query(MenuCB.filter(F.action=="hunt"))
async def menu_hunt(query: CallbackQuery, callback_data: MenuCB):
    player = await get_player(query.from_user.id)
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    b = InlineKeyboardBuilder()

    kills_on_current = player.kills_per_difficulty.get(str(player.current_difficulty),0)
    kills_needed = KILLS_TO_UNLOCK_NEXT - kills_on_current if player.current_difficulty==player.max_unlocked_difficulty else 0
    next_unlock_info = ""
    if player.current_difficulty==player.max_unlocked_difficulty and kills_needed>0:
        next_unlock_info = f"\n⚔️ До следующей угрозы осталось убить: {kills_needed} врагов"
    elif player.current_difficulty<player.max_unlocked_difficulty:
        next_unlock_info = f"\n✅ Угроза {player.max_unlocked_difficulty} уже открыта"

    b.button(text="◀️", callback_data=HuntCB(action="dec").pack())
    b.button(text=f"Угроза: {player.current_difficulty}", callback_data=HuntCB(action="set").pack())
    b.button(text="▶️", callback_data=HuntCB(action="inc").pack())
    b.button(text="⚔️ Начать поиск", callback_data=HuntCB(action="start").pack())
    b.button(text="🔙 Назад", callback_data=MenuCB(action="profile").pack())
    b.adjust(3,1,1)

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
        if player.current_difficulty>1:
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
            kills = player.kills_per_difficulty.get(diff_str,0)
            player.kills_per_difficulty[diff_str] = kills + 1

            base_gold = 10 * player.current_difficulty
            actual_gold = int(base_gold * enemy['power_mult'] * player.stats["drop_chance"])
            player.gold += actual_gold
            result_msg += f"\n💰 Найдено золота: {actual_gold}."

            drop_chance_scaled = 0.2 * enemy['power_mult']
            if random.random() < drop_chance_scaled:
                item_type = random.choice(ITEM_TYPES)
                eff_diff = max(1, int(player.current_difficulty * player.stats["drop_chance"]))
                item = generate_item(item_type, eff_diff)
                if len(player.inventory) < player.inv_slots:
                    player.inventory.append(item)
                    result_msg += f"\n📦 Выпал предмет: {item['name']}"
                else:
                    result_msg += "\n📦 Предмет выпал, но инвентарь полон!"

            # Дроп заклинания
            if enemy.get('spells') and random.random() < 0.05:
                dropped = random.choice(enemy['spells']).copy()
                if len(player.spell_inventory) < 20:
                    player.spell_inventory.append(dropped)
                    result_msg += f"\n📜 Вы получили заклинание: {dropped['name']}"
                else:
                    result_msg += "\n📜 Инвентарь заклинаний полон!"

            if player.current_difficulty == player.max_unlocked_difficulty and kills+1 >= KILLS_TO_UNLOCK_NEXT:
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

            # Сохраняем врага в кэш и создаём ключ
            cache_key = f"{query.from_user.id}_{int(time.time())}_{random.randint(1000,9999)}"
            enemy_cache[cache_key] = enemy
            asyncio.create_task(clear_enemy_cache(cache_key, 60))

            back_builder.button(
                text="📊 Статистика боя",
                callback_data=CombatStatsCB(action="show", enemy_data=cache_key).pack()
            )
            back_builder.adjust(2)
            await safe_edit(query.message, f"{log_text}\n\n<b>{result_msg}</b>", reply_markup=back_builder.as_markup())

@dp.message(Form.waiting_for_difficulty)
async def hunt_diff_input(message: Message, state: FSMContext):
    try:
        lvl = int(message.text)
        if lvl>0:
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

@dp.callback_query(CombatStatsCB.filter(F.action=="show"))
async def show_combat_stats(query: CallbackQuery, callback_data: CombatStatsCB):
    player = await get_player(query.from_user.id)
    t_stats = get_total_stats(player)

    # Получаем врага из кэша по ключу
    key = callback_data.enemy_data
    enemy = enemy_cache.get(key)
    if not enemy:
        await query.answer("Данные о бое устарели или не найдены.", show_alert=True)
        return
    # Можно сразу удалить из кэша, чтобы не занимать память
    enemy_cache.pop(key, None)

    text = "📊 <b>Подробная статистика боя</b>\n\n"
    text += "👤 <b>Ваши статы (с учётом экипировки):</b>\n"
    text += f"❤️ Здоровье: {player.stats['hp']:.1f}/{t_stats['max_hp']:.1f} (+{t_stats['hp_regen']:.2f}/мин)\n"
    text += f"✨ МагЩит: {t_stats['m_shield']:.1f}\n"
    text += f"💧 Мана: {player.stats['mp']:.1f}/{t_stats['max_mp']:.1f} (+{t_stats['mp_regen']:.2f}/мин)\n"
    text += f"🗡 Атака: {t_stats['atk']:.2f} | 🔮 Маг.Атака: {t_stats['magic_atk']:.2f}\n"
    text += f"🛡 Защита: {t_stats['def']:.2f} | 💠 Маг.Сопр.: {t_stats['magic_res']:.2f}\n"
    text += f"💥 ШК: {t_stats['crit_chance']:.2f}% | 💢 КУ: {t_stats['crit_damage']:.2f}%\n"
    text += f"✨ МагШК: {t_stats['magic_crit_chance']:.2f}% | 💫 МагКУ: {t_stats['magic_crit_damage']:.2f}%\n"
    text += f"🎯 Точность: {t_stats['accuracy']:.2f} | 💨 Уклонение: {t_stats['evasion_rating']:.2f}\n"
    text += f"🦇 Вампиризм: {t_stats['lifesteal']:.2f}% | 🌵 Шипы: {t_stats['thorns']:.2f}%\n"
    text += f"🔋 Ист.энергии: {t_stats['magic_shield_drain']:.2f}%\n"
    text += f"🪓 Пробитие: {t_stats['armor_pen']} | ⚡ Ск.атаки: {t_stats['atk_spd']:.2f}\n"
    text += f"🍀 Мн.дропа: x{t_stats['drop_chance']:.2f} | 🌟 Адаптивность: {t_stats['adaptability']:.3f}\n\n"

    text += "😡 <b>Статы врага:</b>\n"
    text += f"Класс: {enemy.get('class','Неизвестно')}\n"
    text += f"❤️ Здоровье: {enemy['hp']:.1f}/{enemy['max_hp']:.1f}\n"
    text += f"✨ МагЩит: {enemy.get('m_shield', 0):.1f}\n" 
    text += f"🗡 Атака: {enemy['atk']:.2f} | 🔮 Маг.Атака: {enemy['magic_atk']:.2f}\n"
    text += f"🛡 Защита: {enemy['def']:.2f} | 💠 Маг.Сопр.: {enemy['magic_res']:.2f}\n"
    text += f"🎯 Точность: {enemy['accuracy']:.2f} | 💨 Уклонение: {enemy['evasion_rating']:.2f}\n"
    text += f"💥 ШК: {enemy['crit_chance']:.1f}% | 💢 КУ: {enemy['crit_damage']:.1f}%\n"
    text += f"✨ МагШК: {enemy.get('magic_crit_chance',0):.1f}% | 💫 МагКУ: {enemy.get('magic_crit_damage',150):.1f}%\n"
    text += f"🩸 Вампиризм: {enemy['lifesteal']:.1f}% | 🌵 Шипы: {enemy['thorns']:.1f}%\n"
    text += f"🔋 Ист.энергии: {enemy.get('magic_shield_drain',0):.1f}%\n"
    text += f"⚡ Ск.атаки: {enemy['atk_spd']:.2f}\n"

    await query.message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data=MenuCB(action="hunt").pack())]
    ]))
    await query.answer()

# ===================== ИНВЕНТАРЬ (предметы) =====================
@dp.callback_query(MenuCB.filter(F.action=="inv"))
async def menu_inv(query: CallbackQuery, callback_data: MenuCB):
    player = await get_player(query.from_user.id)
    text = f"💰 Золото: {player.gold}\n\n🎒 <b>Инвентарь ({len(player.inventory)}/{player.inv_slots})</b>\n\nЭкипировано:\n"

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    b = InlineKeyboardBuilder()

    all_items = []
    btn_index = 0

    for slot, item in player.equip.items():
        slot_ru = {
            "right_hand":"Правая рука","left_hand":"Левая рука","boots":"Обувь",
            "belt":"Пояс","robe":"Одежда","helmet":"Голова",
            "amulet":"Амулет","ring1":"Кольцо 1","ring2":"Кольцо 2"
        }.get(slot,slot)
        if item:
            text += f"{btn_index+1}. [{slot_ru}] {item['name']}\n"
            b.button(text=f"{btn_index+1}", callback_data=ItemCB(action="view", idx=btn_index).pack())
            all_items.append({"data":item,"is_equip":True,"slot":slot,"real_idx":-1})
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
            all_items.append({"data":item,"is_equip":False,"slot":None,"real_idx":real_idx})
            btn_index += 1

    b.adjust(5)
    b.row(InlineKeyboardButton(text="💰 Массовая продажа", callback_data=SellMassCB(action="menu").pack()))
    b.row(InlineKeyboardButton(text="🔙 Назад", callback_data=MenuCB(action="profile").pack()))

    await safe_edit(query.message, text, reply_markup=b.as_markup())

@dp.callback_query(ItemCB.filter(F.action=="view"))
async def view_item(query: CallbackQuery, callback_data: ItemCB):
    player = await get_player(query.from_user.id)
    idx = callback_data.idx

    text, reply_markup = await get_item_view_data(player, idx)
    if text is None:
        await query.answer("Предмет не найден!")
        return

    await safe_edit(query.message, text, reply_markup)

@dp.callback_query(ItemCB.filter(F.action=="choose_slot"))
async def choose_slot_for_equip(query: CallbackQuery, callback_data: ItemCB, state: FSMContext):
    player = await get_player(query.from_user.id)
    idx = callback_data.idx
    if idx >= len(player.inventory):
        await query.answer("Предмет не найден!")
        return
    item = player.inventory[idx]
    allowed_slots = ITEM_TYPE_TO_SLOTS.get(item['item_type'], [])
    if not allowed_slots:
        await query.answer("Этот предмет нельзя надеть!")
        return

    await state.update_data(item_idx=idx)

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    for slot in allowed_slots:
        slot_ru = {
            "right_hand":"Правая рука","left_hand":"Левая рука","boots":"Обувь",
            "belt":"Пояс","robe":"Одежда","helmet":"Голова",
            "amulet":"Амулет","ring1":"Кольцо 1","ring2":"Кольцо 2"
        }.get(slot,slot)
        builder.button(text=slot_ru, callback_data=EquipChoiceCB(item_idx=idx, slot=slot).pack())
    builder.button(text="❌ Отмена", callback_data=MenuCB(action="inv").pack())
    builder.adjust(1)
    await safe_edit(query.message, "Выберите слот для экипировки:", reply_markup=builder.as_markup())

@dp.callback_query(ItemCB.filter(F.action=="equip"))
async def equip_item_single_slot(query: CallbackQuery, callback_data: ItemCB, state: FSMContext):
    player = await get_player(query.from_user.id)
    idx = callback_data.idx
    if idx >= len(player.inventory):
        await query.answer("Предмет не найден!")
        return
    item = player.inventory[idx]
    allowed_slots = ITEM_TYPE_TO_SLOTS.get(item['item_type'], [])
    if not allowed_slots:
        await query.answer("Этот предмет нельзя надеть!")
        return
    # Берём первый слот
    slot = allowed_slots[0]
    # Проверяем, можно ли надеть (аналогично equip_to_slot)
    hands_used = ITEM_HANDS_USED.get(item['item_type'],0)
    if hands_used == 2:
        if player.equip['right_hand'] is not None or player.equip['left_hand'] is not None:
            await query.answer("Для двуручного оружия обе руки должны быть свободны!", show_alert=True)
            return
    else:
        if player.equip[slot] is not None:
            await query.answer("Этот слот занят! Сначала снимите предмет.", show_alert=True)
            return
        if slot in ['right_hand','left_hand']:
            other_hand = 'left_hand' if slot=='right_hand' else 'right_hand'
            if player.equip[other_hand] is not None:
                other_item = player.equip[other_hand]
                if ITEM_HANDS_USED.get(other_item['item_type'],0)==2:
                    await query.answer("Нельзя надеть одноручное оружие, пока в другой руке двуручное!", show_alert=True)
                    return

    old_item = player.equip[slot]
    if old_item:
        if len(player.inventory) >= player.inv_slots:
            await query.answer("Нет места в инвентаре для снятого предмета!", show_alert=True)
            return
        player.inventory.append(old_item)
    player.equip[slot] = item
    player.inventory.pop(idx)

    if hands_used == 2:
        other = 'left_hand' if slot=='right_hand' else 'right_hand'
        player.equip[other] = item

    await save_player(player)
    await query.answer(f"Экипировано в {slot}!")
    await menu_inv(query, MenuCB(action="inv"))

@dp.callback_query(EquipChoiceCB.filter())
async def equip_to_slot(query: CallbackQuery, callback_data: EquipChoiceCB, state: FSMContext):
    player = await get_player(query.from_user.id)
    idx = callback_data.item_idx
    slot = callback_data.slot

    if idx >= len(player.inventory):
        await query.answer("Предмет не найден!")
        return
    item = player.inventory[idx]

    allowed = ITEM_TYPE_TO_SLOTS.get(item['item_type'], [])
    if slot not in allowed:
        await query.answer("Этот предмет нельзя надеть в выбранный слот!", show_alert=True)
        return

    hands_used = ITEM_HANDS_USED.get(item['item_type'],0)
    if hands_used == 2:
        if player.equip['right_hand'] is not None or player.equip['left_hand'] is not None:
            await query.answer("Для двуручного оружия обе руки должны быть свободны!", show_alert=True)
            return
    else:
        if player.equip[slot] is not None:
            await query.answer("Этот слот занят! Сначала снимите предмет.", show_alert=True)
            return
        if slot in ['right_hand','left_hand']:
            other_hand = 'left_hand' if slot=='right_hand' else 'right_hand'
            if player.equip[other_hand] is not None:
                other_item = player.equip[other_hand]
                if ITEM_HANDS_USED.get(other_item['item_type'],0)==2:
                    await query.answer("Нельзя надеть одноручное оружие, пока в другой руке двуручное!", show_alert=True)
                    return

    old_item = player.equip[slot]
    if old_item:
        player.inventory.append(old_item)
    player.equip[slot] = item
    player.inventory.pop(idx)

    if hands_used == 2:
        other = 'left_hand' if slot=='right_hand' else 'right_hand'
        player.equip[other] = item

    await save_player(player)
    await query.answer(f"Экипировано в {slot}!")
    await menu_inv(query, MenuCB(action="inv"))

@dp.callback_query(ItemCB.filter(F.action=="unequip"))
async def uneq_item(query: CallbackQuery, callback_data: ItemCB):
    player = await get_player(query.from_user.id)
    idx = callback_data.idx
    if idx >= 900:  # экипированный предмет
        slot_index = idx - 900
        slots = list(player.equip.keys())
        if slot_index >= len(slots):
            return
        slot = slots[slot_index]
    else:
        await query.answer("Ошибка: предмет не экипирован.")
        return
    item = player.equip[slot]
    if item:
        if len(player.inventory) < player.inv_slots:
            player.inventory.append(item)
            player.equip[slot] = None
            if ITEM_HANDS_USED.get(item['item_type'],0)==2:
                other = 'left_hand' if slot=='right_hand' else 'right_hand'
                player.equip[other] = None
            await save_player(player)
            await query.answer("Предмет снят!")
            await menu_inv(query, MenuCB(action="inv"))
        else:
            await query.answer("В инвентаре нет места!", show_alert=True)
    else:
        await query.answer("Предмет не найден.")

@dp.callback_query(ItemCB.filter(F.action=="sell"))
async def sell_item(query: CallbackQuery, callback_data: ItemCB):
    player = await get_player(query.from_user.id)
    idx = callback_data.idx
    if idx >= len(player.inventory):
        return
    item = player.inventory.pop(idx)
    earn = item.get("sell_price",10)
    player.gold += earn
    await save_player(player)
    await query.answer(f"Продано за {earn} золота.")
    await menu_inv(query, MenuCB(action="inv"))

@dp.callback_query(ItemCB.filter(F.action=="upg"))
async def upg_item(query: CallbackQuery, callback_data: ItemCB):
    player = await get_player(query.from_user.id)
    idx = callback_data.idx
    stat_key = callback_data.stat

    is_equip = idx < 900
    if is_equip:
        slots = list(player.equip.keys())
        if idx >= len(slots):
            return
        slot = slots[idx]
        item = player.equip[slot]
    else:
        inv_idx = idx - 900
        if inv_idx >= len(player.inventory):
            return
        item = player.inventory[inv_idx]

    if not item or stat_key not in item["stats"]:
        return

    s_data = item["stats"][stat_key]
    raw_cost = (s_data['base']*50 + s_data['upgrades']*s_data['base']*20) * s_data.get('upgrade_price_mult',1.0)
    upg_cost = max(250, int(raw_cost))

    if player.gold >= upg_cost:
        player.gold -= upg_cost
        s_data['upgrades'] += 1
        s_data['current'] = s_data['base'] * (s_data['upgrades']+1)
        item['sell_price'] += int(upg_cost*0.3)

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

@dp.callback_query(SellMassCB.filter(F.action=="menu"))
async def sell_mass_menu(query: CallbackQuery, callback_data: SellMassCB):
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    builder.button(text="Продать всё", callback_data=SellMassCB(action="all").pack())
    builder.button(text="Продать по цене", callback_data=SellMassCB(action="price").pack())
    builder.button(text="🔙 Назад", callback_data=MenuCB(action="inv").pack())
    builder.adjust(1)
    await safe_edit(query.message, "Выберите тип массовой продажи:", reply_markup=builder.as_markup())

@dp.callback_query(SellMassCB.filter(F.action=="all"))
async def sell_mass_all(query: CallbackQuery, callback_data: SellMassCB):
    player = await get_player(query.from_user.id)
    if not player.inventory:
        await query.answer("Инвентарь пуст!", show_alert=True)
        return
    total = 0
    sold_items = []
    for item in player.inventory[:]:
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

@dp.callback_query(SellMassCB.filter(F.action=="price"))
async def sell_mass_price(query: CallbackQuery, callback_data: SellMassCB, state: FSMContext):
    await query.message.answer("Введите максимальную цену предмета (число, всё ниже этой цены будет продано):")
    await state.set_state(Form.waiting_for_sell_price)
    await query.answer()

@dp.message(Form.waiting_for_sell_price)
async def sell_mass_price_input(message: Message, state: FSMContext):
    try:
        max_price = int(message.text)
        if max_price<0: raise ValueError
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
        await message.answer(f"💰 Продано:\n{sold_list}\n\nПолучено: {total} золота.\nТеперь у вас {player.gold} золота.",
                             reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                                 [InlineKeyboardButton(text="🔙 В инвентарь", callback_data=MenuCB(action="inv").pack())]
                             ]))
    await state.clear()

# ===================== МАГАЗИН =====================
@dp.callback_query(MenuCB.filter(F.action=="shop"))
async def menu_shop(query: CallbackQuery, callback_data: MenuCB):
    player = await get_player(query.from_user.id)
    await update_shop(player)

    cost_slot = 1000 + ((player.inv_slots - 10) * 2000)

    text = f"💰 Золото: {player.gold}\n🏪 <b>Магазин (обновляется каждые 5 мин)</b>\nРедкость: {player.shop_rarity} (влияет на новые товары)\n\nАссортимент:\n"

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
            stat_desc = ", ".join([f"{STAT_EMOJI.get(k,'')}{STAT_RU.get(k,k)}:{v['base']:.2f}" for k,v in it['stats'].items()])
            price = entry["price"]
            text += f"\n{idx}. 📦 {it['name']} ({stat_desc})\n   Стоимость: 💰 {price}\n"
            b.button(text=f"{idx}", callback_data=ShopCB(action="buy_it", idx=i).pack())
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
        if player.shop_rarity>1:
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
            t_stats = get_total_stats(player)
            player.stats['hp'] = t_stats['max_hp']
            player.stats['mp'] = t_stats['max_mp']
            await save_player(player)
            await query.answer("Здоровье и мана восстановлены!")
            await menu_shop(query, MenuCB(action="shop"))
        else:
            await query.answer("Недостаточно золота!", show_alert=True)
    elif act in ["buy_it"]:
        idx = callback_data.idx
        entry = player.shop_assortment[idx]
        if entry["sold"]:
            await query.answer("Уже продано!")
            return
        obj = entry["item"]
        price = entry["price"]

        if player.gold >= price:
            if len(player.inventory) < player.inv_slots:
                player.gold -= price
                player.inventory.append(obj)
                entry["sold"] = True
                await save_player(player)
                await query.answer("Предмет куплен!")
            else:
                await query.answer("Инвентарь полон!", show_alert=True)
                return
            await menu_shop(query, MenuCB(action="shop"))
        else:
            await query.answer("Недостаточно золота!", show_alert=True)

@dp.message(Form.waiting_for_shop_rarity)
async def shop_rarity_input(message: Message, state: FSMContext):
    try:
        lvl = int(message.text)
        if lvl>0:
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

# ===================== ЛАВКА ЗЕЛИЙ =====================
@dp.callback_query(MenuCB.filter(F.action=="potions"))
async def menu_potions(query: CallbackQuery, callback_data: MenuCB):
    player = await get_player(query.from_user.id)
    await update_potion_shop(player)

    text = f"💰 Золото: {player.gold}\n🧪 <b>Лавка зелий (обновляется каждые 5 мин)</b>\n\nАссортимент:\n"

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
            if pot["stat"] == "adaptability":
                player.stats[pot["stat"]] += pot["value"]
            else:
                player.stats[pot["stat"]] += pot["value"] * player.stats["adaptability"]
            entry["sold"] = True
            await save_player(player)
            await query.answer(f"Вы выпили зелье! {STAT_RU[pot['stat']]} увеличен.")
            await menu_potions(query, MenuCB(action="potions"))
        else:
            await query.answer("Недостаточно золота!", show_alert=True)

# ===================== ЭКСПЕДИЦИЯ =====================
@dp.callback_query(MenuCB.filter(F.action=="exped"))
async def menu_exped(query: CallbackQuery, callback_data: MenuCB):
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    b = InlineKeyboardBuilder()
    b.button(text="Отправиться (5 мин)", callback_data=ActionCB(action="start_exped").pack())
    b.button(text="🔙 Назад", callback_data=MenuCB(action="profile").pack())
    b.adjust(1)
    await safe_edit(query.message,
                    f"💰 Золото: {(await get_player(query.from_user.id)).gold}\n🧭 <b>Экспедиция</b>\nБезопасный поиск золота и ресурсов. Вы не сможете сражаться или тренироваться 5 минут.\n"
                    "Шанс найти несколько предметов!",
                    reply_markup=b.as_markup())

@dp.callback_query(ActionCB.filter(F.action=="start_exped"))
async def start_exped(query: CallbackQuery, callback_data: ActionCB):
    player = await get_player(query.from_user.id)
    player.state = 'expedition'
    player.state_end_time = time.time() + CONFIG["time_expedition"]
    await save_player(player)
    await safe_edit(query.message,
                    "Вы отправились в экспедицию. Вернитесь через 5 минут.",
                    reply_markup=waiting_kbd(player.state_end_time))

# ===================== НОВОЕ МЕНЮ МАГИИ =====================
@dp.callback_query(MenuCB.filter(F.action=="spells"))
async def menu_spells(query: CallbackQuery, callback_data: MenuCB):
    player = await get_player(query.from_user.id)

    text = f"💰 Золото: {player.gold}\n🔮 <b>Магия</b>\n\nАктивные слоты (5):\n"
    for i, spell in enumerate(player.active_spells):
        if spell:
            text += f"Слот {i+1}: {spell['name']} (МП:{spell['mp_cost']}, КД:{spell['base_cooldown']:.1f}с, улучш.{spell['upgrades']})\n"
        else:
            text += f"Слот {i+1}: Пусто\n"

    text += f"\nИнвентарь заклинаний ({len(player.spell_inventory)}/20):\n"
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    b = InlineKeyboardBuilder()

    for i, spell in enumerate(player.spell_inventory):
        passive = " (пасс)" if spell.get('is_passive') else ""
        text += f"{i+1}. {spell['name']}{passive} | МП:{spell['mp_cost']} | КД:{spell['base_cooldown']:.1f}с\n"
        b.button(text=f"{i+1}", callback_data=SpellCB(action="view", idx=i).pack())

    if player.spell_inventory:
        b.adjust(5)
    else:
        text += "Пусто"

    b.row(InlineKeyboardButton(text="🔙 Назад", callback_data=MenuCB(action="profile").pack()))

    await safe_edit(query.message, text, reply_markup=b.as_markup())

@dp.callback_query(SpellCB.filter(F.action=="view"))
async def view_spell(query: CallbackQuery, callback_data: SpellCB):
    player = await get_player(query.from_user.id)
    idx = callback_data.idx
    if idx >= len(player.spell_inventory):
        await query.answer("Заклинание не найдено!")
        return
    spell = player.spell_inventory[idx]

    text = f"🔮 <b>{spell['name']}</b>\n"
    text += f"📖 Описание:\n"
    for eff in spell['effects']:
        target = "на себя" if eff['target']==TARGET_SELF else "на врага"
        if eff['type']=='damage':
            text += f"• Наносит {eff['base_value']:.1f} магического урона {target}\n"
        elif eff['type']=='heal':
            text += f"• Лечит {eff['base_value']:.1f} HP {target}\n"
        elif eff['type']=='dot':
            text += f"• Наносит {eff['base_value']:.1f} урона каждые {eff['interval']}с в течение {eff['duration']}с {target}\n"
        elif eff['type']=='hot':
            text += f"• Лечит {eff['base_value']:.1f} HP каждые {eff['interval']}с в течение {eff['duration']}с {target}\n"
        elif eff['type']=='buff':
            text += f"• Увеличивает {STAT_RU.get(eff['stat'],eff['stat'])} на {eff['base_value']*100:.0f}% на {eff['duration']}с {target}\n"
        elif eff['type']=='debuff':
            text += f"• Уменьшает {STAT_RU.get(eff['stat'],eff['stat'])} на {eff['base_value']*100:.0f}% на {eff['duration']}с {target}\n"
        elif eff['type']=='shield':
            text += f"• Даёт {eff['base_value']} магического щита {target}\n"
        elif eff['type']=='time_stop':
            text += f"• Останавливает время на {eff['duration']}с {target}\n"
        elif eff['type']=='mp_restore':
            text += f"• Восстанавливает {eff['base_value']} маны {target}\n"
        elif eff['type']=='mp_burn':
            text += f"• Сжигает {eff['base_value']} маны {target}\n"

    text += f"\n💰 Стоимость маны: {spell['mp_cost']}\n"
    text += f"⏱ Базовая перезарядка: {spell['base_cooldown']:.1f}с\n"
    text += f"📈 Улучшений: {spell['upgrades']}\n"
    text += f"💰 Цена продажи: {spell['sell_price']}\n"

    upg_cost = int(spell['mp_cost'] * 10 + spell['upgrades'] * 20)  # примерная стоимость улучшения
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    b = InlineKeyboardBuilder()
    b.button(text="🔙 Назад", callback_data=MenuCB(action="spells").pack())
    b.button(text=f"Улучшить (💰 {upg_cost})", callback_data=SpellCB(action="upgrade", idx=idx).pack())
    b.button(text="Выбросить", callback_data=SpellCB(action="discard", idx=idx).pack())
    b.button(text="Экипировать", callback_data=SpellCB(action="equip", idx=idx).pack())
    b.adjust(2,2)

    await safe_edit(query.message, text, reply_markup=b.as_markup())

@dp.callback_query(SpellCB.filter(F.action=="equip"))
async def equip_spell(query: CallbackQuery, callback_data: SpellCB, state: FSMContext):
    player = await get_player(query.from_user.id)
    idx = callback_data.idx
    if idx >= len(player.spell_inventory):
        await query.answer("Заклинание не найдено!")
        return

    # Показываем выбор слота
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    b = InlineKeyboardBuilder()
    for slot in range(5):
        slot_name = f"Слот {slot+1}"
        if player.active_spells[slot] is not None:
            slot_name += f" ({player.active_spells[slot]['name']})"
        b.button(text=slot_name, callback_data=SpellCB(action="equip_slot", idx=idx, slot=slot).pack())
    b.button(text="❌ Отмена", callback_data=MenuCB(action="spells").pack())
    b.adjust(1)

    await safe_edit(query.message, "Выберите слот для экипировки:", reply_markup=b.as_markup())

@dp.callback_query(SpellCB.filter(F.action=="equip_slot"))
async def equip_spell_slot(query: CallbackQuery, callback_data: SpellCB):
    player = await get_player(query.from_user.id)
    idx = callback_data.idx
    slot = callback_data.slot
    if idx >= len(player.spell_inventory):
        await query.answer("Заклинание не найдено!")
        return
    spell = player.spell_inventory[idx]
    old = player.active_spells[slot]

    # Проверяем, не превысит ли лимит инвентаря, если есть старое заклинание
    if old and len(player.spell_inventory) >= 20:
        await query.answer("Невозможно заменить: инвентарь заклинаний полон (макс. 20)!", show_alert=True)
        return

    # Если слот занят, меняем местами (кладём старое в инвентарь)
    if old:
        player.spell_inventory.append(old)
    player.active_spells[slot] = spell
    # Убираем новое заклинание из инвентаря
    player.spell_inventory.pop(idx)

    await save_player(player)
    await query.answer(f"Заклинание {spell['name']} экипировано в слот {slot+1}.")
    await menu_spells(query, MenuCB(action="spells"))

# ===================== ПРОСМОТР АКТИВНОГО СЛОТА =====================
@dp.callback_query(SpellCB.filter(F.action == "view_slot"))
async def view_active_spell(query: CallbackQuery, callback_data: SpellCB):
    player = await get_player(query.from_user.id)
    slot = callback_data.slot
    if slot < 0 or slot >= 5:
        await query.answer("Неверный слот")
        return
    spell = player.active_spells[slot]
    if not spell:
        await query.answer("Слот пуст")
        return

    text = f"🔮 <b>{spell['name']}</b> (активный слот {slot+1})\n"
    text += f"📖 Описание:\n"
    for eff in spell['effects']:
        target = "на себя" if eff['target']==TARGET_SELF else "на врага"
        if eff['type']=='damage':
            text += f"• Наносит {eff['base_value']:.1f} магического урона {target}\n"
        elif eff['type']=='heal':
            text += f"• Лечит {eff['base_value']:.1f} HP {target}\n"
        elif eff['type']=='dot':
            text += f"• Наносит {eff['base_value']:.1f} урона каждые {eff['interval']}с в течение {eff['duration']}с {target}\n"
        elif eff['type']=='hot':
            text += f"• Лечит {eff['base_value']:.1f} HP каждые {eff['interval']}с в течение {eff['duration']}с {target}\n"
        elif eff['type']=='buff':
            text += f"• Увеличивает {STAT_RU.get(eff['stat'],eff['stat'])} на {eff['base_value']*100:.0f}% на {eff['duration']}с {target}\n"
        elif eff['type']=='debuff':
            text += f"• Уменьшает {STAT_RU.get(eff['stat'],eff['stat'])} на {eff['base_value']*100:.0f}% на {eff['duration']}с {target}\n"
        elif eff['type']=='shield':
            text += f"• Даёт {eff['base_value']} магического щита {target}\n"
        elif eff['type']=='time_stop':
            text += f"• Останавливает время на {eff['duration']}с {target}\n"
        elif eff['type']=='mp_restore':
            text += f"• Восстанавливает {eff['base_value']} маны {target}\n"
        elif eff['type']=='mp_burn':
            text += f"• Сжигает {eff['base_value']} маны {target}\n"

    text += f"\n💰 Стоимость маны: {spell['mp_cost']}\n"
    text += f"⏱ Базовая перезарядка: {spell['base_cooldown']:.1f}с\n"
    text += f"📈 Улучшений: {spell['upgrades']}\n"

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    b = InlineKeyboardBuilder()
    b.button(text="🔙 Назад", callback_data=MenuCB(action="spells").pack())
    b.button(text="Снять", callback_data=SpellCB(action="unequip", idx=slot, slot=slot).pack())  # используем idx для слота, но передаём slot
    b.adjust(2)

    await safe_edit(query.message, text, reply_markup=b.as_markup())

@dp.callback_query(SpellCB.filter(F.action == "unequip"))
async def unequip_spell(query: CallbackQuery, callback_data: SpellCB):
    player = await get_player(query.from_user.id)
    slot = callback_data.slot  # слот, из которого снимаем
    if slot < 0 or slot >= 5:
        await query.answer("Неверный слот")
        return
    spell = player.active_spells[slot]
    if not spell:
        await query.answer("Слот пуст")
        return

    # Проверяем, есть ли место в инвентаре заклинаний (лимит 20)
    if len(player.spell_inventory) >= 20:
        await query.answer("Инвентарь заклинаний полон (макс. 20)!", show_alert=True)
        return

    # Перемещаем
    player.spell_inventory.append(spell)
    player.active_spells[slot] = None
    await save_player(player)
    await query.answer(f"Заклинание {spell['name']} снято в инвентарь.")
    await menu_spells(query, MenuCB(action="spells"))

# ===================== ОБНОВЛЕНИЕ МЕНЮ МАГИИ (добавляем кнопки для активных слотов) =====================
# Переопределим menu_spells, чтобы добавить кнопки для активных слотов
@dp.callback_query(MenuCB.filter(F.action=="spells"))
async def menu_spells(query: CallbackQuery, callback_data: MenuCB):
    player = await get_player(query.from_user.id)

    text = f"💰 Золото: {player.gold}\n🔮 <b>Магия</b>\n\nАктивные слоты (5):\n"
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    b = InlineKeyboardBuilder()

    # Кнопки для активных слотов (если не пусто)
    for i, spell in enumerate(player.active_spells):
        if spell:
            text += f"Слот {i+1}: {spell['name']} (МП:{spell['mp_cost']}, КД:{spell['base_cooldown']:.1f}с, улучш.{spell['upgrades']})\n"
            b.button(text=f"Слот {i+1}", callback_data=SpellCB(action="view_slot", idx=i, slot=i).pack())
        else:
            text += f"Слот {i+1}: Пусто\n"
            # Можно добавить кнопку для пустого слота, но не обязательно

    text += f"\nИнвентарь заклинаний ({len(player.spell_inventory)}/20):\n"

    for i, spell in enumerate(player.spell_inventory):
        passive = " (пасс)" if spell.get('is_passive') else ""
        text += f"{i+1}. {spell['name']}{passive} | МП:{spell['mp_cost']} | КД:{spell['base_cooldown']:.1f}с\n"
        b.button(text=f"{i+1}", callback_data=SpellCB(action="view", idx=i).pack())

    if player.spell_inventory:
        b.adjust(5)  # подряд 5 кнопок для инвентаря, но у нас ещё есть кнопки слотов, нужно аккуратно
    else:
        text += "Пусто"

    # Добавляем кнопки навигации
    b.row(InlineKeyboardButton(text="🔙 Назад", callback_data=MenuCB(action="profile").pack()))

    await safe_edit(query.message, text, reply_markup=b.as_markup())

@dp.callback_query(SpellCB.filter(F.action=="upgrade"))
async def upgrade_spell(query: CallbackQuery, callback_data: SpellCB):
    player = await get_player(query.from_user.id)
    idx = callback_data.idx
    if idx >= len(player.spell_inventory):
        await query.answer("Заклинание не найдено!")
        return
    spell = player.spell_inventory[idx]
    cost = int(spell['mp_cost'] * 10 + spell['upgrades'] * 20)
    if player.gold >= cost:
        player.gold -= cost
        spell['upgrades'] += 1
        spell['mp_cost'] = int(spell['mp_cost'] * 1.1)  # стоимость маны растёт
        spell['base_cooldown'] = spell['base_cooldown'] * 0.95  # кд уменьшается
        for eff in spell['effects']:
            eff['base_value'] *= 1.1  # сила эффекта растёт
        spell['sell_price'] = int(spell['sell_price'] * 1.3)
        await save_player(player)
        await query.answer("Заклинание улучшено!")
        await view_spell(query, SpellCB(action="view", idx=idx))
    else:
        await query.answer("Недостаточно золота!", show_alert=True)

@dp.callback_query(SpellCB.filter(F.action=="discard"))
async def discard_spell(query: CallbackQuery, callback_data: SpellCB):
    player = await get_player(query.from_user.id)
    idx = callback_data.idx
    if idx >= len(player.spell_inventory):
        await query.answer("Заклинание не найдено!")
        return
    spell = player.spell_inventory.pop(idx)
    await save_player(player)
    await query.answer(f"Заклинание {spell['name']} выброшено.")
    await menu_spells(query, MenuCB(action="spells"))

# ===================== ЗАПУСК =====================
async def main():
    print("Запуск бота на aiogram 3.x...")
    await load_db()
    asyncio.create_task(background_worker())
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
