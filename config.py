import os
from dotenv import load_dotenv

load_dotenv()

# --- ТЕХНИЧЕСКИЕ ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
DB_NAME = "rpg_game.db"

# --- БАЛАНС ИГРЫ (АЛГЕБРАИЧЕСКАЯ ПРОГРЕССИЯ) ---
# Формула цены прокачки: BASE + (LEVEL * STEP)
# Это гарантирует, что цена растет линейно, а не взрывообразно.
TRAINING_BASE_COST = 100
TRAINING_COST_STEP = 50
TRAINING_TIME_SECONDS = 600  # 10 минут

# Бой
DEATH_LOCK_TIME = 3600  # 1 час блокировки при смерти
COMBAT_LOG_LIMIT = 10   # Сколько ходов показывать в логе

# Магазин
SHOP_REFRESH_TIME = 600  # 10 минут
SHOP_SLOTS_COUNT = 5

# Инвентарь
BASE_INVENTORY_SLOTS = 10
SLOT_UPGRADE_COST = 500

# Характеристики (Базовые значения для игрока)
BASE_STATS = {
    "hp": 100,
    "mana": 50,
    "dmg": 10,
    "def": 5,
    "crit_chance": 5,      # %
    "dodge_chance": 5,     # %
    "atk_speed": 1.0,      # Множитель скорости
    "hp_regen": 1,
    "mana_regen": 1,
    "magic_shield": 0,
    "luck": 0,             # Влияет на дроп
    "rarity": 0            # Влияет на качество предметов
}

# Коэффициенты роста статов за уровень прокачки
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

# Враги (Шаблоны)
ENEMIES = [
    {"name": "Слизень", "base_hp": 50, "base_dmg": 5, "gold_min": 10, "gold_max": 20},
    {"name": "Гоблин", "base_hp": 100, "base_dmg": 10, "gold_min": 20, "gold_max": 40},
    {"name": "Орк", "base_hp": 250, "base_dmg": 25, "gold_min": 50, "gold_max": 100},
    {"name": "Дракон", "base_hp": 1000, "base_dmg": 100, "gold_min": 200, "gold_max": 500},
]

# Доп. активности
MEDITATION_TIME = 300 # 5 минут
MEDITATION_MANA_BONUS = 20