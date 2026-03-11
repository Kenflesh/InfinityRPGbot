import asyncio
import random
import time
import logging
import os
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Union
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton

# ==========================================
# 1. КОНФИГУРАЦИЯ И БАЛАНС (CONFIG)
# ==========================================
class Config:
    TOKEN = os.getenv("BOT_TOKEN")
    
    # Алгебраическая прогрессия: цена = база + (уровень * шаг)
    UPGRADE_BASE_COST = 100
    UPGRADE_STEP_COST = 50
    
    # Таймеры (в секундах)
    UPGRADE_TIME = 600  # 10 минут
    DEATH_COOLDOWN = 3600  # 1 час
    SHOP_REFRESH_TIME = 600  # 10 минут
    REGEN_TICK_TIME = 60  # 1 минута
    
    # Ограничения
    INITIAL_INVENTORY_SLOTS = 5
    INITIAL_ABILITY_SLOTS = 2
    
    # Боевые константы
    CRIT_MULTIPLIER = 2.0
    MISS_CAP = 0.8  # Максимальный шанс уклонения 80%
    
    # Шансы дропа
    DROP_CHANCE_ITEM = 0.3
    DROP_CHANCE_ABILITY = 0.1

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
    luck: float = 1.0
    rarity_find: float = 1.0

@dataclass
class Item:
    id: str
    name: str
    type: str  # 'weapon', 'armor', 'accessory'
    stats_bonus: Dict[str, float]
    price: float = 0
    level: int = 1

@dataclass
class Ability:
    id: str
    name: str
    mana_cost: float
    power: float
    effect_type: str
    level: int = 1

@dataclass
class Player:
    user_id: int
    name: str
    gold: float = 500.0
    level: int = 1
    stats: Stats = field(default_factory=Stats)
    inventory: List[Item] = field(default_factory=list)
    equipped: Dict[str, Optional[Item]] = field(default_factory=lambda: {"weapon": None, "armor": None, "accessory": None})
    abilities: List[Ability] = field(default_factory=list)
    equipped_abilities: List[Ability] = field(default_factory=list)
    
    inventory_slots: int = Config.INITIAL_INVENTORY_SLOTS
    ability_slots: int = Config.INITIAL_ABILITY_SLOTS
    
    state: str = "idle"  # idle, upgrading, dead, fighting
    state_end_time: float = 0
    last_regen_tick: float = field(default_factory=time.time)

# ==========================================
# 3. ИГРОВАЯ ЛОГИКА
# ==========================================

class GameEngine:
    def __init__(self):
        self.players: Dict[int, Player] = {}
        self.shop_items: Dict[int, List[Item]] = {} # Магазин индивидуален или по времени
        self.last_shop_refresh: Dict[int, float] = {}

    def get_player(self, user_id: int, name: str = "Герой") -> Player:
        if user_id not in self.players:
            self.players[user_id] = Player(user_id=user_id, name=name)
        return self.players[user_id]

    def get_effective_stats(self, player: Player) -> Stats:
        """Возвращает статы с учетом надетого снаряжения."""
        base = asdict(player.stats)
        for slot, item in player.equipped.items():
            if item:
                for stat, bonus in item.stats_bonus.items():
                    if stat in base:
                        base[stat] += bonus
        return Stats(**base)

    def process_regen(self, player: Player):
        now = time.time()
        effective = self.get_effective_stats(player)
        ticks = int((now - player.last_regen_tick) / Config.REGEN_TICK_TIME)
        if ticks > 0:
            player.stats.hp = min(effective.max_hp, player.stats.hp + effective.hp_regen * ticks)
            player.stats.mp = min(effective.max_mp, player.stats.mp + effective.mp_regen * ticks)
            player.last_regen_tick = now

    def generate_shop(self, player: Player):
        items = []
        types = [("Меч", "weapon", "damage"), ("Щит", "armor", "armor"), ("Кольцо", "accessory", "crit_chance")]
        for i in range(3):
            name, itype, stat = random.choice(types)
            bonus_val = 5 + (player.level * 2) if stat != "crit_chance" else 0.02 + (player.level * 0.005)
            price = 100 + (player.level * 40)
            items.append(Item(
                id=f"item_{random.randint(1000, 9999)}",
                name=f"{name} {random.choice(['Новичка', 'Героя', 'Мастера'])}",
                type=itype,
                stats_bonus={stat: bonus_val},
                price=price,
                level=player.level
            ))
        return items

    def generate_enemy(self, player_level: int, difficulty_offset: int = 0):
        level = max(1, player_level + difficulty_offset)
        hp = 50 + (level * 20)
        damage = 5 + (level * 3)
        return {
            "name": random.choice(["Гоблин", "Орк", "Тень", "Дракон", "Слизень"]),
            "level": level,
            "hp": hp,
            "max_hp": hp,
            "damage": damage,
            "attack_speed": 0.5 + (level * 0.05),
            "armor": level * 2,
            "exp": level * 10,
            "gold": level * 15
        }

    def simulate_battle(self, player: Player, enemy: dict) -> list:
        log = []
        eff = self.get_effective_stats(player)
        p_hp = player.stats.hp
        p_mp = player.stats.mp
        e_hp = enemy["hp"]
        
        t = 0
        p_next_atk = 0
        e_next_atk = 0
        
        while p_hp > 0 and e_hp > 0 and t < 1000:
            t += 1
            current_time = t / 10
            
            if current_time >= p_next_atk:
                dmg = eff.damage
                if random.random() < eff.crit_chance:
                    dmg *= Config.CRIT_MULTIPLIER
                    log.append(f"⚔️ Критический удар по {enemy['name']}!")
                
                actual_dmg = max(1, dmg - enemy["armor"] * 0.2)
                e_hp -= actual_dmg
                p_next_atk = current_time + (1 / eff.attack_speed)
                log.append(f"👤 Удар по {enemy['name']}: {actual_dmg:.1f}. (Ост. {max(0, e_hp):.1f})")

            if e_hp <= 0: break

            if current_time >= e_next_atk:
                if random.random() > eff.dodge_chance:
                    e_dmg = enemy["damage"]
                    if eff.magic_shield > 0 and p_mp > 5:
                        shield_absorb = min(e_dmg * 0.5, p_mp)
                        p_mp -= shield_absorb
                        e_dmg -= shield_absorb
                        log.append(f"🔮 Щит поглотил {shield_absorb:.1f} урона.")
                    
                    actual_e_dmg = max(1, e_dmg - eff.armor * 0.2)
                    p_hp -= actual_e_dmg
                    log.append(f"👹 {enemy['name']} ударил вас на {actual_e_dmg:.1f}. (Ваше ХП: {max(0, p_hp):.1f})")
                else:
                    log.append(f"💨 Вы уклонились!")
                e_next_atk = current_time + (1 / enemy["attack_speed"])

        player.stats.hp = p_hp
        player.stats.mp = p_mp
        return log, p_hp > 0

# ==========================================
# 4. БОТ И ИНТЕРФЕЙС
# ==========================================

bot = Bot(token=Config.TOKEN)
dp = Dispatcher()
engine = GameEngine()

def get_main_kb(player: Player):
    builder = InlineKeyboardBuilder()
    now = time.time()
    
    if player.state == "upgrading" and now < player.state_end_time:
        rem = int(player.state_end_time - now)
        builder.row(InlineKeyboardButton(text=f"⏳ Прокачка ({rem}с)", callback_data="status"))
        builder.row(InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_action"))
        return builder.as_markup()
    
    if player.state == "dead" and now < player.state_end_time:
        rem = int((player.state_end_time - now) // 60)
        builder.row(InlineKeyboardButton(text=f"💀 Оживление через {rem}м", callback_data="status"))
        return builder.as_markup()

    builder.row(InlineKeyboardButton(text="⚔️ Искать врага", callback_data="find_enemy"))
    builder.row(InlineKeyboardButton(text="📈 Прокачка", callback_data="upgrade_menu"),
                InlineKeyboardButton(text="🎒 Инвентарь", callback_data="inventory"))
    builder.row(InlineKeyboardButton(text="🛒 Магазин", callback_data="shop"),
                InlineKeyboardButton(text="🏆 Статистика", callback_data="stats"))
    return builder.as_markup()

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    player = engine.get_player(message.from_user.id, message.from_user.full_name)
    await message.answer(f"Приветствуем в бесконечной RPG, {player.name}!", reply_markup=get_main_kb(player))

@dp.callback_query(F.data == "status")
async def status_check(callback: types.CallbackQuery):
    await callback.answer("Выполняется действие. Ждите завершения таймера.")

@dp.callback_query(F.data == "stats")
async def show_stats(callback: types.CallbackQuery):
    p = engine.get_player(callback.from_user.id)
    engine.process_regen(p)
    eff = engine.get_effective_stats(p)
    text = (
        f"📊 **Статистика {p.name}**\n"
        f"❤️ HP: {p.stats.hp:.1f}/{eff.max_hp:.1f} (+{eff.hp_regen}/мин)\n"
        f"💧 MP: {p.stats.mp:.1f}/{eff.max_mp:.1f} (+{eff.mp_regen}/мин)\n"
        f"🛡 Броня: {eff.armor} | ✨ Щит: {eff.magic_shield}\n"
        f"⚔️ Урон: {eff.damage} | ⚡️ Скорость: {eff.attack_speed}/с\n"
        f"🎯 Крит: {eff.crit_chance*100:.1f}% | 💨 Уклон: {eff.dodge_chance*100:.1f}%\n"
        f"💰 Золото: {p.gold:.1f}"
    )
    await callback.message.edit_text(text, reply_markup=get_main_kb(p))

@dp.callback_query(F.data == "shop")
async def show_shop(callback: types.CallbackQuery):
    p = engine.get_player(callback.from_user.id)
    now = time.time()
    
    if p.user_id not in engine.last_shop_refresh or now - engine.last_shop_refresh[p.user_id] > Config.SHOP_REFRESH_TIME:
        engine.shop_items[p.user_id] = engine.generate_shop(p)
        engine.last_shop_refresh[p.user_id] = now
        
    builder = InlineKeyboardBuilder()
    for idx, item in enumerate(engine.shop_items[p.user_id]):
        builder.row(InlineKeyboardButton(text=f"{item.name} - {item.price}💰", callback_data=f"buy_{idx}"))
    
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="stats"))
    await callback.message.edit_text("🛒 **Магазин**\nОбновление каждые 10 минут.", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("buy_"))
async def buy_item(callback: types.CallbackQuery):
    p = engine.get_player(callback.from_user.id)
    idx = int(callback.data.split("_")[1])
    item = engine.shop_items[p.user_id][idx]
    
    if p.gold < item.price:
        return await callback.answer("Недостаточно золота!")
    if len(p.inventory) >= p.inventory_slots:
        return await callback.answer("Инвентарь полон!")
    
    p.gold -= item.price
    p.inventory.append(item)
    engine.shop_items[p.user_id].pop(idx)
    await callback.answer(f"Куплено: {item.name}")
    await show_shop(callback)

@dp.callback_query(F.data == "inventory")
async def show_inventory(callback: types.CallbackQuery):
    p = engine.get_player(callback.from_user.id)
    builder = InlineKeyboardBuilder()
    
    for idx, item in enumerate(p.inventory):
        builder.row(InlineKeyboardButton(text=f"📦 {item.name}", callback_data=f"invitem_{idx}"))
    
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="stats"))
    text = f"🎒 **Инвентарь** ({len(p.inventory)}/{p.inventory_slots})\n"
    for slot, item in p.equipped.items():
        name = item.name if item else "Пусто"
        text += f"🔹 {slot.capitalize()}: {name}\n"
        
    await callback.message.edit_text(text, reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("invitem_"))
async def item_action(callback: types.CallbackQuery):
    p = engine.get_player(callback.from_user.id)
    idx = int(callback.data.split("_")[1])
    item = p.inventory[idx]
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="✅ Надеть", callback_data=f"equip_{idx}"))
    builder.row(InlineKeyboardButton(text="🗑 Продать (50%)", callback_data=f"sell_{idx}"))
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="inventory"))
    
    bonuses = ", ".join([f"{k}: +{v}" for k, v in item.stats_bonus.items()])
    await callback.message.edit_text(f"📦 **{item.name}**\nБонусы: {bonuses}", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("equip_"))
async def equip_item(callback: types.CallbackQuery):
    p = engine.get_player(callback.from_user.id)
    idx = int(callback.data.split("_")[1])
    item = p.inventory.pop(idx)
    
    old_item = p.equipped[item.type]
    if old_item:
        p.inventory.append(old_item)
    
    p.equipped[item.type] = item
    await callback.answer("Предмет надет!")
    await show_inventory(callback)

@dp.callback_query(F.data == "upgrade_menu")
async def upgrade_menu(callback: types.CallbackQuery):
    p = engine.get_player(callback.from_user.id)
    cost = Config.UPGRADE_BASE_COST + (p.level * Config.UPGRADE_STEP_COST)
    builder = InlineKeyboardBuilder()
    stats_to_up = [("Макс. HP", "max_hp"), ("Реген HP", "hp_regen"), ("Урон", "damage"), 
                   ("Скорость", "attack_speed"), ("Броня", "armor"), ("Маг. Щит", "magic_shield")]
    for name, key in stats_to_up:
        builder.add(InlineKeyboardButton(text=f"{name} ({cost})", callback_data=f"up_{key}"))
    builder.adjust(2)
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="stats"))
    await callback.message.edit_text(f"📈 **Прокачка**\nЦена: {cost}💰\nВремя: 10м", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("up_"))
async def process_upgrade(callback: types.CallbackQuery):
    p = engine.get_player(callback.from_user.id)
    stat_key = callback.data.split("_")[1]
    cost = Config.UPGRADE_BASE_COST + (p.level * Config.UPGRADE_STEP_COST)
    if p.gold < cost:
        return await callback.answer("Недостаточно золота!", show_alert=True)
    
    p.gold -= cost
    p.state = "upgrading"
    p.state_end_time = time.time() + Config.UPGRADE_TIME
    
    await callback.message.edit_text(f"⏳ Прокачка запущена. Ждем 10 минут.", reply_markup=get_main_kb(p))
    
    async def finish():
        await asyncio.sleep(Config.UPGRADE_TIME)
        if p.state == "upgrading":
            if stat_key == "max_hp": p.stats.max_hp += 20
            elif stat_key == "damage": p.stats.damage += 5
            elif stat_key == "attack_speed": p.stats.attack_speed += 0.05
            elif stat_key == "armor": p.stats.armor += 2
            elif stat_key == "magic_shield": p.stats.magic_shield += 5
            p.level += 1
            p.state = "idle"
    asyncio.create_task(finish())

@dp.callback_query(F.data == "find_enemy")
async def find_enemy(callback: types.CallbackQuery):
    p = engine.get_player(callback.from_user.id)
    enemy = engine.generate_enemy(p.level)
    p.current_enemy = enemy
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="⚔️ В бой!", callback_data="battle_start"))
    builder.row(InlineKeyboardButton(text="🏃 Назад", callback_data="stats"))
    await callback.message.edit_text(f"👹 {enemy['name']} (Ур.{enemy['level']})\nHP: {enemy['hp']}\nDMG: {enemy['damage']}", reply_markup=builder.as_markup())

@dp.callback_query(F.data == "battle_start")
async def battle_start(callback: types.CallbackQuery):
    p = engine.get_player(callback.from_user.id)
    if not hasattr(p, 'current_enemy'): return
    log, win = engine.simulate_battle(p, p.current_enemy)
    if win:
        p.gold += p.current_enemy['gold']
        res = f"🎉 Победили {p.current_enemy['name']}! +{p.current_enemy['gold']}💰"
    else:
        p.state = "dead"
        p.state_end_time = time.time() + Config.DEATH_COOLDOWN
        res = "💀 Вы погибли! Воскрешение 1 час."
    await callback.message.edit_text(f"{res}\n\n" + "\n".join(log[-5:]), reply_markup=get_main_kb(p))

@dp.callback_query(F.data == "cancel_action")
async def cancel_action(callback: types.CallbackQuery):
    p = engine.get_player(callback.from_user.id)
    p.state = "idle"
    await callback.message.edit_text("Действие отменено.", reply_markup=get_main_kb(p))

async def main():
    logging.basicConfig(level=logging.INFO)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())