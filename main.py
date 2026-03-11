import asyncio
import random
import time
import logging
import os
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Union
from aiogram.exceptions import TelegramBadRequest

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
    type: str  # 'weapon', 'armor', 'accessory'
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
    pending_stat: Optional[str] = None
    current_enemy: Optional[dict] = None
    
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
        self.check_state_expiration(player)
        return player

    def check_state_expiration(self, player: Player):
        now = time.time()
        if player.state != "idle" and now >= player.state_end_time:
            if player.state == "upgrading" and player.pending_stat:
                self.apply_upgrade(player, player.pending_stat)
            player.state = "idle"
            player.state_end_time = 0
            player.pending_stat = None

    def apply_upgrade(self, player: Player, stat_key: str):
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

    def simulate_battle(self, player: Player, enemy: dict):
        log = []
        eff = self.get_effective_stats(player)
        p_hp, p_mp = player.stats.hp, player.stats.mp
        e_hp = enemy["hp"]
        t = 0
        p_next, e_next = 0, 0
        
        while p_hp > 0 and e_hp > 0 and t < 500:
            t += 1
            curr = t / 10
            if curr >= p_next:
                dmg = eff.damage * (Config.CRIT_MULTIPLIER if random.random() < eff.crit_chance else 1)
                actual = max(1, dmg - enemy["armor"] * 0.2)
                e_hp -= actual
                p_next = curr + (1 / eff.attack_speed)
                log.append(f"👤 Удар: {actual:.1f}")

            if e_hp <= 0: break

            if curr >= e_next:
                if random.random() > eff.dodge_chance:
                    e_dmg = max(1, enemy["damage"] - eff.armor * 0.2)
                    p_hp -= e_dmg
                    log.append(f"👹 Враг: {e_dmg:.1f}")
                e_next = curr + (1 / enemy["attack_speed"])

        player.stats.hp, player.stats.mp = max(0, p_hp), max(0, p_mp)
        return log, p_hp > 0

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
    try:
        await callback.message.edit_text(f"Статус обновлен. Состояние: {p.state}", reply_markup=get_main_kb(p))
    except TelegramBadRequest:
        await callback.answer("Пока без изменений...")

@dp.callback_query(F.data == "stats")
async def show_stats(callback: types.CallbackQuery):
    p = engine.get_player(callback.from_user.id)
    engine.process_regen(p)
    eff = engine.get_effective_stats(p)
    text = (f"📊 **{p.name}** (Ур. {p.level})\n❤️ HP: {p.stats.hp:.1f}/{eff.max_hp}\n"
            f"⚔️ Урон: {eff.damage} | 💰 Золото: {p.gold:.1f}")
    try:
        await callback.message.edit_text(text, reply_markup=get_main_kb(p))
    except TelegramBadRequest:
        await callback.answer()

@dp.callback_query(F.data == "shop")
async def show_shop(callback: types.CallbackQuery):
    p = engine.get_player(callback.from_user.id)
    now = time.time()
    if p.user_id not in engine.last_shop_refresh or now - engine.last_shop_refresh[p.user_id] > Config.SHOP_REFRESH_TIME:
        engine.shop_items[p.user_id] = engine.generate_shop(p)
        engine.last_shop_refresh[p.user_id] = now
    
    builder = InlineKeyboardBuilder()
    for idx, item in enumerate(engine.shop_items.get(p.user_id, [])):
        builder.row(InlineKeyboardButton(text=f"{item.name} - {item.price}💰", callback_data=f"buy_{idx}"))
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="stats"))
    await callback.message.edit_text("🛒 Магазин", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("buy_"))
async def buy_item(callback: types.CallbackQuery):
    p = engine.get_player(callback.from_user.id)
    idx = int(callback.data.split("_")[1])
    items = engine.shop_items.get(p.user_id, [])
    if idx >= len(items): return await callback.answer("Товар исчез!")
    item = items[idx]
    if p.gold < item.price: return await callback.answer("Нет золота!")
    if len(p.inventory) >= p.inventory_slots: return await callback.answer("Сумка полна!")
    
    p.gold -= item.price
    p.inventory.append(item)
    items.pop(idx)
    await callback.answer(f"Куплено: {item.name}")
    await show_shop(callback)

@dp.callback_query(F.data == "inventory")
async def show_inv(callback: types.CallbackQuery):
    p = engine.get_player(callback.from_user.id)
    builder = InlineKeyboardBuilder()
    for idx, item in enumerate(p.inventory):
        builder.row(InlineKeyboardButton(text=f"📦 {item.name}", callback_data=f"inv_{idx}"))
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="stats"))
    await callback.message.edit_text(f"🎒 Инвентарь ({len(p.inventory)}/{p.inventory_slots})", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("inv_"))
async def inv_item(callback: types.CallbackQuery):
    p = engine.get_player(callback.from_user.id)
    idx = int(callback.data.split("_")[1])
    item = p.inventory[idx]
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="✅ Надеть", callback_data=f"eq_{idx}"))
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="inventory"))
    await callback.message.edit_text(f"📦 {item.name}\nТип: {item.type}", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("eq_"))
async def equip(callback: types.CallbackQuery):
    p = engine.get_player(callback.from_user.id)
    idx = int(callback.data.split("_")[1])
    item = p.inventory.pop(idx)
    old = p.equipped[item.type]
    if old: p.inventory.append(old)
    p.equipped[item.type] = item
    await callback.answer("Надето!")
    await show_inv(callback)

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
    p.state, p.pending_stat = "upgrading", stat
    p.state_end_time = time.time() + Config.UPGRADE_TIME
    await callback.message.edit_text("⏳ Прокачка началась!", reply_markup=get_main_kb(p))

@dp.callback_query(F.data == "find_enemy")
async def find_enemy(callback: types.CallbackQuery):
    p = engine.get_player(callback.from_user.id)
    enemy = {"name": random.choice(["Орк", "Слизень", "Бес"]), "level": p.level, "hp": 50+p.level*20, "damage": 5+p.level*2, "armor": p.level, "attack_speed": 0.8, "gold": 20+p.level*10}
    p.current_enemy = enemy
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="⚔️ В бой!", callback_data="bat_start"))
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="stats"))
    await callback.message.edit_text(f"👹 {enemy['name']} (Ур.{enemy['level']})", reply_markup=builder.as_markup())

@dp.callback_query(F.data == "bat_start")
async def bat_start(callback: types.CallbackQuery):
    p = engine.get_player(callback.from_user.id)
    if not p.current_enemy: return await callback.answer("Враг потерян")
    log, win = engine.simulate_battle(p, p.current_enemy)
    if win:
        p.gold += p.current_enemy['gold']
        txt = f"🎉 Победили! +{p.current_enemy['gold']}💰"
    else:
        p.state, p.state_end_time = "dead", time.time() + Config.DEATH_COOLDOWN
        txt = "💀 Вы погибли!"
    await callback.message.edit_text(f"{txt}\n\n" + "\n".join(log[-5:]), reply_markup=get_main_kb(p))

@dp.callback_query(F.data == "cancel_action")
async def cancel(callback: types.CallbackQuery):
    p = engine.get_player(callback.from_user.id)
    p.state, p.pending_stat = "idle", None
    await callback.message.edit_text("Действие отменено.", reply_markup=get_main_kb(p))

async def main():
    logging.basicConfig(level=logging.INFO)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
