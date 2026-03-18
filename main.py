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
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter

TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

logging.basicConfig(level=logging.INFO)

DATA_DIR = 'data'
os.makedirs(DATA_DIR, exist_ok=True)
DB_FILE = os.path.join(DATA_DIR, 'database.json')

def fmt_float(num, max_precision=3):
    # Форматирует число, убирая лишние нули в конце
    s = f"{num:.{max_precision}f}".rstrip('0').rstrip('.')
    return s

db_lock = asyncio.Lock()
db = {}
enemy_cache = {}
user_locks = {}
leaderboard_cache = {
    'last_update': 0,
    'full_sorted': [],   # список кортежей (uid, name, username, difficulty)
    'top_25': ""
}

#Константы
KILLS_TO_UNLOCK_NEXT = 25
GOLD_PER_STAGE = 10
DUST_PER_BATTLE = 50
SHOP_BASE_PRICE = 15 * GOLD_PER_STAGE
ITEM_DROP_CHANCE_FROM_ENEMY = 0.075
SPELL_DROP_CHANCE = 0.05
ARCANE_GEOMETRIC_MULT = 0.1

MAX_GUARANTEED_STATS = 5
MAX_STATS_COUNT = 10
MAX_STATS_PER_ITEM = {"ring": 12}

TWOHAND_MULTIPLIER = 2.0
TOME_MULTIPLIER = 5.0

# ===================== СТАТЫ =====================
#Названия статов на русском
STAT_RU = {
    "adaptability": "Адаптивность",
    "max_hp": "Макс. Здоровье", "hp": "Здоровье", "max_mp": "Макс. Мана", "mp": "Мана",
    "atk": "Физ. Атака", "def": "Физ. Защита", "m_shield": "Магический Щит",
    "crit_chance": "Шанс Крита", "crit_damage": "Крит. Урон", "accuracy": "Точность",
    "evasion_rating": "Уклонение", "atk_spd": "Скор. Атаки",
    "hp_regen": "Реген Здоровья", "mp_regen": "Реген Маны",
    "gold_mult": "Множитель Золота",
    "luck": "Удача",
    "talent": "Талант",
    "lifesteal": "Вампиризм", "armor_pen": "Пробитие Брони", "thorns": "Шипы",
    "magic_atk": "Маг. Атака", "magic_res": "Маг. Сопротивление", "magic_efficiency": "Маг. Эффективность",
    "magic_crit_chance": "Маг. шанс крита",
    "magic_crit_damage": "Маг. крит урон",
    "magic_shield_drain": "Восстановление щита",
    "effect_resistance": "Сопр. эффектам"
}

#Смайлики для отображения каждого из статов
STAT_EMOJI = {
    "max_hp": "❤️", "hp": "❤️", "max_mp": "💧", "mp": "💧",
    "atk": "🗡️", "def": "🛡️", "m_shield": "🪬",
    "crit_chance": "💥", "crit_damage": "💢", "accuracy": "🎯", "evasion_rating": "💨",
    "atk_spd": "⚡", "hp_regen": "💊", "mp_regen": "🔮",
    "gold_mult": "💰", "luck": "🍀", "talent": "🎓","lifesteal": "🩸", "armor_pen": "🪓",
    "magic_atk": "🪄", "magic_res": "🌀", "magic_efficiency": "🔹", "thorns": "🌵", "adaptability": "🌟",
    "magic_crit_chance": "✨", "magic_crit_damage": "💫", "magic_shield_drain": "🔋", "effect_resistance":"🧿"
}

#Название типов предметов на русском
ITEM_TYPE_RU = {
    "weapon1h_physical": "⚔️ Одноручное физ.",
    "weapon1h_magical": "🪄 Одноручное маг.",
    "weapon2h_physical": "⚔️ Двуручное физ.",
    "weapon2h_magical": "🪄 Двуручное маг.",
    "shield": "🛡 Щит",
    "tome": "📖 Фолиант",
    "tome2h": "📚 Тяжёлый фолиант",
    "boots": "👢 Обувь",
    "belt": "🧣 Пояс",
    "robe": "👘 Одежда",
    "helmet": "⛑ Голова",
    "amulet": "📿 Амулет",
    "ring": "💍 Кольцо"
}

#Названия слотов на русском
SLOT_RU = {
    "right_hand": "✋ Правая рука",
    "left_hand": "🤚 Левая рука",
    "helmet": "⛑️ Голова",
    "robe": "👘 Одежда",
    "belt": "🧣 Пояс",
    "boots": "👢 Обувь",
    "amulet": "📿 Амулет",
    "ring1": "💍 Кольцо 1",
    "ring2": "💍 Кольцо 2"
}

#Кол-во статов получаемых за 1 тренировку
TRAINING_INCREMENTS = {
    "adaptability": 0.005,
    "max_hp": 3.0,
    "max_mp": 3.0,
    "m_shield": 2.0,
    "atk": 0.33,
    "def": 0.33,
    "magic_atk": 0.33,
    "magic_res": 0.33,
    "crit_chance": 0.05,
    "crit_damage": 0.25,
    "accuracy": 0.15,
    "evasion_rating": 0.1,
    "atk_spd": 0.005,
    "hp_regen": 0.2,
    "mp_regen": 0.2,
    "gold_mult": 0.005,
    "luck": 0.005,
    "talent": 0.005,
    "lifesteal": 0.01,
    "armor_pen": 0.15,
    "thorns": 0.05,
    "magic_efficiency": 0.25,
    "magic_crit_chance": 0.05,
    "magic_crit_damage": 0.25,
    "magic_shield_drain": 0.01,
    "effect_resistance": 0.25,
}

# ===================== СЛОТЫ И ПРЕДМЕТЫ =====================

#Слоты, в которые можно что-то положить
EQUIP_SLOTS = [
    "right_hand", "left_hand", "boots", "belt", "robe", "helmet", "amulet", "ring1", "ring2"
]

#Все типы предметов в игре
ITEM_TYPES = [
    "weapon1h_physical", "weapon1h_magical", "weapon2h_physical", "weapon2h_magical",
    "shield", "tome", "tome2h", "boots", "belt", "robe", "helmet", "amulet", "ring"
]

#Словарь, говорящий какой тип предмета в какие слоты можно положить
ITEM_TYPE_TO_SLOTS = {
    "weapon1h_physical": ["right_hand", "left_hand"],
    "weapon1h_magical": ["right_hand", "left_hand"],
    "weapon2h_physical": ["right_hand", "left_hand"],
    "weapon2h_magical": ["right_hand", "left_hand"],
    "shield": ["right_hand", "left_hand"],
    "tome": ["right_hand", "left_hand"],
    "tome2h": ["right_hand", "left_hand"],
    "boots": ["boots"],
    "belt": ["belt"],
    "robe": ["robe"],
    "helmet": ["helmet"],
    "amulet": ["amulet"],
    "ring": ["ring1", "ring2"]
}

#сколько рук требуется предметам (нужно для двуруков и оружий)
ITEM_HANDS_USED = {
    "weapon1h_physical": 1,
    "weapon1h_magical": 1,
    "weapon2h_physical": 2,
    "weapon2h_magical": 2,
    "shield": 1,
    "tome": 1,
    "tome2h": 2,
    "boots": 0,
    "belt": 0,
    "robe": 0,
    "helmet": 0,
    "amulet": 0,
    "ring": 0
}

#Какие статы для каких предметов разрешены
ITEM_ALLOWED_STATS = {
    "weapon1h_physical": ["atk", "atk_spd", "crit_chance", "crit_damage", "armor_pen", "accuracy", "lifesteal"],
    "weapon1h_magical": ["magic_atk", "atk_spd", "magic_crit_chance", "magic_crit_damage", "magic_shield_drain"],
    "weapon2h_physical": ["atk", "atk_spd", "crit_chance", "crit_damage", "armor_pen", "accuracy", "lifesteal"],
    "weapon2h_magical": ["magic_atk", "atk_spd", "crit_chance", "crit_damage", "accuracy", "lifesteal", "magic_crit_chance", "magic_crit_damage", "magic_shield_drain"],
    "shield": ["def", "magic_res", "max_hp", "m_shield", "thorns"],
    "tome": ["magic_atk", "max_mp", "m_shield", "mp_regen", "crit_chance", "crit_damage", "accuracy", "magic_crit_chance", "magic_crit_damage", "magic_shield_drain"],
    "tome2h": ["def", "max_hp", "max_mp", "hp_regen", "mp_regen", "atk_spd", "evasion_rating", "lifesteal",
               "armor_pen", "magic_atk", "magic_res", "thorns", "m_shield",
               "magic_crit_chance", "magic_crit_damage", "magic_shield_drain"],
    "boots": ["def", "evasion_rating", "hp_regen", "max_hp"],
    "belt": ["def", "evasion_rating", "max_hp", "hp_regen"],
    "robe": ["def", "magic_res", "max_hp", "hp_regen", "mp_regen", "thorns", "evasion_rating"],
    "helmet": ["def", "max_hp", "accuracy", "evasion_rating", "thorns"],
    "amulet": ["magic_atk", "max_mp", "mp_regen", "crit_chance", "crit_damage", "accuracy", "evasion_rating", "lifesteal", "m_shield", "thorns", "hp_regen", "magic_crit_chance", "magic_crit_damage", "magic_shield_drain"],
    "ring": ["atk", "magic_atk", "def", "magic_res", "max_hp", "max_mp", "hp_regen", "mp_regen",
             "crit_chance", "crit_damage", "accuracy", "evasion_rating", "lifesteal", "armor_pen", "thorns", "m_shield",
             "magic_crit_chance", "magic_crit_damage", "magic_shield_drain"]
}

#Множитель, на который умножаются статы предметов, чтобы не быть слишком большими
STAT_BASE_ITEM_MULTIPLIERS = {
    "atk": 0.1, "magic_atk": 0.1, "def": 0.2, "magic_res": 0.2,
    "max_hp": 1.0, "max_mp": 1.0, "hp_regen": 0.1, "mp_regen": 0.1,
    "armor_pen": 0.5, "crit_chance": 0.2, "crit_damage": 0.2,
    "accuracy": 0.5, "evasion_rating": 0.25,
    "atk_spd": 0.005, "lifesteal": 0.005, "thorns": 0.005, "m_shield": 1.0,
    "magic_crit_chance": 0.2, "magic_crit_damage": 0.2, "magic_shield_drain": 0.005
}

#Статы, которые отображаются как проценты и работают как проценты, чтобы подбирать немного другие формулы и давать игре понимание как с этим работать
PERCENT_STATS = {
    "crit_chance", "crit_damage", "atk_spd", "gold_mult", "lifesteal", "thorns",
    "accuracy", "evasion_rating", "magic_crit_chance", "magic_crit_damage", "magic_shield_drain"
}

#множество статов, для которых при генерации может случайно выпасть процентный тип бонуса (bonus_type = "percent")
STATS_WITH_PERCENT_OPTION = {
    "atk", "def", "max_hp", "max_mp", "magic_atk", "magic_res", "hp_regen", "mp_regen",
    "accuracy", "evasion_rating", "magic_crit_chance", "magic_crit_damage", "magic_shield_drain"
}

#В каком порядке отображаются слоты в инвентаре и других местах
EQUIP_ORDER = ["right_hand", "left_hand", "helmet", "robe", "belt", "boots", "amulet", "ring1", "ring2"]

PHYSICAL_WEAPON_TYPES = {"weapon1h_physical", "weapon2h_physical"}
MAGICAL_WEAPON_TYPES = {"weapon1h_magical", "weapon2h_magical"}

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
    "tome2h": ["Тяжёлый фолиант", "Гримуар силы", "Тяжёлая книга", "Фолиант древних"],
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



# ===================== КОНФИГ БАЛАНСА =====================
CONFIG = {
    "time_train": 10,
    "time_death": 600,
    "time_expedition": 1200,
    "time_shop_update": 300,
    "time_potion_update": 120,
    
    #Базовые статы для всех противников на 1 уровне угрозы
    "enemy_base_stats": {
        "hp": 10,
        "atk": 2.5,                 
        "def": 0,
        "m_shield": 5,
        "magic_atk": 1,
        "magic_res": 1,
        "atk_spd": 0.1,
        "accuracy": 10,
        "evasion_rating": 2,
        "crit_chance": 1.0,        
        "crit_damage": 150.0,
        "lifesteal": 0.05,
        "thorns": 0.5,             
        "magic_crit_chance": 0.5,   
        "magic_crit_damage": 150.0,
        "magic_shield_drain": 0.2,   
        "hp_regen": 2.0,      
        "mp_regen": 2.0,
        "effect_resistance": 0,        
    },
    #Прибавка к статам противника за каждый новый уровень угрозы, прибавка тоже общая
    "enemy_stat_scale": {
        "hp": 12,                 
        "atk": 2.5,               
        "def": 0.8,                
        "m_shield": 5,             
        "magic_atk": 1.0,          
        "magic_res": 0.4,          
        "atk_spd": 0.025,         
        "accuracy": 0.15,          
        "evasion_rating": 0.1,     
        "crit_chance": 0.3,        
        "crit_damage": 3.0,        
        "lifesteal": 0.05,         
        "thorns": 0.25,            
        "magic_crit_chance": 0.3,  
        "magic_crit_damage": 1.0,  
        "magic_shield_drain": 0.1,
        "hp_regen": 0.25,      
        "mp_regen": 0.25,
        "effect_resistance": 0.1
    }
}

# ===================== КЛАССЫ ВРАГОВ =====================
# Множитель статов у врагов, чтобы регулировать их прирост статов относительно их класса или убирать ненужные им в классе статы.
# ВАЖНЫЕ УСЛОВИЯ:
# thorns есть только у класса thorn
# lifesteal есть только у класса vampire
# mage "играет" только от магии и уклонения
ENEMY_CLASSES = {
    "warrior": {
        "name": "Воин",
        "atkType": "Physical",
        "mult": {
            "hp": 1.2,
            "atk": 1.0,
            "magic_atk": 0.2,
            "def": 1.2,
            "magic_res": 0.8,
            "atk_spd": 1.2,
            "accuracy": 1.0,
            "evasion_rating": 0.6,
            "crit_chance": 0.5,
            "crit_damage": 1.0,
            "magic_crit_chance": 0.2,
            "magic_crit_damage": 0.5,
            "lifesteal": 0.0,
            "thorns": 0.0,
            "hp_regen": 1.0,
            "mp_regen": 0.25,
            "magic_shield_drain": 0.0,
            "m_shield": 0.0,
            "effect_resistance": 0.2
        }
    },
    "mage": {
        "name": "Маг",
        "atkType": "Magic",
        "mult": {
            "hp": 0.25,
            "m_shield": 1.5,
            "magic_atk": 1.5,
            "magic_res": 1.2,
            "atk_spd": 0.8,
            "evasion_rating": 0.6,
            "magic_crit_chance": 2.0,
            "magic_crit_damage": 2.0,
            "magic_shield_drain": 0.5,
            "atk": 0.0,
            "def": 0.0,
            "accuracy": 0.0,
            "crit_chance": 0.0,
            "crit_damage": 0.0,
            "lifesteal": 0.0,
            "thorns": 0.0,
            "hp_regen": 0.0,
            "mp_regen": 2.0,
            "effect_resistance": 0.8
        }
    },
    "berserker": {
        "name": "Берсерк",
        "atkType": "Physical",
        "mult": {
            "hp": 0.5,
            "atk": 2.0,
            "magic_atk": 0.0,
            "def": 0.2,
            "magic_res": 0.2,
            "atk_spd": 1.25,
            "accuracy": 0.8,
            "evasion_rating": 0.2,
            "crit_chance": 0.25,
            "crit_damage": 0.5,
            "magic_crit_chance": 0.2,
            "magic_crit_damage": 0.5,
            "lifesteal": 0.0,
            "thorns": 0.0,
            "hp_regen": 0.5,
            "mp_regen": 0.25,
            "magic_shield_drain": 0.0,
            "m_shield": 0.0,
            "effect_resistance": 0.0
        }
    },
    "tank": {
        "name": "Танк",
        "atkType": "Physical",
        "mult": {
            "hp": 2.25,
            "atk": 1.0,
            "magic_atk": 0.0,
            "def": 2.0,
            "magic_res": 1.5,
            "atk_spd": 0.6,
            "accuracy": 0.8,
            "evasion_rating": 0.0,
            "crit_chance": 0.2,
            "crit_damage": 1.0,
            "magic_crit_chance": 0.1,
            "magic_crit_damage": 0.5,
            "lifesteal": 0.0,
            "thorns": 0.0,
            "hp_regen": 2.0,
            "mp_regen": 0.1,
            "magic_shield_drain": 0.0,
            "m_shield": 0.0,
            "effect_resistance": 0.5
        }
    },
    "assassin": {
        "name": "Ассасин",
        "atkType": "Physical",
        "mult": {
            "hp": 0.5,
            "atk": 1.5,
            "magic_atk": 0.0,
            "def": 0.2,
            "magic_res": 0.2,
            "atk_spd": 1.5,
            "accuracy": 1.25,
            "evasion_rating": 1.75,
            "crit_chance": 1.5,
            "crit_damage": 1.5,
            "lifesteal": 0.0,
            "thorns": 0.0,
            "hp_regen": 0.1,
            "mp_regen": 0.1,
            "magic_crit_chance": 0.2,
            "magic_crit_damage": 0.5,
            "magic_shield_drain": 0.0,
            "m_shield": 0.0,
            "effect_resistance": 0.1
        }
    },
    "vampire": {
        "name": "Вампир",
        "atkType": "Physical",
        "mult": {
            "hp": 1.0,
            "m_shield": 0.25,
            "atk": 1.0,
            "magic_atk": 0.25,
            "def": 0.5,
            "magic_res": 0.25,
            "atk_spd": 1.25,
            "accuracy": 1.0,
            "evasion_rating": 1.0,
            "crit_chance": 1.0,
            "crit_damage": 1.0,
            "lifesteal": 1.0,
            "thorns": 0.0,
            "magic_crit_chance": 0.5,
            "magic_crit_damage": 1.0,
            "magic_shield_drain": 0.25,
            "hp_regen": 0.25,
            "mp_regen": 0.5,
            "effect_resistance": 0.25
        }
    },
    "thorn": {
        "name": "Шипастый",
        "atkType": "Physical",
        "mult": {
            "hp": 2.5,
            "magic_atk": 0.0,
            "def": 1.5,
            "magic_res": 0.5,
            "thorns": 1.5,
            "atk": 0.0,
            "accuracy": 0.0,
            "evasion_rating": 0.0,
            "crit_chance": 0.0,
            "crit_damage": 0.0,
            "lifesteal": 0.0,
            "hp_regen": 0.5,
            "mp_regen": 0.1,
            "magic_crit_chance": 0.1,
            "magic_crit_damage": 0.1,
            "magic_shield_drain": 0.0,
            "m_shield": 0.0,
            "atk_spd": 0.0,
            "effect_resistance": 0.2
        }
    }
}

# ===================== КОНСТАНТЫ МАГИИ =====================
#Все типы эффектов у скиллов в игре
SPELL_EFFECT_TYPES = [
    "damage", "heal", "dot", "hot", "buff", "debuff", "shield",
    "time_stop", "mp_restore", "mp_burn"
]
TARGET_SELF = "self"
TARGET_ENEMY = "enemy"
#Закос на будущее, который сейчас не реализован
PASSIVE_TRIGGERS = ["on_hit", "on_attack", "low_hp", "low_mp", "on_spell_cast"]
BASE_SPELL_COOLDOWN = 5.0
MAX_EFFECTS_PER_SPELL = 5
#Шансы что сгенерируется несколько эффектов у скилла, 1 = 100%, на второй шанс 10%, на третий 1% и так до 5
EFFECT_CHANCE_CHAIN = [1.0, 0.1, 0.01, 0.001, 0.0001]

CANCELABLE_STATES = {"training", "expedition"}

# ===================== FSM СОСТОЯНИЯ =====================


class Form(StatesGroup):
    waiting_for_difficulty = State()
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
    # индекс в spell_inventory или в active_spells (для unequip)
    idx: int = 0
    slot: int = -1        # слот для экипировки (0-4) или -1
    
class SpellEffectCB(CallbackData, prefix="spelleff"):
    action: str          # "upgrade"
    spell_idx: int       # индекс в инвентаре или -1 для активного
    effect_idx: int      # индекс эффекта
    param: str = "value" # какой параметр улучшать: "value", "interval", "duration"
    slot: int = -1

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
        
async def update_leaderboard_cache(force=False):
    now = time.time()
    # Обновляем раз в час (3600 секунд)
    if force or now - leaderboard_cache['last_update'] > 3600:
        players = []
        async with db_lock:
            for uid, pdata in db['players'].items():
                difficulty = pdata.get('max_unlocked_difficulty', 1)
                name = pdata.get('name', 'Unknown')
                username = pdata.get('username')
                players.append((uid, name, username, difficulty))
        players.sort(key=lambda x: x[3], reverse=True)
        leaderboard_cache['full_sorted'] = players
        top_lines = []
        for i, (uid, name, username, diff) in enumerate(players[:25], 1):
            username_str = f"(@{username})" if username else ""
            top_lines.append(f"{i}. {name} {username_str} — Угроза {diff}")
        leaderboard_cache['top_25'] = "\n".join(top_lines)
        leaderboard_cache['last_update'] = now


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
        self.username = None
        self.gold = 100
        self.shop_assortment = []
        self.shop_last_update = 0
        self.potion_shop_assortment = []
        self.potion_shop_last_update = 0
        
        # Базовые (и начальные) статы (без учёта предметов и процентных зелий)
        self.base_stats = {
            "max_hp": 100,
            "max_mp": 20,
            "atk": 5,
            "def": 0,
            "magic_atk": 5,
            "magic_res": 0,
            "m_shield": 0,
            "crit_chance": 5.0,
            "crit_damage": 150.0,
            "accuracy": 10.0,
            "evasion_rating": 2.0,
            "atk_spd": 0.10,
            "hp_regen": 5.0,
            "mp_regen": 5.0,
            "gold_mult": 1.0,
            "luck": 1.0,
            "talent": 1.0,
            "lifesteal": 0.0,
            "armor_pen": 0,
            "thorns": 0.0,
            "adaptability": 1.0,
            "magic_efficiency": 0.0,
            "magic_crit_chance": 5.0,
            "magic_crit_damage": 150.0,
            "magic_shield_drain": 0.0,
            "effect_resistance": 0.0
        }
        
        self.training_order = list(self.base_stats.keys())

        # Текущие HP и MP
        self.hp = self.base_stats["max_hp"]
        self.mp = self.base_stats["max_mp"]

        # Процентные бонусы от зелий (для всех статов, кроме hp/mp)
        self.percent_bonus = {k: 0.0 for k in self.base_stats.keys()}

        # Счётчик тренировок
        self.stat_upgrades = {k: 0 for k in self.base_stats.keys()}

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
        self.current_difficulty = 1
        self.kills_on_max = 0

        self.last_regen_time = time.time()
    
    #Метод для миграции сохранений
    @classmethod
    def from_dict(cls, data):
        p = cls(data['uid'], data['name'])
        for k, v in data.items():
            if k not in ('uid', 'name'):
                setattr(p, k, v)
        return p

async def get_player(user_id, name=None, username=None):
    uid = str(user_id)
    async with db_lock:
        if uid not in db['players']:
            # Новый игрок – создаём с переданными данными
            player_dict = Player(uid, name or "Hero").__dict__
            player_dict['username'] = username
            db['players'][uid] = player_dict
            _save_db_unlocked()
        else:
            # Обновляем имя и username, только если они переданы и отличаются
            changed = False
            if name is not None and db['players'][uid].get('name') != name:
                db['players'][uid]['name'] = name
                changed = True
            if username is not None and db['players'][uid].get('username') != username:
                db['players'][uid]['username'] = username
                changed = True
            if changed:
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
        player.hp = min(t_stats['max_hp'], player.hp + (t_stats['hp_regen'] * mins))
        player.mp = min(t_stats['max_mp'], player.mp + (t_stats['mp_regen'] * mins))
        player.last_regen_time = now - (delta % 60)
        await save_player(player)

async def check_and_complete_state(player):
    """Проверяет, не истекло ли состояние игрока, и если да – завершает его."""
    now = time.time()
    if player.state != 'idle' and now >= player.state_end_time:
        if player.state == 'dead':
            t_stats = get_total_stats(player)
            player.hp = t_stats['max_hp']
            player.state = 'idle'
            try:
                await bot.send_message(player.uid, "⚡️ Вы воскресли и готовы к новым битвам!", reply_markup=main_menu_kbd())
            except:
                pass
        elif player.state == 'training':
            stat = player.training_stat
            base_increment = TRAINING_INCREMENTS.get(stat, 0.01)
            t_stats = get_total_stats(player)
            total_adapt = t_stats['adaptability']
            if stat == 'adaptability':
                increment = base_increment
            else:
                increment = base_increment * total_adapt
            player.base_stats[stat] += increment
            player.stat_upgrades[stat] += 1
            if stat in player.training_order:
                player.training_order.remove(stat)
                player.training_order.insert(0, stat)
            player.state = 'idle'
            player.training_stat = None
            try:
                await bot.send_message(player.uid,
                    f"🏋️ Тренировка завершена!\n\nХарактеристика <b>{STAT_RU.get(stat, stat)}</b> улучшена.",
                    reply_markup=training_complete_kbd(stat))
            except:
                pass
        elif player.state == 'expedition':
            t_stats = get_total_stats(player)
            base_gold = GOLD_PER_STAGE * 20 * player.max_unlocked_difficulty
            gold_found = int(base_gold * random.uniform(0.1, 3) * t_stats["gold_mult"])
            player.gold += gold_found
            msg = f"🧭 Экспедиция завершена!\nВы нашли: 💰 {gold_found} золота."
            gold_mult = 0.4
            items_found = 0
            while random.random() < gold_mult and items_found < 3:
                item_type = random.choice(ITEM_TYPES)
                rarity = max(1, player.max_unlocked_difficulty * t_stats["gold_mult"])
                item = generate_item(item_type, rarity)
                if len(player.inventory) < player.inv_slots:
                    player.inventory.append(item)
                    items_found += 1
                    msg += f"\n📦 Найден предмет: {item['name']}"
                else:
                    msg += "\n📦 Инвентарь полон, предмет потерян!"
                    break
                gold_mult *= 0.5
            player.state = 'idle'
            try:
                await bot.send_message(player.uid, msg, reply_markup=main_menu_kbd())
            except:
                pass
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
                        t_stats = get_total_stats(player)
                        player.hp = t_stats['max_hp']
                        player.state = 'idle'
                        try:
                            await bot.send_message(uid,
                            "⚡️ Вы воскресли и готовы к новым битвам!",
                            reply_markup=main_menu_kbd())
                        except:
                            pass

                    elif player.state == 'training':
                        stat = player.training_stat
                        base_increment = TRAINING_INCREMENTS.get(stat, 0.01)
                        t_stats = get_total_stats(player)
                        total_adapt = t_stats['adaptability']
                        if stat == 'adaptability':
                            increment = base_increment
                        else:
                            increment = base_increment * total_adapt
                        player.base_stats[stat] += increment
                        player.stat_upgrades[stat] += 1
                        if stat in player.training_order:
                            player.training_order.remove(stat)
                            player.training_order.insert(0, stat)
                        player.state = 'idle'
                        player.training_stat = None
                        try:
                            await bot.send_message(uid,
                                f"🏋️ Тренировка завершена!\n\nХарактеристика <b>{STAT_RU.get(stat, stat)}</b> улучшена.",
                                reply_markup=training_complete_kbd(stat))
                        except:
                            pass

                    elif player.state == 'expedition':
                        t_stats = get_total_stats(player)
                        base_gold = GOLD_PER_STAGE * 20 * player.max_unlocked_difficulty
                        gold_found = int(base_gold * random.uniform(0.1, 3) * t_stats["gold_mult"])
                        player.gold += gold_found
                        msg = f"🧭 Экспедиция завершена!\nВы нашли: 💰 {gold_found} золота."

                        gold_mult = 0.4
                        items_found = 0
                        while random.random() < gold_mult and items_found < 3:
                            item_type = random.choice(ITEM_TYPES)
                            rarity = max(1, player.max_unlocked_difficulty * t_stats["gold_mult"])
                            item = generate_item(item_type, rarity)
                            if len(player.inventory) < player.inv_slots:
                                player.inventory.append(item)
                                items_found += 1
                                msg += f"\n📦 Найден предмет: {item['name']}"
                            else:
                                msg += "\n📦 Инвентарь полон, предмет потерян!"
                                break
                            gold_mult *= 0.5

                        player.state = 'idle'
                        try:
                            await bot.send_message(uid, msg, reply_markup=main_menu_kbd())
                        except:
                            pass

                    db['players'][uid] = player.__dict__
                    changed = True

        if changed:
            _save_db_unlocked()

async def leaderboard_updater():
    while True:
        now = time.time()
        next_hour = (now // 3600 + 1) * 3600
        sleep_seconds = next_hour - now
        await asyncio.sleep(sleep_seconds)
        await update_leaderboard_cache(force=True)

# ===================== ГЕНЕРАЦИЯ ПРЕДМЕТОВ =====================

def generate_item_name(item_type):
    prefix = random.choice(PREFIXES)
    noun = random.choice(NOUNS.get(item_type, ["Предмет"]))
    suffix = random.choice(SUFFIXES)
    return f"{prefix} {noun} {suffix}"

def generate_item(item_type, rarity):
    name = generate_item_name(item_type)

    # Максимальное количество статов для данного типа предмета (кольца могут иметь больше)
    max_stats = MAX_STATS_PER_ITEM.get(item_type, MAX_STATS_COUNT)
    stats_count = 1  # минимум один стат

    # Гарантированные статы от целых сотен редкости (не более MAX_GUARANTEED_STATS и не более max_stats-1)
    total_hundreds = int(rarity // 100)
    guaranteed_extra = min(MAX_GUARANTEED_STATS, max_stats - 1, total_hundreds)
    stats_count += guaranteed_extra
    remaining_rarity = rarity - total_hundreds * 100  # остаток для шанса (всегда < 100)

    # Добавляем случайные статы с убывающей вероятностью, начиная с остатка
    extra_chance = 0.5 + remaining_rarity / 100.0  # от 0 до 1
    while stats_count < max_stats and random.random() < extra_chance:
        stats_count += 1
        extra_chance *= 0.5  # шанс на следующий стат падает вдвое

    allowed = ITEM_ALLOWED_STATS.get(item_type, [])
    if not allowed:
        allowed = list(STAT_RU.keys())

    # Определяем гарантированный стат для оружия
    guaranteed_stat = None
    if item_type in PHYSICAL_WEAPON_TYPES:
        guaranteed_stat = 'atk'
    elif item_type in MAGICAL_WEAPON_TYPES:
        guaranteed_stat = 'magic_atk'

    # Ограничиваем stats_count количеством доступных статов
    max_available = len(allowed)
    if stats_count > max_available:
        stats_count = max_available

    # Формируем список выбранных статов
    if guaranteed_stat and guaranteed_stat in allowed:
        # Убираем гарантированный из списка для выбора остальных
        other_allowed = [s for s in allowed if s != guaranteed_stat]
        # Количество остальных статов (не считая гарантированного)
        num_others = min(stats_count - 1, len(other_allowed))
        if num_others > 0:
            other_stats = random.sample(other_allowed, num_others)
        else:
            other_stats = []
        chosen_stats = [guaranteed_stat] + other_stats
    else:
        # Для не-оружия или если гарантированный по какой-то причине отсутствует
        chosen_stats = random.sample(allowed, min(stats_count, len(allowed)))

    item_stats = {}

    stat_mult = STAT_BASE_ITEM_MULTIPLIERS

    base_price = 0
    for stat in chosen_stats:
        #is_percent = stat in PERCENT_STATS - Я не знаю надо ли это писать с методом ниже
        
        stat_data = generate_single_stat(stat, item_type, rarity)
        item_stats[stat] = stat_data
        base_price += int(stat_data["base"] * (100 if stat in PERCENT_STATS else 10))

    return {
        "id": "i_" + str(time.time()).replace(".", "") + str(random.randint(10, 99)),
        "name": name,
        "item_type": item_type,
        "stats": item_stats,
        "rarity": rarity,
        "dust": 0,
        "battle_count": 0,
        "sell_price": max(10, int(base_price * 0.25))
    }

def generate_single_stat(stat: str, item_type: str, rarity: float):
    stat_mult = STAT_BASE_ITEM_MULTIPLIERS
    mult = stat_mult.get(stat, 1.0)

    raw = (rarity * 0.25 * random.uniform(0.8, 1.2)) * mult
    if "weapon2h" in item_type:
        raw *= TWOHAND_MULTIPLIER
    elif item_type == "tome2h":
        raw *= TOME_MULTIPLIER

    base_val = round(raw, 3)
    factor = raw / rarity if rarity > 0 else 1.0

    bonus_type = "flat"
    if stat in STATS_WITH_PERCENT_OPTION:
        bonus_type = random.choice(["flat", "percent"])

    upgrade_price_mult = random.uniform(0.25, 2.5)

    return {
        "base": base_val,
        "current": base_val,
        "upgrades": 0,
        "bonus_type": bonus_type,
        "upgrade_price_mult": upgrade_price_mult,
        "factor": factor
    }

def generate_potion(difficulty):
    potion_stats = [s for s in STAT_RU.keys() if s not in ["hp", "mp"]]
    all_potion_stats = potion_stats
    stat = random.choice(all_potion_stats)

    # Теперь адаптивность тоже может быть процентной
    potion_type = random.choice(["flat", "percent"])
    is_percent = potion_type == "percent"

    # Генерация значения эффекта
    if stat == "adaptability":
        if is_percent:
            # Процентное зелье адаптивности: от 0.1% до 0.5%
            value = round(random.uniform(0.1, 0.2), 1)
        else:
            # Плоское зелье адаптивности: от 0.001 до 0.005
            value = round(random.uniform(0.001, 0.005), 3)
    else:
        if is_percent:
            # Процентные зелья для остальных статов: от 0.1% до 1.0%
            value = round(random.uniform(0.1, 1.0), 1)
        else:
            # Аддитивные зелья: эквивалент 1–3 тренировок
            base_inc = TRAINING_INCREMENTS.get(stat, 0.01)
            raw_value = random.uniform(1, 3) * base_inc
            value = round(raw_value, 2)

    # Цена зависит от сложности (чем выше угроза, тем дороже)
    base_price = int(GOLD_PER_STAGE * 5 * difficulty * random.uniform(0.8, 1.2))
    price = max(50, base_price)

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
        "target": target if target else (TARGET_ENEMY if effect_type in ["damage", "dot", "debuff", "time_stop", "mp_burn"] else TARGET_SELF),
        "base_value": 0,
        "duration": 0,          # будет использоваться только для time_stop
        "interval": 0,
        "chance": 1.0,
        "stat": None
    }
    if effect_type in ["damage", "heal", "shield", "mp_restore", "mp_burn"]:
        if effect_type == "heal":
            base = power * random.uniform(0.2, 1.0)
        else:
            base = power * random.uniform(0.5, 1.5)
        effect["base_value"] = round(max(1.0, base), 1) if effect_type in ["shield", "mp_restore", "mp_burn"] else round(base, 1)
    elif effect_type in ["dot", "hot"]:
        base = power * random.uniform(0.2, 0.5)          # уменьшено
        effect["base_value"] = round(base, 1)
        effect["interval"] = random.choice([1, 2, 3])
    elif effect_type in ["buff", "debuff"]:
        stat = random.choice(["atk", "def", "magic_atk", "magic_res", "atk_spd",
                             "crit_chance", "crit_damage", "magic_crit_chance", "magic_crit_damage"])
        base = power * random.uniform(0.02, 0.1)         # 2% – 10%
        effect["stat"] = stat
        effect["base_value"] = round(base, 3)
    elif effect_type == "time_stop":
        effect["duration"] = random.uniform(0.1, 0.3)
    return effect


def generate_spell(enemy_class_key, power, max_mp, force_min_effects=1):
    prefixes = ["Огненный", "Ледяной", "Теневой", "Святой",
                "Древний", "Проклятый", "Молниеносный", "Кровавый"]
    nouns = ["Шар", "Взрыв", "Копьё", "Сфера", "Поток",
             "Клинок", "Щит", "Благословение", "Проклятие"]
    suffix = random.choice(
        ["", " Мага", " Тьмы", " Света", " Разрушения", " Защиты"])
    name = f"{random.choice(prefixes)} {random.choice(nouns)}{suffix}"

    possible_effects = ["damage", "heal", "dot", "hot", "buff",
                        "debuff", "shield", "time_stop", "mp_restore", "mp_burn"]
    effects = []
    chance_index = 0
    while chance_index < MAX_EFFECTS_PER_SPELL and (len(effects) < force_min_effects or random.random() < EFFECT_CHANCE_CHAIN[chance_index]):
        effect_type = random.choice(possible_effects)
        target = TARGET_ENEMY if effect_type in [
            "damage", "dot", "debuff", "time_stop", "mp_burn"] else TARGET_SELF
        eff = generate_effect(effect_type, power, target)
        effects.append(eff)
        chance_index += 1
        if chance_index == 1 and force_min_effects == 1:
            continue

    base_cooldown = BASE_SPELL_COOLDOWN * random.uniform(1, 4)
    # Стоимость маны — процент от максимальной маны врага (20–60%)
    mp_cost = int(max_mp * random.uniform(0.2, 0.6))
    is_passive = False  # для врагов всегда активные заклинания
    trigger = None

    spell = {
        "id": "s_" + str(time.time()).replace(".", "") + str(random.randint(10, 99)),
        "name": name,
        "effects": effects,
        "mp_cost": mp_cost,
        "base_mp_cost": mp_cost,
        "base_cooldown": base_cooldown,
        "current_cooldown": 0,
        "cooldown_upgrades": 0,
        "arcane": 0,
        "arcane_progress": 0,
        "is_passive": is_passive,
        "trigger": trigger,
        "upgrades": 0
    }
    return spell

# ===================== ГЕНЕРАЦИЯ ВРАГА =====================

def generate_enemy(difficulty):
    # Общий множитель силы врага (от 0.5 до 2.0)
    strength_mult = random.uniform(0.5, 2.0)
    
    def variance(): return random.uniform(0.8, 1.2)  # индивидуальный разброс по статам
    class_key = random.choice(list(ENEMY_CLASSES.keys()))
    enemy_class = ENEMY_CLASSES[class_key]
    class_mult = enemy_class["mult"]
    atk_type = enemy_class.get("atkType", "Physical")

    e_stats = {}
    for stat in ["hp", "atk", "def", "magic_atk", "magic_res", "accuracy", "evasion_rating",
                 "crit_chance", "crit_damage", "lifesteal", "thorns", "hp_regen", "mp_regen",
                 "magic_crit_chance", "magic_crit_damage", "magic_shield_drain", "m_shield", "effect_resistance"]:
        base = CONFIG["enemy_base_stats"].get(stat, 0)
        scale = CONFIG["enemy_stat_scale"].get(stat, 0)
        # Применяем: база + сложность*масштаб, умножаем на классовый множитель, на общий множитель силы и на индивидуальную вариацию
        val = (base + difficulty * scale) * class_mult.get(stat, 1.0) * strength_mult * variance()
        if stat in ["hp", "atk", "def", "magic_atk", "magic_res", "magic_crit_chance", "magic_crit_damage"]:
            e_stats[stat] = max(0, int(val)) if stat not in ["magic_crit_chance", "magic_crit_damage"] else max(0, val)
        else:
            e_stats[stat] = max(0, val)

    e_stats["atk_spd"] = max(0.00, (CONFIG["enemy_base_stats"]["atk_spd"] + difficulty * CONFIG["enemy_stat_scale"]["atk_spd"]) * class_mult.get("atk_spd", 1.0) * strength_mult * variance())
    e_stats["max_mp"] = max(0, int(difficulty * 15))
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
        spell = generate_spell(class_key, difficulty, e_stats["max_mp"], force_min_effects=1)
        spells.append(spell)

    # Множитель для золота теперь не нужен, оставляем для совместимости, но не используем
    norm_hp = CONFIG["enemy_base_stats"]["hp"] + (difficulty * CONFIG["enemy_stat_scale"]["hp"])
    power_multiplier = e_stats["hp"] / (norm_hp if norm_hp > 0 else 1)  # больше не используется

    names = {
        "warrior": ["Воин", "Рыцарь", "Латинец", "Паладин"],
        "mage": ["Маг", "Чародей", "Волшебник", "Заклинатель"],
        "berserker": ["Берсерк", "Дикарь", "Варвар"],
        "tank": ["Страж", "Защитник", "Гладиатор"],
        "assassin": ["Ассасин", "Убийца", "Ниндзя", "Разбойник"],
        "vampire": ["Вампир", "Кровопийца", "Носферату", "Комар"],
        "thorn": ["Шипастый", "Колючий", "Остряк"]
    }
    name_choices = names.get(class_key, ["Монстр"])
    name = f"{random.choice(name_choices)} {random.choice(['Слабый', 'Обычный', 'Свирепый', 'Древний', 'Элитный', 'Кошмарный'])}"

    return {
        "name": name,
        "class": enemy_class["name"],
        "class_key": class_key,
        "atk_type": atk_type,
        "difficulty": difficulty,
        "max_hp": e_stats["hp"],
        "hp": e_stats["hp"],
        "max_mp": e_stats["max_mp"],
        "mp": e_stats["mp"],
        "m_shield": e_stats["m_shield"],
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
        "effect_resistance": e_stats["effect_resistance"],
        "hp_regen": e_stats["hp_regen"],
        "mp_regen": e_stats["mp_regen"],
        "magic_crit_chance": e_stats["magic_crit_chance"],
        "magic_crit_damage": e_stats["magic_crit_damage"],
        "magic_shield_drain": e_stats["magic_shield_drain"],
        "spells": spells,
        "power_mult": power_multiplier,  # оставлено для обратной совместимости, но не используется в золоте
        "strength_mult": strength_mult   # новый множитель силы
    }

def get_evasion_chance(acc, eva):
    if acc+eva == 0:
        return 0
    return eva/(acc+eva)*100

# ===================== ОБНОВЛЕНИЕ МАГАЗИНОВ =====================


async def update_shop(player, force=False):
    now = time.time()
    if force or now - player.shop_last_update > CONFIG["time_shop_update"]:
        t_stats = get_total_stats(player)
        player.shop_assortment = []
        rarity = (player.max_unlocked_difficulty + 5.0) * t_stats["luck"]
        for _ in range(5):
            item_type = random.choice(ITEM_TYPES)
            item = generate_item(item_type, rarity)
            price = int(SHOP_BASE_PRICE * player.max_unlocked_difficulty * random.uniform(0.8, 1.2))
            player.shop_assortment.append(
                {"item": item, "price": price, "sold": False})
        player.shop_last_update = now
        await save_player(player)


async def update_potion_shop(player, force=False):
    now = time.time()
    if force or now - player.potion_shop_last_update > CONFIG["time_potion_update"]:
        player.potion_shop_assortment = []
        for _ in range(10):
            player.potion_shop_assortment.append(
                {"potion": generate_potion(player.max_unlocked_difficulty), "sold": False})
        player.potion_shop_last_update = now
        await save_player(player)

# ===================== РАСЧЁТ СУММАРНЫХ СТАТОВ =====================

def get_total_stats(player):
    total = player.base_stats.copy()
    flat_items = {k: 0.0 for k in total.keys()}
    percent_items = {k: 0.0 for k in total.keys()}

    for slot, item in player.equip.items():
        if item:
            for stat_name, stat_data in item["stats"].items():
                if stat_name in total:
                    current_val = stat_data['base'] * (stat_data['upgrades'] + 1)
                    if stat_data.get('bonus_type') == 'percent':
                        percent_items[stat_name] += current_val
                    else:
                        flat_items[stat_name] += current_val

    percent_potions = player.percent_bonus.copy()

    for stat in total.keys():
        base = total[stat]
        flat = flat_items.get(stat, 0)
        total_percent = percent_items.get(stat, 0) + percent_potions.get(stat, 0)
        total[stat] = (base + flat) * (1 + total_percent / 100.0)

    total['hp'] = min(player.hp, total['max_hp'])
    total['mp'] = min(player.mp, total['max_mp'])

    return total

# ===================== НОВАЯ СИМУЛЯЦИЯ БОЯ =====================

async def run_combat_simulation(player, enemy):
    loop = asyncio.get_event_loop()
    # Запускаем синхронную функцию в отдельном потоке
    return await loop.run_in_executor(None, simulate_combat_realtime, player, enemy)

def simulate_combat_realtime(player, enemy):
    p_stats = get_total_stats(player)
    e_stats = enemy.copy()

    current_shield = p_stats['m_shield']
    enemy_shield = e_stats.get('m_shield', 0)

    p_effects = []  # эффекты на игроке (только dot/hot)
    e_effects = []  # эффекты на враге (только dot/hot)

    # Множители от баффов/дебаффов (длятся весь бой)
    p_multipliers = {stat: 1.0 for stat in ["atk", "def", "magic_atk", "magic_res", "atk_spd",
                                             "crit_chance", "crit_damage", "magic_crit_chance", "magic_crit_damage"]}
    e_multipliers = p_multipliers.copy()

    # Перезарядки заклинаний игрока (время готовности)
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
    has_free_hand = player.equip.get('right_hand') is None or player.equip.get('left_hand') is None

    # Вспомогательная функция для форматирования состояния
    def status_str(target_stats, shield, is_player):
        hp = max(0, target_stats['hp'])
        max_hp = target_stats['max_hp']
        shield_part = f" 🪬 {shield:.1f}" if shield > 0 else ""
        return f"| ❤️ {hp:.1f}/{max_hp:.1f}{shield_part}"
    
    def apply_crit_damage(damage, crit_chance, crit_damage, emoji):
        """Применяет механику мульти-критов.
        Возвращает (новый_урон, строка_с_описанием)"""
        if crit_chance <= 0:
            return damage, ""
        crit_mult = crit_damage / 100.0
        guaranteed = int(crit_chance // 100)          # целые криты
        extra = crit_chance % 100                     # остаточный шанс
        total_mult = crit_mult ** guaranteed
        crit_count = guaranteed
        if random.random() * 100 < extra:
            total_mult *= crit_mult
            crit_count += 1
        new_damage = damage * total_mult
        if crit_count == 0:
            return new_damage, ""
        elif crit_count == 1:
            return new_damage, f" {emoji} КРИТ!"
        else:
            return new_damage, f" {emoji} КРИТ x{crit_count}!"
        
    log = [
        f"⚔️ <b>Бой начался!</b>\nУгроза: {enemy['difficulty']}",
        f"👤 <b>Вы:</b> ❤️ {p_stats['hp']:.1f}/{p_stats['max_hp']:.1f} | 🪬 {p_stats['m_shield']:.1f} | 💧 {p_stats['mp']:.1f}/{p_stats['max_mp']:.1f}",
        f"😡 <b>[{enemy.get('class', '')}] {enemy['name']}</b>: ❤️ {enemy['hp']:.1f}/{enemy['max_hp']:.1f}",
        f"🎯 Ваш уклон {get_evasion_chance(e_stats['accuracy'], p_stats['evasion_rating']):.1f}% | Уклон врага: {get_evasion_chance(p_stats['accuracy'], e_stats['evasion_rating']):.1f}%\n",
    ]

    t = 0.0
    max_time = 300.0

    p_action_interval = 1.0 / max(0.05, p_stats["atk_spd"])
    e_action_interval = 1.0 / max(0.05, e_stats["atk_spd"])

    p_next_action = p_action_interval
    e_next_action = e_action_interval

    def apply_regen(target_stats, delta):
        target_stats["hp"] = min(target_stats["max_hp"], target_stats["hp"] + target_stats["hp_regen"] / 60.0 * delta)
        target_stats["mp"] = min(target_stats["max_mp"], target_stats["mp"] + target_stats["mp_regen"] / 60.0 * delta)

    def apply_effect(effect, caster_stats, target_stats, is_player_caster, target_effects_list):
        nonlocal current_shield, enemy_shield, t, p_multipliers, e_multipliers
        msg = ""
        eff_type = effect["type"]
        base = effect["base_value"]
        duration = effect.get("duration", 0)
        interval = effect.get("interval", 0)
        stat = effect.get("stat")
        target = effect.get("target", TARGET_ENEMY)

        if eff_type in ["damage", "mp_burn"]:
            dmg = base + caster_stats.get('magic_atk', 0)
            if random.random()*100 < caster_stats.get("magic_crit_chance", 0):
                dmg *= caster_stats.get("magic_crit_damage", 200)/100.0
            res = target_stats.get("magic_res", 0)
            dmg = max(0, dmg - res)

            if eff_type == "damage":
                remaining_dmg = dmg
                absorbed = 0.0
                if target_stats is e_stats:
                    if enemy_shield > 0:
                        absorbed = min(remaining_dmg, enemy_shield)
                        enemy_shield -= absorbed
                        remaining_dmg -= absorbed
                    if remaining_dmg > 0:
                        target_stats["hp"] -= remaining_dmg
                else:
                    if current_shield > 0:
                        absorbed = min(remaining_dmg, current_shield)
                        current_shield -= absorbed
                        remaining_dmg -= absorbed
                    if remaining_dmg > 0:
                        target_stats["hp"] -= remaining_dmg

                drain = caster_stats.get("magic_shield_drain", 0)
                if drain > 0:
                    shield_gain = dmg * (drain/100.0)
                    if is_player_caster:
                        current_shield = min(current_shield + shield_gain, p_stats["max_hp"]*0.5)
                    else:
                        enemy_shield = min(enemy_shield + shield_gain, e_stats["max_hp"]*0.5)
                    msg += f"🔋 +{fmt_float(shield_gain, 4)} щита "

                if target_stats is e_stats:
                    msg += f"🔥 Вы нанесли {dmg:.1f} урона"
                    if absorbed > 0:
                        msg += f" (поглощено {absorbed:.1f})"
                    msg += " " + status_str(target_stats, enemy_shield, False)
                else:
                    msg += f"🔥 Вам нанесли {dmg:.1f} урона"
                    if absorbed > 0:
                        msg += f" (поглощено {absorbed:.1f})"
                    msg += " " + status_str(target_stats, current_shield, True)
            else:  # mp_burn
                if "max_mp" in target_stats:
                    target_stats["mp"] = max(0, target_stats["mp"] - dmg)
                    if target_stats is e_stats:
                        msg += f"💧 Вы сожгли {dmg:.1f} маны"
                    else:
                        msg += f"💧 Вы потеряли {dmg:.1f} маны"

        elif eff_type in ["heal", "mp_restore"]:
            if eff_type == "heal":
                target_stats["hp"] = min(target_stats["max_hp"], target_stats["hp"] + base)
                if target_stats is e_stats:
                    msg += f"💚 +{base:.1f} HP врагу"
                else:
                    msg += f"💚 +{base:.1f} HP"
                msg += " " + status_str(target_stats, enemy_shield if target_stats is e_stats else current_shield, target_stats is p_stats)
            else:
                if "max_mp" in target_stats:
                    target_stats["mp"] = min(target_stats["max_mp"], target_stats["mp"] + base)
                    if target_stats is e_stats:
                        msg += f"💧 +{base:.1f} MP врагу"
                    else:
                        msg += f"💧 +{base:.1f} MP"

        elif eff_type in ["dot", "hot"]:
            effect_copy = effect.copy()
            effect_copy["next_tick"] = t + interval
            # Если эффект накладывается на игрока, применяем сопротивление игрока
            if target_stats is p_stats:
                res = p_stats.get('effect_resistance', 0.0)
                factor = 99 / (res + 99)
                effect_copy["interval"] = effect_copy.get("interval", interval) * factor
                effect_copy["next_tick"] = t + effect_copy["interval"]
            # Если эффект накладывается на врага, применяем сопротивление врага
            elif target_stats is e_stats:
                res = e_stats.get('effect_resistance', 0.0)
                factor = 99 / (res + 99)
                effect_copy["interval"] = effect_copy.get("interval", interval) * factor
                effect_copy["next_tick"] = t + effect_copy["interval"]
            target_effects_list.append(effect_copy)
            msg += f"✨ Эффект {STAT_RU.get(stat, eff_type)}"

        elif eff_type == "buff":
            mult = 1 + base
            if target_stats is p_stats:
                p_multipliers[stat] *= mult
                msg += f"✨ {STAT_RU.get(stat, stat)} увеличен в {mult:.3f} раз (навсегда)"
            else:
                e_multipliers[stat] *= mult
                msg += f"✨ Враг: {STAT_RU.get(stat, stat)} увеличен в {mult:.3f} раз (навсегда)"

        elif eff_type == "debuff":
            mult = 1 - base
            if target_stats is p_stats:
                p_multipliers[stat] *= mult
                msg += f"✨ Ваш стат {STAT_RU.get(stat, stat)} уменьшен в {fmt_float(mult, 5)}"
            else:
                e_multipliers[stat] *= mult
                msg += f"✨ Вражеский стат {STAT_RU.get(stat, stat)} уменьшен в {fmt_float(mult, 5)}"

        elif eff_type == "time_stop":
            effect_copy = effect.copy()
            # Если накладывается на игрока, применяем сопротивление игрока
            if target_stats is p_stats:
                res = p_stats.get('effect_resistance', 0.0)
                factor = 99 / (res + 99)
                effect_copy["duration"] = duration * factor
            # Если накладывается на врага, применяем сопротивление врага
            elif target_stats is e_stats:
                res = e_stats.get('effect_resistance', 0.0)
                factor = 99 / (res + 99)
                effect_copy["duration"] = duration * factor
            effect_copy["end_time"] = t + effect_copy["duration"]
            target_effects_list.append(effect_copy)
            msg += f"⏸ Остановка времени на {effect_copy['duration']}с"

        elif eff_type == "shield":
            if is_player_caster:
                current_shield = min(current_shield + base, p_stats["max_hp"]*0.5)
                msg += f"🪬 Вы получили +{base:.1f} щита"
                msg += " " + status_str(p_stats, current_shield, True)
            else:
                enemy_shield = min(enemy_shield + base, e_stats["max_hp"]*0.5)
                msg += f"🪬 Враг получил +{base:.1f} щита"
                msg += " " + status_str(e_stats, enemy_shield, False)

        return msg

    def process_effects(effects_list, target_stats, is_player_target):
        nonlocal current_shield, enemy_shield, t, log
        for eff in effects_list[:]:
            eff_type = eff["type"]
            if "next_tick" in eff:  # периодический (dot/hot)
                if t >= eff["next_tick"]:
                    if eff_type == "dot":
                        dmg = eff["base_value"]
                        remaining_dmg = dmg
                        if is_player_target:
                            if current_shield > 0:
                                absorbed = min(remaining_dmg, current_shield)
                                current_shield -= absorbed
                                remaining_dmg -= absorbed
                            if remaining_dmg > 0:
                                target_stats["hp"] -= remaining_dmg
                            log.append(f"[{fmt_float(t,6)}с] 🌡 Вы получили {fmt_float(dmg, 4)} урона от горения {status_str(target_stats, current_shield, True)}")
                        else:
                            if enemy_shield > 0:
                                absorbed = min(remaining_dmg, enemy_shield)
                                enemy_shield -= absorbed
                                remaining_dmg -= absorbed
                            if remaining_dmg > 0:
                                target_stats["hp"] -= remaining_dmg
                            log.append(f"[{fmt_float(t,6)}с] 🌡 Враг получил {fmt_float(dmg, 4)} урона от горения {status_str(target_stats, enemy_shield, False)}")
                    elif eff_type == "hot":
                        heal = eff["base_value"]
                        target_stats["hp"] = min(target_stats["max_hp"], target_stats["hp"] + heal)
                        if is_player_target:
                            log.append(f"[{fmt_float(t,6)}с] 💚 Вы восстановили {heal:.1f} HP {status_str(target_stats, current_shield, True)}")
                        else:
                            log.append(f"[{fmt_float(t,6)}с] 💚 Враг восстановил {heal:.1f} HP {status_str(target_stats, enemy_shield, False)}")
                    eff["next_tick"] += eff["interval"]
                    # не удаляем, так как бесконечно
            elif "end_time" in eff:  # эффект с окончанием (time_stop)
                if t >= eff["end_time"]:
                    if eff["type"] == "time_stop":
                        log.append(f"[{fmt_float(t,6)}с] ⏸ Время возобновилось")
                    effects_list.remove(eff)

    # Основной цикл событий
    while p_stats["hp"] > 0 and e_stats["hp"] > 0 and t < max_time:
        times = []
        if p_next_action > t + 1e-9:
            times.append(p_next_action)
        if e_next_action > t + 1e-9:
            times.append(e_next_action)
        for eff in p_effects:
            if "next_tick" in eff and eff["next_tick"] > t + 1e-9:
                times.append(eff["next_tick"])
            if "end_time" in eff and eff["end_time"] > t + 1e-9:
                times.append(eff["end_time"])
        for eff in e_effects:
            if "next_tick" in eff and eff["next_tick"] > t + 1e-9:
                times.append(eff["next_tick"])
            if "end_time" in eff and eff["end_time"] > t + 1e-9:
                times.append(eff["end_time"])

        if not times:
            break

        next_t = min(times)
        if next_t >= max_time:
            t = max_time
            break
        delta = next_t - t
        t = next_t

        apply_regen(p_stats, delta)
        apply_regen(e_stats, delta)

        player_stopped = any(eff['type'] == 'time_stop' for eff in p_effects)
        enemy_stopped = any(eff['type'] == 'time_stop' for eff in e_effects)

        process_effects(p_effects, p_stats, True)
        process_effects(e_effects, e_stats, False)

        player_stopped = any(eff['type'] == 'time_stop' for eff in p_effects)
        enemy_stopped = any(eff['type'] == 'time_stop' for eff in e_effects)

        # Действие игрока
        if abs(t - p_next_action) < 1e-9:
            if not player_stopped:
                p_next_action = t + p_action_interval
                spell_used = False
                for i, spell in enumerate(player.active_spells):
                    if spell and not spell.get('is_passive', False):
                        magic_eff = p_stats.get('magic_efficiency', 0.0)
                        cost_mult = 99 / (magic_eff + 99)   # множитель стоимости: 1 при eff=0, стремится к 0
                        actual_cost = max(1, int(spell["mp_cost"] * cost_mult + 0.5))

                        if spell_cooldowns[i] <= t and p_stats["mp"] >= actual_cost:
                            p_stats["mp"] -= actual_cost
                            
                            talent = p_stats.get('talent', 1.0)
                            cd = spell["base_cooldown"] * ((1 - 0.1 * talent) ** spell.get("cooldown_upgrades", 0))
                            spell_cooldowns[i] = t + cd

                            # Накопление аркан
                            spell['arcane_progress'] = spell.get('arcane_progress', 0) + 1
                            if spell['arcane_progress'] >= 20:
                                spell['arcane'] = spell.get('arcane', 0) + 1
                                spell['arcane_progress'] -= 20

                            msg_lines = [f"[{fmt_float(t,6)}с] Вы использовали ✨ {spell['name']}:"]
                            for eff in spell["effects"]:
                                effect_msg = ""
                                if eff["target"] == TARGET_ENEMY:
                                    effect_msg = apply_effect(eff, p_stats, e_stats, True, e_effects)
                                else:
                                    effect_msg = apply_effect(eff, p_stats, p_stats, True, p_effects)
                                if effect_msg:
                                    msg_lines.append(f"  • {effect_msg}")
                            log.append("\n".join(msg_lines))
                            spell_used = True
                            break
                if not spell_used:
                    can_phys = has_phys_weapon or (not has_phys_weapon and has_free_hand)
                    can_magic = has_magic_weapon
                    if can_phys or can_magic:
                        phys_dmg = 0.0
                        magic_dmg = 0.0
                        crit_flag = ""
                        magic_crit_flag = ""
                        missed = False

                        if can_phys:
                            effective_atk = p_stats["atk"] * p_multipliers.get("atk", 1.0)
                            effective_def = e_stats["def"] * e_multipliers.get("def", 1.0)
                            effective_armor_pen = p_stats["armor_pen"]
                            effective_def_after_pen = max(0, effective_def - effective_armor_pen)
                            base_phys = effective_atk * effective_atk / (effective_atk + effective_def_after_pen) if effective_atk + effective_def_after_pen > 0 else 0
                            phys_dmg = base_phys * random.uniform(0.8, 1.2)
                        if can_magic:
                            effective_magic_atk = p_stats["magic_atk"] * p_multipliers.get("magic_atk", 1.0)
                            effective_mres = e_stats["magic_res"] * e_multipliers.get("magic_res", 1.0)
                            base_magic = effective_magic_atk * effective_magic_atk / (effective_magic_atk + effective_mres) if effective_magic_atk + effective_mres > 0 else 0
                            magic_dmg = base_magic * random.uniform(0.8, 1.2)

                        hit = random.random() * 100 > get_evasion_chance(p_stats["accuracy"] * p_multipliers.get("accuracy", 1.0),
                                                                         e_stats["evasion_rating"] * e_multipliers.get("evasion_rating", 1.0))
                        crit_flag = ""
                        magic_crit_flag = ""
                        if hit:
                            if can_phys:
                                phys_crit_chance = p_stats["crit_chance"] * p_multipliers.get("crit_chance", 1.0)
                                phys_crit_damage = p_stats["crit_damage"] * p_multipliers.get("crit_damage", 1.0)
                                phys_dmg, crit_flag = apply_crit_damage(phys_dmg, phys_crit_chance, phys_crit_damage, "💥")
                        else:
                            phys_dmg = 0.0
                            missed = True

                        if can_magic:
                            magic_crit_chance = p_stats["magic_crit_chance"] * p_multipliers.get("magic_crit_chance", 1.0)
                            magic_crit_damage = p_stats["magic_crit_damage"] * p_multipliers.get("magic_crit_damage", 1.0)
                            magic_dmg, magic_crit_flag = apply_crit_damage(magic_dmg, magic_crit_chance, magic_crit_damage, "💫")

                        total_dmg = phys_dmg + magic_dmg

                        if total_dmg > 0:
                            remaining_dmg = total_dmg
                            absorbed = 0.0
                            if enemy_shield > 0:
                                absorbed = min(remaining_dmg, enemy_shield)
                                enemy_shield -= absorbed
                                remaining_dmg -= absorbed

                            if remaining_dmg > 0:
                                e_stats["hp"] -= remaining_dmg
                                msg = f"[{fmt_float(t,6)}с] 🗡{crit_flag}{magic_crit_flag} Вы атаковали, {remaining_dmg:.1f} урона"
                            else:
                                msg = f"[{fmt_float(t,6)}с] 🗡{crit_flag}{magic_crit_flag} Вы атаковали, весь урон поглощён щитом"

                            if absorbed > 0:
                                msg += f" (поглощено {absorbed:.1f})"

                            if phys_dmg > 0 and p_stats["lifesteal"] > 0:
                                ls = phys_dmg * (p_stats["lifesteal"] / 100.0)
                                p_stats["hp"] = min(p_stats["max_hp"], p_stats["hp"] + ls)
                                msg += f" 🩸 +{fmt_float(ls,4)} HP"
                            if phys_dmg > 0 and e_stats["thorns"] > 0:
                                th = phys_dmg * (e_stats["thorns"] / 100.0)
                                absorbed_th = 0.0
                                if current_shield > 0:
                                    absorbed_th = min(th, current_shield)
                                    current_shield -= absorbed_th
                                    th -= absorbed_th
                                if th > 0:
                                    p_stats["hp"] -= th
                                    msg += f" 🌵 -{fmt_float(th, 4)} HP"
                                if absorbed_th > 0:
                                    msg += f" (поглощено щитом {fmt_float(absorbed_th, 4)})"
                            if magic_dmg > 0 and p_stats["magic_shield_drain"] > 0:
                                drain = magic_dmg * (p_stats["magic_shield_drain"] / 100.0)
                                current_shield = min(current_shield + drain, p_stats["max_hp"] * 0.5)
                                msg += f" 🔋 +{fmt_float(drain, 4)} щита"

                            msg += f" {status_str(e_stats, enemy_shield, False)}"
                            log.append(msg)
                        else:
                            if missed and can_phys and not can_magic:
                                msg = f"[{fmt_float(t,6)}с] 🗡{magic_crit_flag} Вы промахнулись"
                            elif missed and can_phys and can_magic and magic_dmg == 0:
                                msg = f"[{fmt_float(t,6)}с] 🗡{magic_crit_flag} Вы промахнулись"
                            else:
                                msg = f"[{fmt_float(t,6)}с] 🗡{crit_flag}{magic_crit_flag} Вы атаковали, но не пробили защиту"
                            log.append(msg)
            else:
                p_next_action += p_action_interval

        # Действие врага
        if abs(t - e_next_action) < 1e-9:
            if not enemy_stopped and e_stats["hp"] > 0:
                e_next_action = t + e_action_interval
                spell_used = False
                if enemy_spells:
                    available = [i for i, cd in enumerate(enemy_cooldowns) if cd <= t]
                    random.shuffle(available)
                    for idx in available:
                        spell = enemy_spells[idx]
                        if e_stats.get("mp", 0) >= spell["mp_cost"]:
                            e_stats["mp"] -= spell["mp_cost"]
                            cd = spell["base_cooldown"] / (1 + spell["upgrades"] * 0.1)
                            enemy_cooldowns[idx] = t + cd
                            msg = f"[{fmt_float(t,6)}с] Враг использует заклинание ✨ {spell['name']}:\n"
                            for eff in spell["effects"]:
                                if eff["target"] == TARGET_ENEMY:
                                    msg += apply_effect(eff, e_stats, p_stats, False, p_effects)
                                else:
                                    msg += apply_effect(eff, e_stats, e_stats, False, e_effects)
                            log.append(msg)
                            spell_used = True
                            break

                if not spell_used:
                    # Определяем тип атаки врага и базовый урон
                    if enemy.get('atk_type') == 'Magic':
                        effective_magic_atk = e_stats["magic_atk"] * e_multipliers.get("magic_atk", 1.0)
                        effective_mres = p_stats["magic_res"] * p_multipliers.get("magic_res", 1.0)
                        base_dmg = effective_magic_atk * effective_magic_atk / (effective_magic_atk + effective_mres) if effective_magic_atk + effective_mres > 0 else 0
                        dmg = base_dmg * random.uniform(0.8, 1.2)
                        crit_chance = e_stats.get("magic_crit_chance", 0) * e_multipliers.get("magic_crit_chance", 1.0)
                        crit_damage = e_stats.get("magic_crit_damage", 150) * e_multipliers.get("magic_crit_damage", 1.0)
                        emoji = "💫"
                    else:
                        effective_atk = e_stats["atk"] * e_multipliers.get("atk", 1.0)
                        effective_def = p_stats["def"] * p_multipliers.get("def", 1.0)
                        base_dmg = effective_atk * effective_atk / (effective_atk + effective_def) if effective_atk + effective_def > 0 else 0
                        dmg = base_dmg * random.uniform(0.8, 1.2)
                        crit_chance = e_stats["crit_chance"] * e_multipliers.get("crit_chance", 1.0)
                        crit_damage = e_stats["crit_damage"] * e_multipliers.get("crit_damage", 1.0)
                        emoji = "💥"

                    # Проверка на уклонение
                    if random.random() * 100 > get_evasion_chance(e_stats["accuracy"] * e_multipliers.get("accuracy", 1.0),
                                                                 p_stats["evasion_rating"] * e_multipliers.get("evasion_rating", 1.0)):
                        # Применяем криты
                        dmg, crit_flag = apply_crit_damage(dmg, crit_chance, crit_damage, emoji)

                        # Поглощение щитом
                        absorbed = 0.0
                        if current_shield > 0:
                            absorbed = min(dmg, current_shield)
                            current_shield -= absorbed
                            dmg -= absorbed

                        # Нанесение урона
                        if dmg > 0:
                            p_stats["hp"] -= dmg
                            msg = f"[{fmt_float(t,6)}с] 😡 Враг нанёс вам{crit_flag} {dmg:.1f} урона"
                        else:
                            msg = f"[{fmt_float(t,6)}с] 😡 Враг атаковал, но весь урон был поглощён щитом"
                        if absorbed > 0:
                            msg += f" (поглощено {absorbed:.1f})"

                        # Вампиризм врага
                        if dmg > 0 and e_stats["lifesteal"] > 0:
                            heal = dmg * (e_stats["lifesteal"] / 100.0)
                            if heal > 0:
                                e_stats["hp"] = min(e_stats["max_hp"], e_stats["hp"] + heal)
                                msg += f" 🩸 +{fmt_float(heal, 4)} HP"

                        msg += f" {status_str(p_stats, current_shield, True)}"
                        log.append(msg)

                        # Шипы игрока
                        if p_stats["thorns"] > 0 and dmg > 0:
                            th = dmg * (p_stats["thorns"] / 100.0)
                            if enemy_shield > 0:
                                absorbed_th = min(th, enemy_shield)
                                enemy_shield -= absorbed_th
                                th -= absorbed_th
                            if th > 0:
                                e_stats["hp"] -= th
                                log.append(f"[{fmt_float(t,6)}с] 🌵 Ваши шипы нанесли врагу {fmt_float(th, 4)} урона {status_str(e_stats, enemy_shield, False)}")
                    else:
                        log.append(f"[{fmt_float(t,6)}с] 💨 Вы уклонились")
            else:
                e_next_action += e_action_interval

        if p_stats["hp"] <= 0 or e_stats["hp"] <= 0:
            break

    player.hp = max(0, p_stats["hp"])
    player.mp = max(0, p_stats["mp"])

    if t >= max_time:
        return False, log, "⏳ Битва оказалась на равных, поэтому вы решили мирно разойтись..."
    elif player.hp <= 0:
        return False, log, "💀 Вы погибли!"
    else:
        return True, log, "🏆 Вы победили!"

# ===================== КЛАВИАТУРЫ =====================


def main_menu_kbd():
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    builder.button(text="🗡 Охота", callback_data=MenuCB(action="hunt").pack())
    builder.button(text="🏋️ Тренировка",
                   callback_data=MenuCB(action="train").pack())
    builder.button(text="🎒 Инвентарь",
                   callback_data=MenuCB(action="inv").pack())
    builder.button(text="🔮 Магия", callback_data=MenuCB(
        action="spells").pack())
    builder.button(text="🏪 Магазин",
                   callback_data=MenuCB(action="shop").pack())
    builder.button(text="🧪 Зелья", callback_data=MenuCB(
        action="potions").pack())
    builder.button(text="🧭 Экспедиция",
                   callback_data=MenuCB(action="exped").pack())
    builder.button(text="👤 Герой", callback_data=MenuCB(
        action="profile").pack())
    builder.adjust(2, 2, 2, 2)
    return builder.as_markup()


def waiting_kbd(state_end_time):
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Отменить",
                   callback_data=ActionCB(action="cancel").pack())
    builder.button(text="⏳ Осталось времени",
                   callback_data=ActionCB(action="check_time").pack())
    builder.adjust(2)
    return builder.as_markup()


def dead_kbd():
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 В главное меню",
                   callback_data=MenuCB(action="profile").pack())
    return builder.as_markup()


def cancel_kbd():
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Отменить",
                   callback_data=ActionCB(action="cancel").pack())
    return builder.as_markup()

def training_complete_kbd(stat: str):
    """Клавиатура после завершения тренировки."""
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    builder.button(text="🏋️ Снова тренировать", callback_data=TrainCB(stat=stat).pack())
    builder.button(text="📋 К списку тренировок", callback_data=MenuCB(action="train").pack())
    builder.button(text="🔙 В главное меню", callback_data=MenuCB(action="profile").pack())
    builder.adjust(1)  # кнопки в столбик (можно изменить на 2, если нужно)
    return builder.as_markup()

async def safe_edit(message: Message, text: str, reply_markup: InlineKeyboardMarkup = None):
    try:
        await message.edit_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    except TelegramRetryAfter as e:
        await asyncio.sleep(e.retry_after)
        await safe_edit(message, text, reply_markup)
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            raise

# ===================== ПРОСМОТР ПРЕДМЕТА =====================

async def get_item_view_data(player: Player, global_idx: int):
    item, is_equip, slot_or_idx = get_item_by_global_index(player, global_idx)
    if not item:
        return None, None

    if is_equip:
        slot_name = slot_or_idx
        real_idx = -1
    else:
        real_idx = slot_or_idx
        slot_name = ""

    text = f"💰 Золото: {player.gold}\n📦 <b>{item['name']}</b> ({'Надето' if is_equip else 'В сумке'})\nТип: {ITEM_TYPE_RU.get(item['item_type'], item['item_type'])}\n\nХарактеристики:\n"

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    b = InlineKeyboardBuilder()

    dust = item.get('dust', 0)
    battle_count = item.get('battle_count', 0)

    for stat_key, stat_data in item["stats"].items():
        is_percent = stat_key in PERCENT_STATS
        
        raw_cost = GOLD_PER_STAGE * 25 * player.max_unlocked_difficulty * stat_data.get('upgrade_price_mult', 1.0)
        upg_cost = max(100, int(raw_cost))
        s_ru = f"{STAT_EMOJI.get(stat_key, '')} {STAT_RU.get(stat_key, stat_key)}"
        bonus_type = stat_data.get('bonus_type', 'flat')
        bonus_symbol = '%' if bonus_type == 'percent' else ''
        curr_str = fmt_float(stat_data['current'], 4)
        base_str = fmt_float(stat_data['base'], 4)
        text += f"• {s_ru}: {curr_str}{bonus_symbol} (база {base_str}{bonus_symbol}, улучшений {stat_data['upgrades']})\n"
        text += f"         Улучшить: 💰 {upg_cost} (+{base_str}{bonus_symbol})\n"

        upg_text = f"⬆️ {STAT_EMOJI.get(stat_key, '')}".strip()
        b.button(text=upg_text, callback_data=ItemCB(action="upg", idx=global_idx, stat=stat_key).pack())

        if dust > 0:
            b.button(text="🎲 Сброс", callback_data=ItemCB(action="reroll", idx=global_idx, stat=stat_key).pack())

    b.adjust(2)

    text += f"\n🔮 Пыль душ: {dust} | Боёв: {battle_count}/{DUST_PER_BATTLE}\n"
    if dust > 0:
        text += f"\n🎲 Вы можете сбросить выбранный стат, потратив 1 пыль\nЭто сбросит кол-во улучшений этого стата и даст вам новый, случайный стат вместо него\n"
    
    if dust > 0:
        b.row(InlineKeyboardButton(text=f"✨ Использовать пыль душ", callback_data=ItemCB(action="upgrade_rarity", idx=global_idx).pack()))

    if is_equip:
        b.row(InlineKeyboardButton(text="Снять", callback_data=ItemCB(action="unequip", idx=global_idx).pack()))
    else:
        allowed_slots = ITEM_TYPE_TO_SLOTS.get(item['item_type'], [])
        if len(allowed_slots) == 1:
            b.row(InlineKeyboardButton(text="Надеть", callback_data=ItemCB(action="equip", idx=global_idx).pack()))
        elif len(allowed_slots) > 1:
            b.row(InlineKeyboardButton(text="🔧 Выбрать слот", callback_data=ItemCB(action="choose_slot", idx=global_idx).pack()))
        b.row(InlineKeyboardButton(text=f"Продать (💰 {item['sell_price']})", callback_data=ItemCB(action="sell", idx=global_idx).pack()))
    
    if not is_equip:
        allowed_slots = ITEM_TYPE_TO_SLOTS.get(item['item_type'], [])
        if allowed_slots:
            b.row(InlineKeyboardButton(text="🔍 Сравнить с надетым", callback_data=ItemCB(action="compare", idx=global_idx).pack()))

    b.row(InlineKeyboardButton(text="🔙 Назад", callback_data=MenuCB(action="inv").pack()))

    return text, b.as_markup()

@dp.callback_query(ItemCB.filter(F.action == "compare"))
async def compare_item(query: CallbackQuery, callback_data: ItemCB):
    player = await get_player(query.from_user.id)
    global_idx = callback_data.idx
    item, is_equip, slot_or_idx = get_item_by_global_index(player, global_idx)
    if not item:
        await query.answer("Предмет не найден!")
        return

    slots = ITEM_TYPE_TO_SLOTS.get(item['item_type'], [])
    if not slots:
        await query.answer("Для этого предмета нет соответствующих слотов.")
        return

    text = f"<b>Сравнение с экипированным</b>\n\n"
    shown_items = set()
    for slot in slots:
        slot_item = player.equip.get(slot)
        if slot_item:
            item_id = slot_item.get('id')
            if item_id in shown_items:
                continue
            shown_items.add(item_id)
            slot_name = SLOT_RU.get(slot, slot)
            text += f"<b>Слот: [{slot_name}]</b>\n\n"
            text += f"<b>{slot_item['name']}</b>\nТип: {ITEM_TYPE_RU.get(slot_item['item_type'], slot_item['item_type'])}\n\nХарактеристики:\n"
            for stat_key, stat_data in slot_item['stats'].items():
                is_percent = stat_key in PERCENT_STATS
                s_ru = f"{STAT_EMOJI.get(stat_key, '')} {STAT_RU.get(stat_key, stat_key)}"
                bonus_type = stat_data.get('bonus_type', 'flat')
                bonus_symbol = '%' if bonus_type == 'percent' else ''
                curr_str = fmt_float(stat_data['current'], 4)
                base_str = fmt_float(stat_data['base'], 4)
                text += f"• {s_ru}: {curr_str}{bonus_symbol} (база {base_str}{bonus_symbol}, улучшений {stat_data['upgrades']})\n"
            text += f"\n🔮 Пыль душ: {slot_item.get('dust', 0)}\n\n"
        else:
            slot_name = SLOT_RU.get(slot, slot)
            text += f"<b>[{slot_name}]</b> пусто\n\n"

    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    close_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Я посмотрел", callback_data=ActionCB(action="close_compare").pack())]
    ])

    await query.message.answer(text, parse_mode=ParseMode.HTML, reply_markup=close_kb)
    await query.answer()

@dp.callback_query(ActionCB.filter(F.action == "close_compare"))
async def close_compare_message(query: CallbackQuery):
    await query.message.delete()
    await query.answer()

# ===================== ОБРАБОТЧИКИ КОМАНД =====================


@dp.message(CommandStart())
async def cmd_start(message: Message):
    await load_db()
    player = await get_player(
        message.from_user.id,
        name=message.from_user.first_name,
        username=message.from_user.username
    )
    await message.answer(
        f"Добро пожаловать, <b>{player.name}</b>!\n\nНе бойся поражений, твоя сила ограничивается только временем и твоим собственным желанием.\n\nЕсли у тебя есть какие-то вопросы, жми /guide",
        reply_markup=main_menu_kbd()
    )

@dp.message(Command("leaderboard"))
async def cmd_leaderboard(message: Message):
    # Обновляем данные текущего пользователя
    await get_player(
        message.from_user.id,
        name=message.from_user.first_name,
        username=message.from_user.username
    )
    # Обновляем кэш, если нужно
    await update_leaderboard_cache()
    full = leaderboard_cache['full_sorted']
    if not full:
        await message.answer("Пока нет игроков.")
        return
    user_id = str(message.from_user.id)
    position = None
    for idx, (uid, name, username, diff) in enumerate(full, 1):
        if uid == user_id:
            position = idx
            break
    text = f"🏆 <b>Топ игроков по уровню угрозы</b>\n\n{leaderboard_cache['top_25']}\n\n"
    if position:
        if position <= 25:
            text += "Вы в топе! Поздравляем!"
        else:
            for uid, name, username, diff in full:
                if uid == user_id:
                    username_str = f"(@{username})" if username else ""
                    text += f"Ваше место: {position}. {name} {username_str} — Угроза {diff}"
                    break
    else:
        text += "Вы еще не начинали играть?\n\nНапишите /start в @InfinitRPGbot"
    await message.answer(text)

@dp.message(Command("profile"))
async def cmd_profile(message: Message):
    # Обновляем данные самого пользователя (чтобы его username был актуален)
    await get_player(
        message.from_user.id,
        name=message.from_user.first_name,
        username=message.from_user.username
    )
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Укажите username, например: /profile @username")
        return
    username_input = args[1].strip()
    if username_input.startswith('@'):
        username_input = username_input[1:]
    found = None
    async with db_lock:
        for uid, pdata in db['players'].items():
            if pdata.get('username') == username_input:
                found = (uid, pdata)
                break
    if not found:
        await message.answer(f"Пользователь @{username_input} не найден.")
        return
    uid, pdata = found
    player = Player.from_dict(pdata)
    t_stats = get_total_stats(player)

    # Формируем полный профиль, как в menu_profile
    text = f"👤 <b>Профиль игрока {player.name}</b> (@{player.username})\n"
    text += f"💰 Золото: {player.gold}\n"
    text += f"🔓 Доступная угроза: {player.max_unlocked_difficulty}\n\n"
    text += f"🌟 Адаптивность: {t_stats['adaptability']:.3f}\n"
    text += f"{STAT_EMOJI['hp']} {STAT_RU['hp']}: {player.hp:.1f}/{t_stats['max_hp']:.1f} (+{t_stats['hp_regen']:.2f}/мин)\n"
    text += f"{STAT_EMOJI['m_shield']} {STAT_RU['m_shield']}: {t_stats['m_shield']:.1f} (восстанавливается каждый бой)\n"
    text += f"{STAT_EMOJI['mp']} {STAT_RU['mp']}: {player.mp:.1f}/{t_stats['max_mp']:.1f} (+{t_stats['mp_regen']:.2f}/мин)\n"
    text += f"{STAT_EMOJI['atk']} {STAT_RU['atk']}: {t_stats['atk']:.2f} | {STAT_EMOJI['magic_atk']} {STAT_RU['magic_atk']}: {t_stats['magic_atk']:.2f}\n"
    text += f"{STAT_EMOJI['def']} {STAT_RU['def']}: {t_stats['def']:.2f} | {STAT_EMOJI['magic_res']} {STAT_RU['magic_res']}: {t_stats['magic_res']:.2f}\n"
    text += f"{STAT_EMOJI['crit_chance']} {STAT_RU['crit_chance']}: {t_stats['crit_chance']:.2f}% | {STAT_EMOJI['crit_damage']} {STAT_RU['crit_damage']}: {t_stats['crit_damage']:.2f}%\n"
    text += f"{STAT_EMOJI['magic_crit_chance']} {STAT_RU['magic_crit_chance']}: {t_stats['magic_crit_chance']:.2f}% | {STAT_EMOJI['magic_crit_damage']} {STAT_RU['magic_crit_damage']}: {t_stats['magic_crit_damage']:.2f}%\n"
    text += f"{STAT_EMOJI['accuracy']} {STAT_RU['accuracy']}: {t_stats['accuracy']:.2f} | {STAT_EMOJI['evasion_rating']} {STAT_RU['evasion_rating']}: {t_stats['evasion_rating']:.2f}\n"
    text += f"{STAT_EMOJI['lifesteal']} {STAT_RU['lifesteal']}: {t_stats['lifesteal']:.2f}% | {STAT_EMOJI['thorns']} {STAT_RU['thorns']}: {t_stats['thorns']:.2f}%\n"
    text += f"{STAT_EMOJI['magic_shield_drain']} {STAT_RU['magic_shield_drain']}: {t_stats['magic_shield_drain']:.2f}% | {STAT_EMOJI['magic_efficiency']} {STAT_RU['magic_efficiency']}: {t_stats['magic_efficiency']:.2f}\n"
    text += f"{STAT_EMOJI['armor_pen']} {STAT_RU['armor_pen']}: {t_stats['armor_pen']:.2f} | {STAT_EMOJI['atk_spd']} {STAT_RU['atk_spd']}: {t_stats['atk_spd']:.2f}\n"
    text += f"{STAT_EMOJI['gold_mult']} {STAT_RU['gold_mult']}: x{fmt_float(t_stats['gold_mult'], 4)} | {STAT_EMOJI['luck']} {STAT_RU['luck']}: x{fmt_float(t_stats['luck'], 4)} | {STAT_EMOJI['talent']} {STAT_RU['talent']}: x{fmt_float(t_stats['talent'], 4)}\n"
    text += f"{STAT_EMOJI['effect_resistance']} {STAT_RU['effect_resistance']}: {t_stats['effect_resistance']:.2f}\n"

    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 В главное меню", callback_data=MenuCB(action="profile").pack())]
    ])
    await message.answer(text, reply_markup=keyboard)

@dp.message(Command("guide"))
async def cmd_guide(message: Message):
    text = 'Гайд по игре будет <a href="https://telegra.ph/Infinity-RPG-03-18">ЗДЕСЬ</a>'
    await message.answer(text, parse_mode=ParseMode.HTML)

@dp.message(Command("relive"))
async def cmd_relive(message: Message):
    if message.from_user.id != 812357068:
        await message.answer("⛔ Эта команда доступна только разработчику.")
        return
    await load_db()
    player = await get_player(message.from_user.id)
    if player.state == 'dead':
        player.state = 'idle'
        player.state_end_time = 0
        t_stats = get_total_stats(player)
        player.hp = t_stats['max_hp']
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
    if message.from_user.id != 812357068:
        await message.answer("⛔ Эта команда доступна только разработчику.")
        return
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

@dp.message(Command("update_leaderboard"))
async def cmd_update_leaderboard(message: Message):
    if message.from_user.id != 812357068:
        await message.answer("⛔ Эта команда доступна только разработчику.")
        return
    await update_leaderboard_cache(force=True)
    await message.answer("✅ Кэш лидерборда принудительно обновлён.")

@dp.callback_query(ActionCB.filter(F.action == "cancel"))
async def cb_cancel(query: CallbackQuery, callback_data: ActionCB):
    player = await get_player(query.from_user.id)
    if player.state in CANCELABLE_STATES:
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
    await check_and_complete_state(player)
    if player.state != 'idle':
        remaining = player.state_end_time - time.time()
        minutes = int(remaining//60)
        seconds = int(remaining % 60)
        state_rus = {"training": "тренируетесь", "expedition": "в экспедиции",
                     "dead": "мертвы"}.get(player.state, player.state)
        await query.answer(f"Вы {state_rus}. Осталось: {minutes} мин {seconds} сек.", show_alert=True)
    else:
        await query.answer("Вы сейчас не заняты.", show_alert=True)


@dp.callback_query()
async def process_any_callback(query: CallbackQuery, bot: Bot):
    # Специальные действия, которые обрабатываются отдельно и не требуют блокировки
    if query.data and (query.data.startswith("act:cancel") or query.data.startswith("act:check_time")):
        return

    await load_db()
    player = await get_player(query.from_user.id)
    await apply_passive_regen(player)
    
    await check_and_complete_state(player)

    # Разрешённые префиксы callback_data, которые можно выполнять даже при не-idle состоянии
    allowed_prefixes = (
        'menu:', 'it:', 'spell:', 'cbtstats:', 'sellmass:',
        'sh:', 'pot:', 'eqchoice:', 'act:', 'hunt:'
    )
    if query.data and any(query.data.startswith(p) for p in allowed_prefixes):
        # Пропускаем дальше, позволяя другим обработчикам сработать
        raise SkipHandler()

    # Если игрок не в состоянии idle и действие не разрешено – блокируем
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

    # Если игрок свободен – пропускаем
    raise SkipHandler()


@dp.callback_query(MenuCB.filter(F.action == "profile"))
async def menu_profile(query: CallbackQuery, callback_data: MenuCB):
    player = await get_player(query.from_user.id)
    t_stats = get_total_stats(player)

    text = f"👤 <b>Профиль: {player.name}</b>\n💰 Золото: {player.gold}\n"
    text += f"🔓 Доступная угроза: {player.max_unlocked_difficulty}\n\n"
    text += f"🌟 Адаптивность: {t_stats['adaptability']:.3f}\n"
    text += f"{STAT_EMOJI['hp']} {STAT_RU['hp']}: {player.hp:.1f}/{t_stats['max_hp']:.1f} (+{t_stats['hp_regen']:.2f}/мин)\n"
    text += f"{STAT_EMOJI['m_shield']} {STAT_RU['m_shield']}: {t_stats['m_shield']:.1f} (восстанавливается каждый бой)\n"
    text += f"{STAT_EMOJI['mp']} {STAT_RU['mp']}: {player.mp:.1f}/{t_stats['max_mp']:.1f} (+{t_stats['mp_regen']:.2f}/мин)\n"
    text += f"{STAT_EMOJI['atk']} {STAT_RU['atk']}: {t_stats['atk']:.2f} | {STAT_EMOJI['magic_atk']} {STAT_RU['magic_atk']}: {t_stats['magic_atk']:.2f}\n"
    text += f"{STAT_EMOJI['def']} {STAT_RU['def']}: {t_stats['def']:.2f} | {STAT_EMOJI['magic_res']} {STAT_RU['magic_res']}: {t_stats['magic_res']:.2f}\n"
    text += f"{STAT_EMOJI['crit_chance']} {STAT_RU['crit_chance']}: {t_stats['crit_chance']:.2f}% | {STAT_EMOJI['crit_damage']} {STAT_RU['crit_damage']}: {t_stats['crit_damage']:.2f}%\n"
    text += f"{STAT_EMOJI['magic_crit_chance']} {STAT_RU['magic_crit_chance']}: {t_stats['magic_crit_chance']:.2f}% | {STAT_EMOJI['magic_crit_damage']} {STAT_RU['magic_crit_damage']}: {t_stats['magic_crit_damage']:.2f}%\n"
    text += f"{STAT_EMOJI['accuracy']} {STAT_RU['accuracy']}: {t_stats['accuracy']:.2f} | {STAT_EMOJI['evasion_rating']} {STAT_RU['evasion_rating']}: {t_stats['evasion_rating']:.2f}\n"
    text += f"{STAT_EMOJI['lifesteal']} {STAT_RU['lifesteal']}: {t_stats['lifesteal']:.2f}% | {STAT_EMOJI['thorns']} {STAT_RU['thorns']}: {t_stats['thorns']:.2f}%\n"
    text += f"{STAT_EMOJI['magic_shield_drain']} {STAT_RU['magic_shield_drain']}: {t_stats['magic_shield_drain']:.2f}% | {STAT_EMOJI['magic_efficiency']} {STAT_RU['magic_efficiency']}: {t_stats['magic_efficiency']:.2f}\n"
    text += f"{STAT_EMOJI['armor_pen']} {STAT_RU['armor_pen']}: {t_stats['armor_pen']:.2f} | {STAT_EMOJI['atk_spd']} {STAT_RU['atk_spd']}: {t_stats['atk_spd']:.2f}\n"
    text += f"{STAT_EMOJI['gold_mult']} {STAT_RU['gold_mult']}: x{fmt_float(t_stats['gold_mult'], 4)} | {STAT_EMOJI['luck']} {STAT_RU['luck']}: x{fmt_float(t_stats['luck'], 4)} | {STAT_EMOJI['talent']} {STAT_RU['talent']}: x{fmt_float(t_stats['talent'], 4)}\n"
    text += f"{STAT_EMOJI['effect_resistance']} {STAT_RU['effect_resistance']}: {t_stats['effect_resistance']:.2f}\n"
    
    await safe_edit(query.message, text, reply_markup=main_menu_kbd())


def get_percent_bonuses(player):
    """Возвращает словарь суммарных процентных бонусов от экипировки и зелий."""
    percent = player.percent_bonus.copy()
    for slot, item in player.equip.items():
        if item:
            for stat_name, stat_data in item["stats"].items():
                if stat_data.get('bonus_type') == 'percent':
                    current_val = stat_data['base'] * (stat_data['upgrades'] + 1)
                    percent[stat_name] = percent.get(stat_name, 0) + current_val
    return percent

def get_stat_components(player, stat):
    """Возвращает (base, flat_bonus, percent_bonus) для указанного стата."""
    base = player.base_stats[stat]
    flat = 0.0
    percent = player.percent_bonus.get(stat, 0.0)
    for slot, item in player.equip.items():
        if item and stat in item["stats"]:
            s_data = item["stats"][stat]
            val = s_data['base'] * (s_data['upgrades'] + 1)
            if s_data.get('bonus_type') == 'percent':
                percent += val
            else:
                flat += val
    return base, flat, percent

def get_item_by_global_index(player, global_idx):
    # Экипированные предметы в фиксированном порядке (как в menu_inv)
    order = EQUIP_ORDER
    for slot in order:
        item = player.equip.get(slot)
        if item:
            if global_idx == 0:
                return item, True, slot
            global_idx -= 1

    # Предметы в инвентаре
    for inv_idx, item in enumerate(player.inventory):
        if global_idx == 0:
            return item, False, inv_idx
        global_idx -= 1

    return None, None, None

def get_spell_emoji(spell):
    """Возвращает эмодзи, соответствующий основному эффекту заклинания."""
    # Приоритет типов эффектов (чем выше в списке, тем важнее)
    priority_map = {
        "damage": "⚔️",
        "heal": "💚",
        "shield": "🛡️",
        "buff": "⬆️",
        "debuff": "⬇️",
        "time_stop": "⏸️",
        "mp_restore": "💧",
        "mp_burn": "🔥",
        "dot": "🔥",
        "hot": "💚"
    }
    # Собираем все типы эффектов из заклинания
    types = {eff['type'] for eff in spell.get('effects', [])}
    if not types:
        return "❓"
    # Выбираем первый по приоритету
    for key in priority_map:
        if key in types:
            return priority_map[key]
    return "✨"

@dp.callback_query(MenuCB.filter(F.action == "train"))
async def menu_train(query: CallbackQuery, callback_data: MenuCB):
    player = await get_player(query.from_user.id)
    page = callback_data.page
    stats = player.training_order

    per_page = 9
    start = page * per_page
    end = start + per_page

    # Получаем текущую адаптивность и процентные бонусы
    t_stats = get_total_stats(player)
    total_adapt = t_stats['adaptability']
    percent_bonuses = get_percent_bonuses(player)

    text = f"🏋️ <b>Тренировка</b>\n\nВыберите характеристику:\n\n"

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()

    for i, stat in enumerate(stats[start:end], start=1):
        stat_name = f"{STAT_EMOJI.get(stat, '')} {STAT_RU.get(stat, stat)}"
        base_inc = TRAINING_INCREMENTS.get(stat, 0.01)

        if stat == 'adaptability':
            increment = base_inc
        else:
            increment = base_inc * total_adapt

        # Реальный прирост к итоговому стану с учётом процентных бонусов
        real_gain = increment * (1 + percent_bonuses.get(stat, 0) / 100.0)

        text += f"<b>{stat_name}</b> +{fmt_float(increment)} ({fmt_float(real_gain)})\n"
        builder.button(text=f"{STAT_EMOJI.get(stat, '')}", callback_data=TrainCB(stat=stat).pack())

    builder.adjust(3)

    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(
            text="⬅️", callback_data=MenuCB(action="train", page=page-1).pack()))
    if end < len(stats):
        nav_row.append(InlineKeyboardButton(
            text="➡️", callback_data=MenuCB(action="train", page=page+1).pack()))
    if nav_row:
        builder.row(*nav_row)

    builder.row(InlineKeyboardButton(text="🔙 Назад",
                callback_data=MenuCB(action="profile").pack()))

    await safe_edit(query.message, text, reply_markup=builder.as_markup())


@dp.callback_query(TrainCB.filter())
async def process_train(query: CallbackQuery, callback_data: TrainCB):
    player = await get_player(query.from_user.id)
    
    # Проверка, что игрок жив и не занят
    if player.state != 'idle':
        if player.state == 'dead':
            await query.answer("💀 Вы мертвы и не можете тренироваться.", show_alert=True)
        else:
            await query.answer("⏳ Вы сейчас заняты другим делом.", show_alert=True)
        return
    
    stat = callback_data.stat

    # Текущее финальное значение
    t_stats = get_total_stats(player)
    current_val = t_stats[stat]

    # Расчёт прироста (аналогично menu_train)
    base_inc = TRAINING_INCREMENTS.get(stat, 0.01)
    if stat == 'adaptability':
        increment = base_inc
    else:
        total_adapt = t_stats['adaptability']
        increment = base_inc * total_adapt

    # Сбор плоских и процентных бонусов от предметов и зелий для данного стата
    flat_bonus = 0.0
    percent_bonus = 0.0

    # Предметы в экипировке
    for slot, item in player.equip.items():
        if item and stat in item["stats"]:
            s_data = item["stats"][stat]
            current_item_val = s_data['base'] * (s_data['upgrades'] + 1)
            if s_data.get('bonus_type') == 'percent':
                percent_bonus += current_item_val
            else:
                flat_bonus += current_item_val

    # Процентные бонусы от зелий
    percent_bonus += player.percent_bonus.get(stat, 0.0)

    # Новое финальное значение после тренировки
    new_base = player.base_stats[stat] + increment
    new_val = (new_base + flat_bonus) * (1 + percent_bonus / 100.0)

    # Устанавливаем состояние тренировки
    player.state = 'training'
    player.training_stat = stat
    player.state_end_time = time.time() + CONFIG["time_train"]
    await save_player(player)

    # Отправляем сообщение с реальными значениями
    await safe_edit(query.message,
                    f"Вы начали тренировку стата <b>{STAT_RU.get(stat, stat)}</b>\n\n"
                    f"Текущее значение: {fmt_float(current_val)}\n"
                    f"После тренировки: {fmt_float(new_val)}",
                    reply_markup=waiting_kbd(player.state_end_time))


@dp.callback_query(MenuCB.filter(F.action == "hunt"))
async def menu_hunt(query: CallbackQuery, callback_data: MenuCB):
    player = await get_player(query.from_user.id)
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    b = InlineKeyboardBuilder()

    kills_on_current = player.kills_on_max
    kills_needed = KILLS_TO_UNLOCK_NEXT - kills_on_current if player.current_difficulty == player.max_unlocked_difficulty else 0
    
    next_unlock_info = ""
    if player.current_difficulty == player.max_unlocked_difficulty and kills_needed > 0:
        next_unlock_info = f"\nДо следующей угрозы осталось убить: {kills_needed} врагов"

    b.button(text="◀️", callback_data=HuntCB(action="dec").pack())
    b.button(text=f"Угроза: {player.current_difficulty}",
             callback_data=HuntCB(action="set").pack())
    b.button(text="▶️", callback_data=HuntCB(action="inc").pack())
    b.button(text="⚔️ Начать поиск",
             callback_data=HuntCB(action="start").pack())
    b.button(text="🔙 Назад", callback_data=MenuCB(action="profile").pack())
    b.adjust(3, 1, 1)

    text = f"💰 Золото: {player.gold}\n\n⚔️ <b>Охота</b>\n\nМакс. доступная угроза: {player.max_unlocked_difficulty}\n"
    text += next_unlock_info
    text += "\n\nУстановите уровень угрозы для поиска."

    await safe_edit(query.message, text, reply_markup=b.as_markup())


@dp.callback_query(HuntCB.filter())
async def process_hunt(query: CallbackQuery, callback_data: HuntCB, state: FSMContext):
    player = await get_player(query.from_user.id)
    act = callback_data.action

    user_id = query.from_user.id
    lock = user_locks.get(user_id)
    if lock is None:
        lock = asyncio.Lock()
        user_locks[user_id] = lock

    if lock.locked():
        await query.answer("⏳ Телега размышляет, дай ей секунду... или минуту...")
        return

    async with lock:
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
            if player.state != 'idle':
                remaining = player.state_end_time - time.time()
                minutes = int(remaining // 60)
                seconds = int(remaining % 60)
                if player.state == 'dead':
                    await query.answer(f"Вы мертвы. Воскрешение через: {minutes} мин {seconds} сек.", show_alert=True)
                else:
                    await query.answer("Вы сейчас заняты и не можете начать бой!", show_alert=True)
                return
            
            enemy = generate_enemy(player.current_difficulty)
            is_win, log, result_msg = await run_combat_simulation(player, enemy)

            t_stats = get_total_stats(player)
            result_msg += f"\n❤️ Осталось здоровья: {player.hp:.1f}/{t_stats['max_hp']:.1f}, 💧 маны: {player.mp:.1f}/{t_stats['max_mp']:.1f}"

            if is_win:
                drop_chance_scaled = ITEM_DROP_CHANCE_FROM_ENEMY
                if random.random() < drop_chance_scaled:
                    item_type = random.choice(ITEM_TYPES)
                    rarity = max(1, player.current_difficulty * t_stats["luck"])
                    item = generate_item(item_type, rarity)
                    if len(player.inventory) < player.inv_slots:
                        player.inventory.append(item)
                        result_msg += f"\n\n📦 Выпал предмет: {item['name']}"
                    else:
                        result_msg += "\n\n📦 Предмет выпал, но инвентарь полон!"
    
                base_gold = GOLD_PER_STAGE * player.current_difficulty
                actual_gold = int(base_gold * enemy['strength_mult'] * t_stats["gold_mult"])
                
                player.gold += actual_gold
    
                result_msg += f"\n\n💰 Найдено золота: {actual_gold}, теперь у вас {player.gold}"

                # Дроп заклинания
                if enemy.get('spells') and random.random() < SPELL_DROP_CHANCE:
                    dropped = random.choice(enemy['spells']).copy()
                    if len(player.spell_inventory) < 20:
                        player.spell_inventory.append(dropped)
                        result_msg += f"\n\n📜 Вы получили заклинание: {dropped['name']}"
                    else:
                        result_msg += "\n\n📜 Инвентарь заклинаний полон!"

                if player.current_difficulty == player.max_unlocked_difficulty:
                    player.kills_on_max += 1
                    if player.kills_on_max >= KILLS_TO_UNLOCK_NEXT:
                        player.max_unlocked_difficulty += 1
                        player.kills_on_max = 0
                        result_msg += f"\n✨ Поздравляем! Открыта угроза уровня {player.max_unlocked_difficulty}!"

            elif "погибли" in result_msg:
                player.state = 'dead'
                player.state_end_time = time.time() + CONFIG["time_death"]

            for slot, item in player.equip.items():
                if item:
                    item['battle_count'] = item.get('battle_count', 0) + 1
                    if item['battle_count'] >= DUST_PER_BATTLE:
                        item['dust'] = item.get('dust', 0) + 1
                        item['battle_count'] -= DUST_PER_BATTLE
            
            await save_player(player)

            log_text = "\n".join(log)
            if len(log_text) > 3000:
                log_text = log_text[:1500] + \
                    "\n\n..... [БОЙ ДОЛГИЙ, ПРОПУСК ТЕКСТА] .....\n\n" + \
                    log_text[-1500:]

            # Сохраняем врага в кэш и создаём ключ (всегда, чтобы можно было посмотреть статистику)
            cache_key = f"{query.from_user.id}_{int(time.time())}_{random.randint(1000, 9999)}"
            enemy_cache[cache_key] = enemy
            asyncio.create_task(clear_enemy_cache(cache_key, 60))

            from aiogram.utils.keyboard import InlineKeyboardBuilder
            back_builder = InlineKeyboardBuilder()
            back_builder.button(
                text="⚔️ Снова в бой", callback_data=HuntCB(action="start").pack())
            back_builder.button(
                text="🔙 К охоте", callback_data=MenuCB(action="hunt").pack())
            back_builder.button(
                text="📊 Статистика бойцов",
                callback_data=CombatStatsCB(action="show", enemy_data=cache_key).pack()
            )
            back_builder.adjust(1, 2)

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


@dp.callback_query(CombatStatsCB.filter(F.action == "show"))
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

    text = "📊 <b>Подробная статистика бойцов</b>\n\n"
    text += "👤 <b>Ваши статы (с учётом экипировки):</b>\n"
    text += f"{STAT_EMOJI['hp']} Здоровье: {player.hp:.1f}/{t_stats['max_hp']:.1f} (+{t_stats['hp_regen']:.2f}/мин)\n"
    text += f"{STAT_EMOJI['m_shield']} МагЩит: {t_stats['m_shield']:.1f}\n"
    text += f"{STAT_EMOJI['mp']} Мана: {player.mp:.1f}/{t_stats['max_mp']:.1f} (+{t_stats['mp_regen']:.2f}/мин)\n"
    text += f"{STAT_EMOJI['atk']} Атака: {t_stats['atk']:.2f} | {STAT_EMOJI['magic_atk']} Маг.Атака: {t_stats['magic_atk']:.2f}\n"
    text += f"{STAT_EMOJI['def']} Защита: {t_stats['def']:.2f} | {STAT_EMOJI['magic_res']} Маг.Сопр.: {t_stats['magic_res']:.2f}\n"
    text += f"{STAT_EMOJI['crit_chance']} ШК: {t_stats['crit_chance']:.2f}% | {STAT_EMOJI['crit_damage']} КУ: {t_stats['crit_damage']:.2f}%\n"
    text += f"{STAT_EMOJI['magic_crit_chance']} МагШК: {t_stats['magic_crit_chance']:.2f}% | {STAT_EMOJI['magic_crit_damage']} МагКУ: {t_stats['magic_crit_damage']:.2f}%\n"
    text += f"{STAT_EMOJI['accuracy']} Точность: {t_stats['accuracy']:.2f} | {STAT_EMOJI['evasion_rating']} Уклонение: {t_stats['evasion_rating']:.2f}\n"
    text += f"{STAT_EMOJI['lifesteal']} Вампиризм: {t_stats['lifesteal']:.2f}% | {STAT_EMOJI['thorns']} Шипы: {t_stats['thorns']:.2f}%\n"
    text += f"{STAT_EMOJI['magic_shield_drain']} Ист.энергии: {t_stats['magic_shield_drain']:.2f}%\n"
    text += f"{STAT_EMOJI['armor_pen']} Пробитие: {t_stats['armor_pen']:.2f} | {STAT_EMOJI['atk_spd']} Ск.атаки: {t_stats['atk_spd']:.2f}\n"
    text += f"{STAT_EMOJI['gold_mult']} Мн.золота: x{t_stats['gold_mult']:.2f} | {STAT_EMOJI['adaptability']} Адаптивность: {t_stats['adaptability']:.3f}\n"
    text += f"{STAT_EMOJI['luck']} Удача: x{t_stats['luck']:.2f} | {STAT_EMOJI['talent']} Талант: x{t_stats['talent']:.2f}\n"
    text += f"{STAT_EMOJI['magic_efficiency']} Маг.Эффективность: {t_stats['magic_efficiency']:.2f}\n"
    text += f"{STAT_EMOJI['effect_resistance']} Сопр. эффектам: {t_stats['effect_resistance']:.2f}\n"
    text += "\n"

    text += "😡 <b>Статы врага:</b>\n"
    text += f"Класс: {enemy.get('class', 'Неизвестно')}\n"
    text += f"{STAT_EMOJI['hp']} Здоровье: {enemy['hp']:.1f}/{enemy['max_hp']:.1f}\n"
    text += f"{STAT_EMOJI['m_shield']} МагЩит: {enemy.get('m_shield', 0):.1f}\n"
    text += f"{STAT_EMOJI['atk']} Атака: {enemy['atk']:.2f} | {STAT_EMOJI['magic_atk']} Маг.Атака: {enemy['magic_atk']:.2f}\n"
    text += f"{STAT_EMOJI['def']} Защита: {enemy['def']:.2f} | {STAT_EMOJI['magic_res']} Маг.Сопр.: {enemy['magic_res']:.2f}\n"
    text += f"{STAT_EMOJI['accuracy']} Точность: {enemy['accuracy']:.2f} | {STAT_EMOJI['evasion_rating']} Уклонение: {enemy['evasion_rating']:.2f}\n"
    text += f"{STAT_EMOJI['crit_chance']} ШК: {enemy['crit_chance']:.1f}% | {STAT_EMOJI['crit_damage']} КУ: {enemy['crit_damage']:.1f}%\n"
    text += f"{STAT_EMOJI['magic_crit_chance']} МагШК: {enemy.get('magic_crit_chance', 0):.1f}% | {STAT_EMOJI['magic_crit_damage']} МагКУ: {enemy.get('magic_crit_damage', 150):.1f}%\n"
    text += f"{STAT_EMOJI['lifesteal']} Вампиризм: {enemy['lifesteal']:.1f}% | {STAT_EMOJI['thorns']} Шипы: {enemy['thorns']:.1f}%\n"
    text += f"{STAT_EMOJI['magic_shield_drain']} Ист.энергии: {enemy.get('magic_shield_drain', 0):.1f}%\n"
    text += f"{STAT_EMOJI['atk_spd']} Ск.атаки: {enemy['atk_spd']:.2f}\n"
    text += f"{STAT_EMOJI['effect_resistance']} Сопр. эффектам: {enemy.get('effect_resistance', 0):.1f}\n"
    text += f"{STAT_EMOJI['hp_regen']} Реген HP: {enemy['hp_regen']:.2f}/мин | {STAT_EMOJI['mp_regen']} Реген MP: {enemy['mp_regen']:.2f}/мин\n"

    await query.message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="🔙 Назад", callback_data=MenuCB(action="hunt").pack())]
    ]))
    await query.answer()

# ===================== ИНВЕНТАРЬ (предметы) =====================


@dp.callback_query(MenuCB.filter(F.action == "inv"))
async def menu_inv(query: CallbackQuery, callback_data: MenuCB):
    player = await get_player(query.from_user.id)
    text = f"💰 Золото: {player.gold}\n\n🎒 <b>Инвентарь ({len(player.inventory)}/{player.inv_slots})</b>\n\nЭкипировано:\n"

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    b = InlineKeyboardBuilder()

    all_items = []
    btn_index = 0

    order = EQUIP_ORDER
    for slot in order:
        item = player.equip.get(slot)
        slot_name = SLOT_RU.get(slot, slot)
        if item:
            text += f"{btn_index+1}. [{slot_name}] {item['name']}\n"
            b.button(text=f"{btn_index+1}", callback_data=ItemCB(action="view", idx=btn_index).pack())
            all_items.append({"data": item, "is_equip": True, "slot": slot, "real_idx": -1})
            btn_index += 1
        else:
            text += f"- [{slot_name}] Пусто\n"

    text += "\nВ сумке:\n"
    if not player.inventory:
        text += "Пусто\n"
    else:
        for real_idx, item in enumerate(player.inventory):
            item_type_ru = ITEM_TYPE_RU.get(item['item_type'], item['item_type'])
            text += f"{btn_index+1}. [{item_type_ru}] {item['name']}\n"
            b.button(text=f"{btn_index+1}", callback_data=ItemCB(action="view", idx=btn_index).pack())
            all_items.append({"data": item, "is_equip": False, "slot": None, "real_idx": real_idx})
            btn_index += 1

    b.adjust(5)
    b.row(InlineKeyboardButton(text="💰 Массовая продажа", callback_data=SellMassCB(action="menu").pack()))
    b.row(InlineKeyboardButton(text="🔙 Назад", callback_data=MenuCB(action="profile").pack()))

    await safe_edit(query.message, text, reply_markup=b.as_markup())


@dp.callback_query(ItemCB.filter(F.action == "view"))
async def view_item(query: CallbackQuery, callback_data: ItemCB):
    player = await get_player(query.from_user.id)
    idx = callback_data.idx

    text, reply_markup = await get_item_view_data(player, idx)
    if text is None:
        await query.answer("Предмет не найден!")
        return

    await safe_edit(query.message, text, reply_markup)


@dp.callback_query(ItemCB.filter(F.action == "choose_slot"))
async def choose_slot_for_equip(query: CallbackQuery, callback_data: ItemCB, state: FSMContext):
    player = await get_player(query.from_user.id)
    global_idx = callback_data.idx

    item, is_equip, slot_or_idx = get_item_by_global_index(player, global_idx)
    if not item or is_equip:
        await query.answer("Предмет не найден в инвентаре!")
        return

    allowed_slots = ITEM_TYPE_TO_SLOTS.get(item['item_type'], [])
    if not allowed_slots:
        await query.answer("Этот предмет нельзя надеть!")
        return

    # Сохраняем глобальный индекс для последующего выбора слота
    await state.update_data(item_global_idx=global_idx)

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    for slot in allowed_slots:
        slot_ru = {
            "right_hand": "Правая рука", "left_hand": "Левая рука", "boots": "Обувь",
            "belt": "Пояс", "robe": "Одежда", "helmet": "Голова",
            "amulet": "Амулет", "ring1": "Кольцо 1", "ring2": "Кольцо 2"
        }.get(slot, slot)
        builder.button(text=slot_ru, callback_data=EquipChoiceCB(
            item_idx=global_idx, slot=slot).pack())
    builder.button(text="❌ Отмена", callback_data=MenuCB(action="inv").pack())
    builder.adjust(1)
    await safe_edit(query.message, "Выберите слот для экипировки:", reply_markup=builder.as_markup())


@dp.callback_query(ItemCB.filter(F.action == "equip"))
async def equip_item_single_slot(query: CallbackQuery, callback_data: ItemCB):
    player = await get_player(query.from_user.id)
    global_idx = callback_data.idx

    # Получаем предмет по глобальному индексу (должен быть в инвентаре)
    item, is_equip, slot_or_idx = get_item_by_global_index(player, global_idx)
    if not item or is_equip:
        await query.answer("Предмет не найден в инвентаре!")
        return

    # item находится в инвентаре, slot_or_idx — его индекс в inventory
    inv_idx = slot_or_idx
    allowed_slots = ITEM_TYPE_TO_SLOTS.get(item['item_type'], [])
    if not allowed_slots:
        await query.answer("Этот предмет нельзя надеть!")
        return

    # Берём первый слот (для предметов с одним вариантом)
    slot = allowed_slots[0]
    # Проверяем возможность экипировки
    hands_used = ITEM_HANDS_USED.get(item['item_type'], 0)
    if hands_used == 2:
        if player.equip['right_hand'] is not None or player.equip['left_hand'] is not None:
            await query.answer("Для двуручного оружия обе руки должны быть свободны!", show_alert=True)
            return
    else:
        if player.equip[slot] is not None:
            await query.answer("Этот слот занят! Сначала снимите предмет.", show_alert=True)
            return
        if slot in ['right_hand', 'left_hand']:
            other_hand = 'left_hand' if slot == 'right_hand' else 'right_hand'
            if player.equip[other_hand] is not None:
                other_item = player.equip[other_hand]
                if ITEM_HANDS_USED.get(other_item['item_type'], 0) == 2:
                    await query.answer("Нельзя надеть одноручное оружие, пока в другой руке двуручное!", show_alert=True)
                    return

    # Снимаем старый предмет, если есть
    old_item = player.equip[slot]
    if old_item:
        if len(player.inventory) >= player.inv_slots:
            await query.answer("Нет места в инвентаре для снятого предмета!", show_alert=True)
            return
        player.inventory.append(old_item)

    # Экипируем новый предмет
    player.equip[slot] = item
    # Удаляем предмет из инвентаря по его индексу
    player.inventory.pop(inv_idx)

    # Если предмет двуручный, занимаем и вторую руку
    if hands_used == 2:
        other = 'left_hand' if slot == 'right_hand' else 'right_hand'
        player.equip[other] = item

    await save_player(player)
    await query.answer(f"Экипировано в {slot}!")
    await menu_inv(query, MenuCB(action="inv"))


@dp.callback_query(EquipChoiceCB.filter())
async def equip_to_slot(query: CallbackQuery, callback_data: EquipChoiceCB):
    player = await get_player(query.from_user.id)
    global_idx = callback_data.item_idx
    slot = callback_data.slot

    item, is_equip, slot_or_idx = get_item_by_global_index(player, global_idx)
    if not item or is_equip:
        await query.answer("Предмет не найден в инвентаре!")
        return

    inv_idx = slot_or_idx  # индекс в inventory

    # Проверяем, разрешён ли слот для этого типа предмета
    allowed = ITEM_TYPE_TO_SLOTS.get(item['item_type'], [])
    if slot not in allowed:
        await query.answer("Этот предмет нельзя надеть в выбранный слот!", show_alert=True)
        return

    hands_used = ITEM_HANDS_USED.get(item['item_type'], 0)
    if hands_used == 2:
        if player.equip['right_hand'] is not None or player.equip['left_hand'] is not None:
            await query.answer("Для двуручного оружия обе руки должны быть свободны!", show_alert=True)
            return
    else:
        if player.equip[slot] is not None:
            await query.answer("Этот слот занят! Сначала снимите предмет.", show_alert=True)
            return
        if slot in ['right_hand', 'left_hand']:
            other_hand = 'left_hand' if slot == 'right_hand' else 'right_hand'
            if player.equip[other_hand] is not None:
                other_item = player.equip[other_hand]
                if ITEM_HANDS_USED.get(other_item['item_type'], 0) == 2:
                    await query.answer("Нельзя надеть одноручное оружие, пока в другой руке двуручное!", show_alert=True)
                    return

    old_item = player.equip[slot]
    if old_item:
        player.inventory.append(old_item)

    player.equip[slot] = item
    player.inventory.pop(inv_idx)

    await save_player(player)
    await query.answer(f"Экипировано в {slot}!")
    await menu_inv(query, MenuCB(action="inv"))


@dp.callback_query(ItemCB.filter(F.action == "unequip"))
async def uneq_item(query: CallbackQuery, callback_data: ItemCB):
    player = await get_player(query.from_user.id)
    global_idx = callback_data.idx

    item, is_equip, slot_or_idx = get_item_by_global_index(player, global_idx)
    if not item or not is_equip:
        await query.answer("Предмет не экипирован.")
        return

    slot = slot_or_idx
    if len(player.inventory) < player.inv_slots:
        player.inventory.append(item)
        player.equip[slot] = None
        await save_player(player)
        await query.answer("Предмет снят!")
        await menu_inv(query, MenuCB(action="inv"))
    else:
        await query.answer("В инвентаре нет места!", show_alert=True)


@dp.callback_query(ItemCB.filter(F.action == "sell"))
async def sell_item(query: CallbackQuery, callback_data: ItemCB):
    player = await get_player(query.from_user.id)
    global_idx = callback_data.idx

    item, is_equip, slot_or_idx = get_item_by_global_index(player, global_idx)
    if not item or is_equip:
        await query.answer("Предмет не найден в инвентаре!")
        return

    inv_idx = slot_or_idx
    earn = item.get("sell_price", 10)
    player.gold += earn
    player.inventory.pop(inv_idx)
    await save_player(player)
    await query.answer(f"Продано за {earn} золота.")
    await menu_inv(query, MenuCB(action="inv"))


@dp.callback_query(ItemCB.filter(F.action == "upg"))
async def upg_item(query: CallbackQuery, callback_data: ItemCB):
    player = await get_player(query.from_user.id)
    global_idx = callback_data.idx
    stat_key = callback_data.stat

    item, is_equip, slot_or_idx = get_item_by_global_index(player, global_idx)
    if not item or stat_key not in item["stats"]:
        return

    s_data = item["stats"][stat_key]
    raw_cost = GOLD_PER_STAGE * 25 * player.max_unlocked_difficulty * s_data.get('upgrade_price_mult', 1.0)
    upg_cost = max(100, int(raw_cost))

    if player.gold >= upg_cost:
        player.gold -= upg_cost
        s_data['upgrades'] += 1
        s_data['current'] = s_data['base'] * (s_data['upgrades'] + 1)
        item['sell_price'] += int(upg_cost * 0.3)

        await save_player(player)
        await query.answer("Характеристика улучшена!")

        updated_player = await get_player(query.from_user.id)
        text, reply_markup = await get_item_view_data(updated_player, global_idx)
        if text:
            await safe_edit(query.message, text, reply_markup)
        else:
            await menu_inv(query, MenuCB(action="inv"))
    else:
        await query.answer("Недостаточно золота!", show_alert=True)

def recalc_sell_price(item):
    base_price = 0
    for st, st_data in item["stats"].items():
        is_perc = st in PERCENT_STATS
        base_price += int(st_data["base"] * (100 if is_perc else 10))
    item["sell_price"] = max(10, int(base_price * 0.25))

@dp.callback_query(ItemCB.filter(F.action == "reroll"))
async def reroll_item(query: CallbackQuery, callback_data: ItemCB):
    player = await get_player(query.from_user.id)
    global_idx = callback_data.idx
    old_stat_key = callback_data.stat

    item, is_equip, slot_or_idx = get_item_by_global_index(player, global_idx)
    if not item:
        await query.answer("Предмет не найден!")
        return

    dust = item.get('dust', 0)
    if dust < 1:
        await query.answer("Недостаточно пыли душ!", show_alert=True)
        return

    rarity = item['rarity']
    item_type = item['item_type']

    # Определяем, является ли стат гарантированным для оружия
    is_guaranteed = False
    if item_type in PHYSICAL_WEAPON_TYPES and old_stat_key == 'atk':
        is_guaranteed = True
    elif item_type in MAGICAL_WEAPON_TYPES and old_stat_key == 'magic_atk':
        is_guaranteed = True

    if is_guaranteed:
        # Перегенерируем этот же стат
        new_stat_key = old_stat_key
    else:
        # Ищем доступные другие статы
        allowed_all = ITEM_ALLOWED_STATS.get(item_type, [])
        if not allowed_all:
            allowed_all = list(STAT_RU.keys())
        current_stats = set(item['stats'].keys())
        current_stats.discard(old_stat_key)
        available = [s for s in allowed_all if s not in current_stats]
        if not available:
            await query.answer("Нет других доступных статов для этого предмета!", show_alert=True)
            return
        new_stat_key = random.choice(available)

    # Генерируем новый стат
    new_stat_data = generate_single_stat(new_stat_key, item_type, rarity)

    # Удаляем старый стат и добавляем новый (даже если ключ тот же)
    del item['stats'][old_stat_key]
    item['stats'][new_stat_key] = new_stat_data

    # Пересчитываем sell_price
    recalc_sell_price(item)

    # Тратим пыль
    item['dust'] = dust - 1

    await save_player(player)

    await query.answer(f"Стат изменён на {STAT_RU.get(new_stat_key, new_stat_key)}!")

    # Обновляем отображение предмета
    updated_player = await get_player(query.from_user.id)
    text, reply_markup = await get_item_view_data(updated_player, global_idx)
    if text:
        await safe_edit(query.message, text, reply_markup)
    else:
        await menu_inv(query, MenuCB(action="inv"))

@dp.callback_query(ItemCB.filter(F.action == "upgrade_rarity"))
async def upgrade_item_rarity(query: CallbackQuery, callback_data: ItemCB):
    player = await get_player(query.from_user.id)
    global_idx = callback_data.idx
    item, is_equip, slot_or_idx = get_item_by_global_index(player, global_idx)
    if not item:
        await query.answer("Предмет не найден!")
        return
    dust = item.get('dust', 0)
    if dust < 1:
        await query.answer("Недостаточно пыли душ!", show_alert=True)
        return
    # Увеличиваем редкость
    t_stats = get_total_stats(player)
    talent = t_stats.get('talent', 1.0)
    item['rarity'] = item.get('rarity', 1.0) + 1 * talent
    item['dust'] = dust - 1
    # Пересчитываем базовые статы
    for stat_key, stat_data in item['stats'].items():
        factor = stat_data.get('factor')
        if factor is None:
            # Для старых предметов (если вдруг) пропускаем
            continue
        new_base = item['rarity'] * factor
        #integer_stats = ["atk", "def", "max_hp", "max_mp", "magic_atk", "magic_res", "armor_pen", "m_shield"]
        #if stat_key in integer_stats:
        #    new_base = max(0.5, round(new_base, 2))
        #else:
        new_base = max(0.01, round(new_base, 2))
        stat_data['base'] = new_base
        stat_data['current'] = new_base * (stat_data.get('upgrades', 0) + 1)
    
    recalc_sell_price(item)
    
    await save_player(player)
    
    updated_player = await get_player(query.from_user.id)
    text, reply_markup = await get_item_view_data(updated_player, global_idx)
    if text:
        await safe_edit(query.message, text, reply_markup)
    else:
        await menu_inv(query, MenuCB(action="inv"))

@dp.callback_query(SellMassCB.filter(F.action == "menu"))
async def sell_mass_menu(query: CallbackQuery, callback_data: SellMassCB):
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    builder.button(text="Продать всё",
                   callback_data=SellMassCB(action="all").pack())
    builder.button(text="Продать по цене",
                   callback_data=SellMassCB(action="price").pack())
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
    for item in player.inventory[:]:
        total += item['sell_price']
        sold_items.append(item['name'])
        player.inventory.remove(item)
    player.gold += total
    await save_player(player)
    sold_list = "\n".join(sold_items) if sold_items else "ничего"
    await safe_edit(query.message,
                    f"💰 Продано:\n{sold_list}\n\nПолучено: 💰 {total} золота.\nТеперь у вас 💰 {player.gold} золота.",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(
                            text="🔙 В инвентарь", callback_data=MenuCB(action="inv").pack())]
                    ]))


@dp.callback_query(SellMassCB.filter(F.action == "price"))
async def sell_mass_price(query: CallbackQuery, callback_data: SellMassCB, state: FSMContext):
    await query.message.answer("Введите максимальную цену предмета (число, всё ниже этой цены будет продано):")
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
                                 [InlineKeyboardButton(
                                     text="🔙 В инвентарь", callback_data=MenuCB(action="inv").pack())]
                             ]))
    await state.clear()

# ===================== МАГАЗИН =====================

@dp.callback_query(MenuCB.filter(F.action == "shop"))
async def menu_shop(query: CallbackQuery, callback_data: MenuCB):
    player = await get_player(query.from_user.id)
    await update_shop(player)

    text = f"💰 Золото: {player.gold}\n🏪 <b>Магазин (обновляется каждые 5 мин)</b>\n\n📦 Ассортимент:\n"

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    b = InlineKeyboardBuilder()

    items_with_idx = [(i, entry) for i, entry in enumerate(
        player.shop_assortment) if not entry["sold"]]
    items_with_idx.sort(key=lambda x: (
        x[1]['item']['item_type'], x[1]['item']['name']))

    btn_num = 1
    for original_idx, entry in items_with_idx:
        it = entry["item"]
        item_type_ru = ITEM_TYPE_RU.get(it['item_type'], it['item_type'])
        stat_desc = "\n".join(
            [f"{STAT_EMOJI.get(k, '')}      {STAT_RU.get(k, k)}: {fmt_float(v['base'], 3)}" for k, v in it['stats'].items()])
        price = entry["price"]
        text += f"\n{btn_num}. [{item_type_ru}] {it['name']}:\n{stat_desc}\nСтоимость: 💰 {price}\n"
        b.button(text=f"{btn_num}", callback_data=ShopCB(
            action="buy_it", idx=original_idx).pack())
        btn_num += 1

    b.adjust(5)
    
    if player.state == 'dead':
        cost = GOLD_PER_STAGE * 25 * player.max_unlocked_difficulty
        b.row(InlineKeyboardButton(text=f"💀 Воскреситься (💰 {cost})", callback_data=ShopCB(action="revive").pack()))

    b.row(InlineKeyboardButton(text="🔙 Назад",
          callback_data=MenuCB(action="profile").pack()))

    await safe_edit(query.message, text, reply_markup=b.as_markup())


@dp.callback_query(ShopCB.filter())
async def process_shop(query: CallbackQuery, callback_data: ShopCB):
    player = await get_player(query.from_user.id)
    act = callback_data.action

    if act == "buy_it":
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
    elif act == "revive":
        if player.state == 'dead':
            cost = GOLD_PER_STAGE * 25 * player.max_unlocked_difficulty
            if player.gold >= cost:
                player.gold -= cost
                t_stats = get_total_stats(player)
                player.hp = t_stats['max_hp']
                player.state = 'idle'
                player.state_end_time = 0
                await save_player(player)
                await query.answer("✨ Вы воскресли!", show_alert=True)
                # Обновляем меню магазина
                await menu_shop(query, MenuCB(action="shop"))
            else:
                await query.answer(f"❌ Недостаточно золота! Нужно {cost}.", show_alert=True)
        else:
            await query.answer("💚 Вы живы, воскрешение не требуется.", show_alert=True)

# ===================== ЛАВКА ЗЕЛИЙ =====================

@dp.callback_query(MenuCB.filter(F.action == "potions"))
async def menu_potions(query: CallbackQuery, callback_data: MenuCB):
    player = await get_player(query.from_user.id)
    await update_potion_shop(player)

    t_stats = get_total_stats(player)
    total_adapt = t_stats['adaptability']

    text = f"💰 Золото: {player.gold}\n🧪 <b>Лавка зелий (обновляется каждые 2 мин)</b>\n\nАссортимент:\n"

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    b = InlineKeyboardBuilder()

    idx = 1
    for i, entry in enumerate(player.potion_shop_assortment):
        if entry["sold"]:
            continue
        pot = entry["potion"]
        stat = pot["stat"]
        base_val = pot["value"]
        pot_type = pot["type"]

        # Текущее финальное значение
        current_val = t_stats[stat]

        # Получаем компоненты для симуляции будущего значения
        base, flat, percent = get_stat_components(player, stat)

        unit = '%' if pot_type == 'percent' else ''
        if stat == "adaptability":
            display = base_val
            if pot_type == 'percent':
                new_percent = percent + base_val
                future_val = (base + flat) * (1 + new_percent / 100.0)
            else:
                new_base = base + base_val
                future_val = (new_base + flat) * (1 + percent / 100.0)
        else:
            display = base_val * total_adapt
            if pot_type == 'percent':
                new_percent = percent + base_val * total_adapt
                future_val = (base + flat) * (1 + new_percent / 100.0)
            else:
                new_base = base + base_val * total_adapt
                future_val = (new_base + flat) * (1 + percent / 100.0)

        text += f"{idx}. {STAT_EMOJI.get(stat, '')} {STAT_RU[stat]} +{fmt_float(display)}{unit} ({fmt_float(current_val)} → {fmt_float(future_val)}) — 💰 {pot['price']}\n"
        b.button(text=f"{idx}", callback_data=PotionCB(action="buy", idx=i).pack())
        idx += 1

    b.adjust(5)
    # строка с кнопкой обновления удалена
    b.row(InlineKeyboardButton(text="🔙 Назад",
          callback_data=MenuCB(action="profile").pack()))

    await safe_edit(query.message, text, reply_markup=b.as_markup())


@dp.callback_query(PotionCB.filter())
async def process_potions(query: CallbackQuery, callback_data: PotionCB):
    player = await get_player(query.from_user.id)
    act = callback_data.action

    if act == "buy":
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
            stat = pot["stat"]
            t_stats = get_total_stats(player)
            total_adapt = t_stats['adaptability']
            if pot["type"] == "percent":
                # Процентное зелье
                if stat == "adaptability":
                    player.percent_bonus[stat] += pot["value"]
                else:
                    player.percent_bonus[stat] += pot["value"] * total_adapt
            else:
                # Аддитивное зелье
                if stat == "adaptability":
                    player.base_stats[stat] += pot["value"]
                else:
                    player.base_stats[stat] += pot["value"] * total_adapt
            entry["sold"] = True
            await save_player(player)
            await query.answer(f"Вы выпили зелье! {STAT_RU[stat]} увеличен.")
            await menu_potions(query, MenuCB(action="potions"))
        else:
            await query.answer("Недостаточно золота!", show_alert=True)

# ===================== ЭКСПЕДИЦИЯ =====================

@dp.callback_query(MenuCB.filter(F.action == "exped"))
async def menu_exped(query: CallbackQuery, callback_data: MenuCB):
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    b = InlineKeyboardBuilder()
    b.button(text="Отправиться (20 мин)",
             callback_data=ActionCB(action="start_exped").pack())
    b.button(text="🔙 Назад", callback_data=MenuCB(action="profile").pack())
    b.adjust(1)
    await safe_edit(query.message,
                    f"💰 Золото: {(await get_player(query.from_user.id)).gold}\n🧭 <b>Экспедиция</b>\nБезопасный поиск золота и ресурсов. Вы не сможете сражаться или тренироваться 20 минут.\n"
                    "Шанс найти несколько предметов!",
                    reply_markup=b.as_markup())


@dp.callback_query(ActionCB.filter(F.action == "start_exped"))
async def start_exped(query: CallbackQuery, callback_data: ActionCB):
    player = await get_player(query.from_user.id)
    if player.state != 'idle':
        await query.answer("Вы сейчас заняты!", show_alert=True)
        return
    player.state = 'expedition'
    player.state_end_time = time.time() + CONFIG["time_expedition"]
    await save_player(player)
    await safe_edit(query.message,
                    "Вы отправились в экспедицию.",
                    reply_markup=waiting_kbd(player.state_end_time))



@dp.callback_query(SpellCB.filter(F.action == "view"))
async def view_spell(query: CallbackQuery, callback_data: SpellCB):
    player = await get_player(query.from_user.id)
    idx = callback_data.idx
    if idx >= len(player.spell_inventory):
        await query.answer("Заклинание не найдено!")
        return
    spell = player.spell_inventory[idx]
    
    t_stats = get_total_stats(player)
    talent = t_stats.get('talent', 1.0)
    
    current_cooldown = spell['base_cooldown'] * ((1 - 0.1 * talent) ** spell.get('cooldown_upgrades', 0))

    text = f"✨ <b>{spell['name']}</b>\n"
    text += f"\n📖 Описание:\n"
    for i, eff in enumerate(spell['effects']):
        target = "на себя" if eff['target'] == TARGET_SELF else "на врага"
        line = f"  {i+1}. "
        if eff['type'] == 'damage':
            total_damage = eff['base_value'] + t_stats['magic_atk']
            line += f"Наносит {total_damage:.1f} магического урона {target} (база {eff['base_value']:.1f} + маг.атака)"
        elif eff['type'] == 'heal':
            line += f"Лечит {eff['base_value']:.1f} HP {target}"
        elif eff['type'] == 'dot':
            line += f"Наносит {eff['base_value']:.1f} урона каждые {eff['interval']}с {target}"
        elif eff['type'] == 'hot':
            line += f"Лечит {eff['base_value']:.1f} HP каждые {eff['interval']}с {target}"
        elif eff['type'] == 'buff':
            line += f"Увеличивает {STAT_RU.get(eff['stat'], eff['stat'])} на {eff['base_value']*100:.1f}% {target}"
        elif eff['type'] == 'debuff':
            line += f"Уменьшает {STAT_RU.get(eff['stat'], eff['stat'])} на {eff['base_value']*100:.1f}% {target}"
        elif eff['type'] == 'shield':
            line += f"Даёт {eff['base_value']:.2f} магического щита {target}"
        elif eff['type'] == 'time_stop':
            line += f"Останавливает время на {eff['duration']:.1f}с {target}"
        elif eff['type'] == 'mp_restore':
            line += f"Восстанавливает {eff['base_value']:.1f} маны {target}"
        elif eff['type'] == 'mp_burn':
            total_burn = eff['base_value'] + t_stats['magic_atk']
            line += f"Сжигает {total_burn:.1f} маны {target} (база {eff['base_value']:.1f} + маг.атака)"
        text += line + "\n"
    
    magic_eff = t_stats.get('magic_efficiency', 0.0)
    cost_mult = 99 / (magic_eff + 99)
    actual_cost = max(1, int(spell["mp_cost"] * cost_mult + 0.5))
    
    text += f"\n💧 Стоимость маны: {actual_cost}\n"
    text += f"⏱ Перезарядка: {fmt_float(current_cooldown, 5)}с\n"
    text += f"🃏 Аркан: {spell.get('arcane', 0)} (прогресс: {spell.get('arcane_progress', 0)}/20)\n"
    text += f"\n📈 Всего улучшений: {spell.get('upgrades', 0)}\n"

    # Легенда для кнопок улучшений
    text += "\n<b>Улучшения (тратят 🃏5):</b>\n"
    text += "💥 — увеличение значения на 10%\n"
    text += "⚡ — уменьшение интервала на 10%\n"
    text += "⏱ — увеличение длительности на 10%\n"
    text += "⏱️ — уменьшение перезарядки на 10%\n"

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    b = InlineKeyboardBuilder()

    # Кнопки для улучшения каждого эффекта (все кнопки одного эффекта на одной строке)
    for i, eff in enumerate(spell['effects']):
        buttons = get_effect_upgrade_buttons(eff, i, idx, -1)
        if buttons:
            b.row(*buttons)

    # Кнопка для улучшения перезарядки (отдельная строка)
    b.row(InlineKeyboardButton(
        text=f"⏱️ Перезарядка -10% (🃏5)",
        callback_data=SpellEffectCB(action="upgrade", spell_idx=idx, effect_idx=-1, param="cooldown", slot=-1).pack()
    ))
    
    # Нижние кнопки
    b.row(
        InlineKeyboardButton(text="🔙 Назад", callback_data=MenuCB(action="spells").pack()),
        InlineKeyboardButton(text="🗑 Выбросить", callback_data=SpellCB(action="discard", idx=idx).pack()),
        InlineKeyboardButton(text="Экипировать", callback_data=SpellCB(action="equip", idx=idx).pack())
    )

    await safe_edit(query.message, text, reply_markup=b.as_markup())


@dp.callback_query(SpellCB.filter(F.action == "equip"))
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
        b.button(text=slot_name, callback_data=SpellCB(
            action="equip_slot", idx=idx, slot=slot).pack())
    b.button(text="❌ Отмена", callback_data=MenuCB(action="spells").pack())
    b.adjust(1)

    await safe_edit(query.message, "Выберите слот для экипировки:", reply_markup=b.as_markup())


@dp.callback_query(SpellCB.filter(F.action == "equip_slot"))
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

    t_stats = get_total_stats(player)
    talent = t_stats.get('talent', 1.0)

    text = f"🃏 <b>{spell['name']}</b> (активный слот {slot+1})\n"
    text += f"📖 Описание:\n"
    for i, eff in enumerate(spell['effects']):
        target = "на себя" if eff['target'] == TARGET_SELF else "на врага"
        line = f"  {i+1}. "
        if eff['type'] == 'damage':
            total_damage = eff['base_value'] + t_stats['magic_atk']
            line += f"Наносит {total_damage:.1f} магического урона {target} (база {eff['base_value']:.1f} + маг.атака)"
        elif eff['type'] == 'heal':
            line += f"Лечит {eff['base_value']:.1f} HP {target}"
        elif eff['type'] == 'dot':
            line += f"Наносит {eff['base_value']:.1f} урона каждые {eff['interval']}с {target}"
        elif eff['type'] == 'hot':
            line += f"Лечит {eff['base_value']:.1f} HP каждые {eff['interval']}с {target}"
        elif eff['type'] == 'buff':
            line += f"Увеличивает {STAT_RU.get(eff['stat'], eff['stat'])} на {eff['base_value']*100:.1f}% {target}"
        elif eff['type'] == 'debuff':
            line += f"Уменьшает {STAT_RU.get(eff['stat'], eff['stat'])} на {eff['base_value']*100:.1f}% {target}"
        elif eff['type'] == 'shield':
            line += f"Даёт {eff['base_value']:.2f} магического щита {target}"
        elif eff['type'] == 'time_stop':
            line += f"Останавливает время на {eff['duration']:.1f}с {target}"
        elif eff['type'] == 'mp_restore':
            line += f"Восстанавливает {eff['base_value']:.1f} маны {target}"
        elif eff['type'] == 'mp_burn':
            total_burn = eff['base_value'] + t_stats['magic_atk']
            line += f"Сжигает {total_burn:.1f} маны {target} (база {eff['base_value']:.1f} + маг.атака)"
        text += line + "\n"
    
    magic_eff = t_stats.get('magic_efficiency', 0.0)
    cost_mult = 99 / (magic_eff + 99)
    actual_cost = max(1, int(spell["mp_cost"] * cost_mult + 0.5))
    
    text += f"\n💧 Стоимость маны: {actual_cost}\n"
    current_cooldown = spell['base_cooldown'] * ((1 - 0.1 * talent) ** spell.get('cooldown_upgrades', 0))
    text += f"⏱ Перезарядка: {fmt_float(current_cooldown, 5)}с\n"
    text += f"🃏 Аркан: {spell.get('arcane', 0)} (прогресс: {spell.get('arcane_progress', 0)}/20)\n"
    text += f"\nВсего улучшений: {spell.get('upgrades', 0)}\n"

    # Легенда для кнопок улучшений
    text += "\n<b>Улучшения (тратят 🃏5):</b>\n"
    text += "💥 — увеличение значения на 10%\n"
    text += "⚡ — уменьшение интервала на 10%\n"
    text += "⏱ — увеличение длительности на 10%\n"
    text += "⏱️ — уменьшение перезарядки на 10%\n"

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    b = InlineKeyboardBuilder()

    # Кнопки для улучшения каждого эффекта (все кнопки одного эффекта на одной строке)
    for i, eff in enumerate(spell['effects']):
        buttons = get_effect_upgrade_buttons(eff, i, -1, slot)
        if buttons:
            b.row(*buttons)

    # Кнопка для улучшения перезарядки
    b.row(InlineKeyboardButton(
        text=f"⏱️ Перезарядка -10% (🃏5)",
        callback_data=SpellEffectCB(action="upgrade", spell_idx=-1, effect_idx=-1, param="cooldown", slot=slot).pack()
    ))
    
    # Нижние кнопки
    b.row(
        InlineKeyboardButton(text="🔙 Назад", callback_data=MenuCB(action="spells").pack()),
        InlineKeyboardButton(text="Снять", callback_data=SpellCB(action="unequip", idx=slot, slot=slot).pack())
    )

    await safe_edit(query.message, text, reply_markup=b.as_markup())
    
def get_effect_upgrade_buttons(effect, effect_idx, spell_idx, slot):
    buttons = []
    if effect['type'] in ['damage', 'heal', 'shield', 'mp_restore', 'mp_burn']:
        buttons.append(InlineKeyboardButton(
            text=f"💥 Сила +10% (🃏5)",
            callback_data=SpellEffectCB(action="upgrade", spell_idx=spell_idx, effect_idx=effect_idx, param="value", slot=slot).pack()
        ))
    elif effect['type'] in ['dot', 'hot']:
        buttons.append(InlineKeyboardButton(
            text=f"💥 Урон/лечение +10% (🃏5)",
            callback_data=SpellEffectCB(action="upgrade", spell_idx=spell_idx, effect_idx=effect_idx, param="value", slot=slot).pack()
        ))
        buttons.append(InlineKeyboardButton(
            text=f"⚡ Интервал -10% (🃏5)",
            callback_data=SpellEffectCB(action="upgrade", spell_idx=spell_idx, effect_idx=effect_idx, param="interval", slot=slot).pack()
        ))
    elif effect['type'] in ['buff', 'debuff']:
        buttons.append(InlineKeyboardButton(
            text=f"💥 Эффект +10% (🃏5)",
            callback_data=SpellEffectCB(action="upgrade", spell_idx=spell_idx, effect_idx=effect_idx, param="value", slot=slot).pack()
        ))
    elif effect['type'] == 'time_stop':
        buttons.append(InlineKeyboardButton(
            text=f"⏱ Длительность +10% (🃏5)",
            callback_data=SpellEffectCB(action="upgrade", spell_idx=spell_idx, effect_idx=effect_idx, param="duration", slot=slot).pack()
        ))
    return buttons

@dp.callback_query(SpellEffectCB.filter(F.action == "upgrade"))
async def upgrade_spell_effect(query: CallbackQuery, callback_data: SpellEffectCB):
    player = await get_player(query.from_user.id)
    t_stats = get_total_stats(player)
    talent = t_stats.get('talent', 1.0)                     # <-- получили талант
    cost = 5

    if callback_data.slot != -1:
        slot = callback_data.slot
        if slot < 0 or slot >= 5:
            await query.answer("Неверный слот")
            return
        spell = player.active_spells[slot]
        source = "slot"
        source_id = slot
    else:
        idx = callback_data.spell_idx
        if idx >= len(player.spell_inventory):
            await query.answer("Заклинание не найдено!")
            return
        spell = player.spell_inventory[idx]
        source = "inventory"
        source_id = idx

    if not spell:
        await query.answer("Заклинание не найдено")
        return

    effect_idx = callback_data.effect_idx
    param = callback_data.param

    if spell.get('arcane', 0) < cost:
        await query.answer(f"Недостаточно аркан! Нужно {cost}, у вас {spell.get('arcane', 0)}", show_alert=True)
        return

    # Улучшение кулдауна (effect_idx == -1)
    if effect_idx == -1:
        if param != "cooldown":
            await query.answer("Неверный параметр")
            return
        spell['cooldown_upgrades'] = spell.get('cooldown_upgrades', 0) + 1
        spell['upgrades'] = spell.get('upgrades', 0) + 1
        base_mp = spell.get('base_mp_cost', spell['mp_cost'])
        spell['mp_cost'] = int(base_mp * (1 + 0.1 * spell['upgrades']))
        spell['arcane'] -= cost
        await save_player(player)
        if source == "inventory":
            await view_spell(query, SpellCB(action="view", idx=source_id))
        else:
            await view_active_spell(query, SpellCB(action="view_slot", idx=source_id, slot=source_id))
        return

    # Обычное улучшение эффекта
    if effect_idx >= len(spell['effects']):
        await query.answer("Эффект не найден")
        return

    eff = spell['effects'][effect_idx]

    # Применяем улучшение с учётом таланта
    if param == "value":
        eff['base_value'] *= (1 + ARCANE_GEOMETRIC_MULT * talent) # увеличение на 10% * талант
    elif param == "interval" and 'interval' in eff:
        eff['interval'] *= (1 - ARCANE_GEOMETRIC_MULT * talent)   # уменьшение на 10% * талант
    elif param == "duration" and 'duration' in eff:
        eff['duration'] *= (1 + ARCANE_GEOMETRIC_MULT * talent)   # увеличение на 10% * талант
    else:
        await query.answer("Неизвестный параметр")
        return

    spell['upgrades'] = spell.get('upgrades', 0) + 1
    base_mp = spell.get('base_mp_cost', spell['mp_cost'])
    spell['mp_cost'] = base_mp * (1 + 0.1 * spell['upgrades'])
    spell['arcane'] -= cost

    await save_player(player)

    if source == "inventory":
        await view_spell(query, SpellCB(action="view", idx=source_id))
    else:
        await view_active_spell(query, SpellCB(action="view_slot", idx=source_id, slot=source_id))


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

@dp.callback_query(MenuCB.filter(F.action == "spells"))
async def menu_spells(query: CallbackQuery, callback_data: MenuCB):
    player = await get_player(query.from_user.id)

    text = f"🔮 <b>Магия</b>\n\nАктивные слоты (5):\n"
    from aiogram.types import InlineKeyboardButton
    from aiogram.utils.keyboard import InlineKeyboardBuilder

    slot_buttons = []
    # Активные слоты
    for i, spell in enumerate(player.active_spells):
        if spell:
            emoji = get_spell_emoji(spell)
            arcane = spell.get('arcane', 0)
            arcane_str = f" 🃏{arcane}" if arcane > 0 else ""
            text += (f"Слот {i+1}: {emoji} <b>{spell['name']}</b>{arcane_str} "
                     f"(💧 МП: {spell['mp_cost']} | ⏳ КД: {spell['base_cooldown']:.1f}с | Улучшено {spell['upgrades']})\n")
            slot_buttons.append(
                InlineKeyboardButton(
                    text=f"Слот {i+1}",
                    callback_data=SpellCB(action="view_slot", idx=i, slot=i).pack()
                )
            )
        else:
            text += f"Слот {i+1}: Пусто\n"

    text += f"\n📚 Инвентарь заклинаний ({len(player.spell_inventory)}/20):\n"

    inv_buttons = []
    for i, spell in enumerate(player.spell_inventory):
        emoji = get_spell_emoji(spell)
        passive = " ♾️" if spell.get('is_passive') else ""
        arcane = spell.get('arcane', 0)
        arcane_str = f" 🃏{arcane}" if arcane > 0 else ""
        text += (f"{i+1}. {emoji} <b>{spell['name']}</b>{passive}{arcane_str} | "
                 f"💧 МП: {spell['mp_cost']} | ⏳ КД: {spell['base_cooldown']:.1f}с\n")
        inv_buttons.append(
            InlineKeyboardButton(
                text=f"{i+1}",
                callback_data=SpellCB(action="view", idx=i).pack()
            )
        )

    if not player.spell_inventory:
        text += "Пусто"

    # Построение клавиатуры
    keyboard_rows = []
    if slot_buttons:
        keyboard_rows.append(slot_buttons)  # ряд слотов
    # ряд(ы) инвентаря по 5 кнопок
    for i in range(0, len(inv_buttons), 5):
        keyboard_rows.append(inv_buttons[i:i+5])
    # кнопка назад
    keyboard_rows.append([
        InlineKeyboardButton(text="🔙 Назад", callback_data=MenuCB(action="profile").pack())
    ])

    from aiogram.types import InlineKeyboardMarkup
    markup = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)

    await safe_edit(query.message, text, reply_markup=markup)


@dp.callback_query(SpellCB.filter(F.action == "discard"))
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
    asyncio.create_task(leaderboard_updater())
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
