import asyncio
import random
import time
import logging
import os
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Union

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton

# ==========================================
# 1. КОНФИГУРАЦИЯ
# ==========================================
class Config:
    TOKEN = os.getenv("BOT_TOKEN")
    UPGRADE_BASE_COST = 100
    UPGRADE_STEP_COST = 50
    UPGRADE_TIME = 600  # 10 минут
    DEATH_COOLDOWN = 3600  # 1 час
    SHOP_REFRESH_TIME = 600
    REGEN_TICK_TIME = 60
    INITIAL_INVENTORY_SLOTS = 5
    CRIT_MULTIPLIER = 2.0

# ==========================================
# 2. МОДЕЛИ ДАННЫХ
# ==========================================
@dataclass
class Stats:
    hp: float = 100.0
    max_hp: float = 100.0
    hp_regen: float = 1.0
    mp: float = 50.0
    max_mp: float = 50.0
    mp_regen: float = 0.5
    magic_shield: float = 0.0
    armor: float = 5.0
    damage: float = 10.0
    attack_speed: float = 1.0
    crit_chance: float = 0.05
    dodge_chance: float = 0.05

@dataclass
class Item:
    id: str
    name: str
    type: str
    stats_bonus: Dict[str, float]
    price: float = 0

@dataclass
class Player:
    user_id: int
    name: str
    gold: float = 500.0
    level: int = 1
    stats: Stats = field(default_factory=Stats)
    inventory: List[Item] = field(default_factory=list)
    equipped: Dict[str, Optional[Item]] = field(default_factory=lambda: {"weapon": None, "armor": None, "accessory": None})
    
    state: str = "idle"  # idle, upgrading, dead
    state_end_time: float = 0
    pending_stat: Optional[str] = None  # Какой стат качаем
    
    inventory_slots: int = Config.INITIAL_INVENTORY_SLOTS
    last_regen_tick: float = field(default_factory=time.time)

# ==========================================
# 3. ИГРОВАЯ ЛОГИКА
# ==========================================
class GameEngine:
    def __init__(self):
        self.players: Dict[int, Player] = {}
        self.shop_items: Dict[int, List[Item]] = {}
        self.last_shop_refresh: Dict[int, float] = {}

    def get_player(self, user_id: int, name: str = "Герой") -> Player:
        if user_id not in self.players:
            self.players[user_id] = Player(user_id=user_id, name=name)
        
        player = self.players[user_id]
        self.check_state_expiration(player) # Проверяем таймеры при каждом получении игрока
        return player

    def check_state_expiration(self, player: Player):
        """Проверяет, не закончилось ли время действия (прокачка/смерть)."""
        now = time.time()
        if player.state != "idle" and now >= player.state_end_time:
            if player.state == "upgrading" and player.pending_stat:
                self.apply_upgrade(player, player.pending_stat)
            
            player.state = "idle"
            player.state_end_time = 0
            player.pending_stat = None

    def apply_upgrade(self, player: Player, stat_key: str):
        """Применяет результаты прокачки."""
        if stat_key == "max_hp": player.stats.max_hp += 20
        elif stat_key == "damage": player.stats.damage += 5
        elif stat_key == "attack_speed": player.stats.attack_speed += 0.05
        elif stat_key == "armor": player.stats.armor += 2
        elif stat_key == "magic_shield": player.stats.magic_shield += 5
        player.level += 1

    def get_effective_stats(self, player: Player) -> Stats:
        base = asdict(player.stats)
        for item in player.equipped.values():
            if item:
                for stat, bonus in item.stats_bonus.items():
                    if stat in base: base[stat] += bonus
        return Stats(**base)

    def process_regen(self, player: Player):
        now = time.time()
        eff = self.get_effective_stats(player)
        ticks = int((now - player.last_regen_tick) / Config.REGEN_TICK_TIME)
        if ticks > 0:
            player.stats.hp = min(eff.max_hp, player.stats.hp + eff.hp_regen * ticks)
            player.stats.mp = min(eff.max_mp, player.stats.mp + eff.mp_regen * ticks)
            player.last_regen_tick = now

    def generate_shop(self, player: Player):
        items = []
        opts = [("Меч", "weapon", "damage"), ("Щит", "armor", "armor"), ("Кольцо", "accessory", "crit_chance")]
        for _ in range(3):
            name, itype, stat = random.choice(opts)
            val = 5 + (player.level * 2) if stat != "crit_chance" else 0.02
            items.append(Item(id=f"i_{random.randint(100,999)}", name=f"{name} {player.level}ур", 
                              type=itype, stats_bonus={stat: val}, price=100 + player.level*50))
        return items

# ==========================================
# 4. ОБРАБОТЧИКИ
# ==========================================
bot = Bot(token=Config.TOKEN)
dp = Dispatcher()
engine = GameEngine()

def get_main_kb(player: Player):
    builder = InlineKeyboardBuilder()
    now = time.time()
    
    if player.state != "idle" and now < player.state_end_time:
        rem = int(player.state_end_time - now)
        label = "⏳ Прокачка" if player.state == "upgrading" else "💀 Смерть"
        builder.row(InlineKeyboardButton(text=f"{label} ({rem}с)", callback_data="refresh_status"))
        if player.state == "upgrading":
            builder.row(InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_action"))
        return builder.as_markup()

    builder.row(InlineKeyboardButton(text="⚔️ Искать врага", callback_data="find_enemy"))
    builder.row(InlineKeyboardButton(text="📈 Прокачка", callback_data="upgrade_menu"),
                InlineKeyboardButton(text="🎒 Инвентарь", callback_data="inventory"))
    builder.row(InlineKeyboardButton(text="🛒 Магазин", callback_data="shop"),
                InlineKeyboardButton(text="🏆 Статистика", callback_data="stats"))
    return builder.as_markup()

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    p = engine.get_player(message.from_user.id, message.from_user.full_name)
    await message.answer(f"Добро пожаловать, {p.name}!", reply_markup=get_main_kb(p))

@dp.callback_query(F.data == "refresh_status")
async def refresh_status(callback: types.CallbackQuery):
    p = engine.get_player(callback.from_user.id)
    await callback.message.edit_text(f"Статус обновлен. Состояние: {p.state}", reply_markup=get_main_kb(p))

@dp.callback_query(F.data == "stats")
async def show_stats(callback: types.CallbackQuery):
    p = engine.get_player(callback.from_user.id)
    engine.process_regen(p)
    eff = engine.get_effective_stats(p)
    text = (f"📊 **{p.name}** (Ур. {p.level})\n❤️ HP: {p.stats.hp:.1f}/{eff.max_hp}\n"
            f"⚔️ Урон: {eff.damage} | 💰 Золото: {p.gold:.1f}")
    await callback.message.edit_text(text, reply_markup=get_main_kb(p))

@dp.callback_query(F.data == "upgrade_menu")
async def upgrade_menu(callback: types.CallbackQuery):
    p = engine.get_player(callback.from_user.id)
    cost = Config.UPGRADE_BASE_COST + (p.level * Config.UPGRADE_STEP_COST)
    builder = InlineKeyboardBuilder()
    for n, k in [("HP", "max_hp"), ("Урон", "damage"), ("Броня", "armor")]:
        builder.add(InlineKeyboardButton(text=f"{n} ({cost}💰)", callback_data=f"up_{k}"))
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="stats"))
    await callback.message.edit_text(f"📈 Прокачка (10 мин)", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("up_"))
async def start_up(callback: types.CallbackQuery):
    p = engine.get_player(callback.from_user.id)
    stat = callback.data.split("_")[1]
    cost = Config.UPGRADE_BASE_COST + (p.level * Config.UPGRADE_STEP_COST)
    if p.gold < cost: return await callback.answer("Нет золота!")
    
    p.gold -= cost
    p.state = "upgrading"
    p.pending_stat = stat
    p.state_end_time = time.time() + Config.UPGRADE_TIME
    await callback.message.edit_text("⏳ Прокачка началась!", reply_markup=get_main_kb(p))

@dp.callback_query(F.data == "cancel_action")
async def cancel(callback: types.CallbackQuery):
    p = engine.get_player(callback.from_user.id)
    p.state = "idle"
    p.pending_stat = None
    await callback.message.edit_text("Действие отменено.", reply_markup=get_main_kb(p))

# Добавь остальные хендлеры (shop, inventory, find_enemy) по аналогии с прошлым кодом

async def main():
    logging.basicConfig(level=logging.INFO)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())