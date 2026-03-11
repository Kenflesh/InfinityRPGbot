import os
from dotenv import load_dotenv

load_dotenv()

# --- ТЕХНИЧЕСКИЕ ---
BOT_TOKEN = os.getenv("BOT_TOKEN", "ВСТАВЬ_СЮДА_ТОКЕН_ОТ_BOTFATHER")
DB_NAME = "rpg_game.db"

# --- БАЛАНС ИГРЫ ---
TRAINING_BASE_COST = 100
TRAINING_COST_STEP = 50
TRAINING_TIME_SECONDS = 600  # 10 минут

DEATH_LOCK_TIME = 3600  # 1 час
COMBAT_LOG_LIMIT = 10

SHOP_REFRESH_TIME = 600  # 10 минут
SHOP_SLOTS_COUNT = 5

BASE_INVENTORY_SLOTS = 10
SLOT_UPGRADE_COST = 500

# Характеристики с русскими названиями
BASE_STATS = {
    "hp": 100,
    "mana": 50,
    "dmg": 10,
    "def": 5,
    "crit_chance": 5,
    "dodge_chance": 5,
    "atk_speed": 1.0,
    "hp_regen": 1,
    "mana_regen": 1,
    "magic_shield": 0,
    "luck": 0,
    "rarity": 0
}

STAT_NAMES_RU = {
    "hp": "Здоровье",
    "mana": "Мана",
    "dmg": "Урон",
    "def": "Защита",
    "crit_chance": "Шанс крита",
    "dodge_chance": "Уклонение",
    "atk_speed": "Скорость атаки",
    "hp_regen": "Реген HP",
    "mana_regen": "Реген MP",
    "magic_shield": "Маг. щит",
    "luck": "Удача",
    "rarity": "Редкость"
}

STAT_GROWTH = {
    "hp": 10,
    "mana": 5,
    "dmg": 2,
    "def": 1,
    "crit_chance": 0.5,
    "dodge_chance": 0.5,
    "atk_speed": 0.05,
    "hp_regen": 0.5,
    "mana_regen": 0.5,
    "magic_shield": 1,
    "luck": 0.1,
    "rarity": 0.1
}

ENEMIES = [
    {"name": "Слизень", "base_hp": 50, "base_dmg": 5, "gold_min": 10, "gold_max": 20},
    {"name": "Гоблин", "base_hp": 100, "base_dmg": 10, "gold_min": 20, "gold_max": 40},
    {"name": "Орк", "base_hp": 250, "base_dmg": 25, "gold_min": 50, "gold_max": 100},
    {"name": "Дракон", "base_hp": 1000, "base_dmg": 100, "gold_min": 200, "gold_max": 500},
]

MEDITATION_TIME = 300
MEDITATION_MANA_BONUS = 20

# Качество предметов на русском
ITEM_QUALITY_RU = {
    "Обычное": 1,
    "Редкое": 2,
    "Эпическое": 3,
    "Легендарное": 5
}