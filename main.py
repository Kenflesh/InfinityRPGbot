import os
import asyncio
import random
import time
import logging
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
    magic_shield: float = 0.0  # Поглощает урон за счет маны
    armor: float = 5.0
    damage: float = 10.0
    attack_speed: float = 1.0  # Атак в секунду
    crit_chance: float = 0.05
    dodge_chance: float = 0.05
    luck: float = 1.0  # Влияет на дроп
    rarity_find: float = 1.0

@dataclass
class Item:
    id: str
    name: str
    type: str  # 'weapon', 'armor', 'accessory'
    stats_bonus: Dict[str, float]
    level: int = 1

@dataclass
class Ability:
    id: str
    name: str
    mana_cost: float
    power: float
    effect_type: str  # 'damage', 'heal', 'shield'
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
# 3. ИГРОВАЯ ЛОГИКА И СИМУЛЯЦИЯ
# ==========================================

class GameEngine:
    def __init__(self):
        self.players: Dict[int, Player] = {}
        self.shop_items: List[Item] = []
        self.last_shop_refresh = 0

    def get_player(self, user_id: int, name: str = "Герой") -> Player:
        if user_id not in self.players:
            self.players[user_id] = Player(user_id=user_id, name=name)
        return self.players[user_id]

    def process_regen(self, player: Player):
        now = time.time()
        ticks = int((now - player.last_regen_tick) / Config.REGEN_TICK_TIME)
        if ticks > 0:
            player.stats.hp = min(player.stats.max_hp, player.stats.hp + player.stats.hp_regen * ticks)
            player.stats.mp = min(player.stats.max_mp, player.stats.mp + player.stats.mp_regen * ticks)
            player.last_regen_tick = now

    def generate_enemy(self, player_level: int, difficulty_offset: int = 0):
        # Сложность зависит от желания игрока (offset)
        level = max(1, player_level + difficulty_offset)
        # Алгебраический скейлинг врага
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
        p_hp = player.stats.hp
        p_mp = player.stats.mp
        e_hp = enemy["hp"]
        
        # Тиковая система боя (каждые 0.1 сек)
        t = 0
        p_next_atk = 0
        e_next_atk = 0
        
        while p_hp > 0 and e_hp > 0 and t < 1000: # лимит 100 сек
            t += 1
            current_time = t / 10
            
            # Атака игрока
            if current_time >= p_next_atk:
                # Шанс крита
                dmg = player.stats.damage
                if random.random() < player.stats.crit_chance:
                    dmg *= Config.CRIT_MULTIPLIER
                    log.append(f"⚔️ Критический удар по {enemy['name']}!")
                
                # Учет брони врага
                actual_dmg = max(1, dmg - enemy["armor"] * 0.2)
                e_hp -= actual_dmg
                p_next_atk = current_time + (1 / player.stats.attack_speed)
                log.append(f"👤 Вы ударили {enemy['name']} на {actual_dmg:.1f}. (Осталось {max(0, e_hp):.1f})")

            if e_hp <= 0: break

            # Атака врага
            if current_time >= e_next_atk:
                if random.random() > player.stats.dodge_chance:
                    e_dmg = enemy["damage"]
                    # Магический щит (поглощение)
                    if player.stats.magic_shield > 0 and p_mp > 5:
                        shield_absorb = min(e_dmg * 0.5, p_mp)
                        p_mp -= shield_absorb
                        e_dmg -= shield_absorb
                        log.append(f"🔮 Щит поглотил {shield_absorb:.1f} урона.")
                    
                    actual_e_dmg = max(1, e_dmg - player.stats.armor * 0.2)
                    p_hp -= actual_e_dmg
                    log.append(f"👹 {enemy['name']} ударил вас на {actual_e_dmg:.1f}. (Ваше ХП: {max(0, p_hp):.1f})")
                else:
                    log.append(f"💨 Вы уклонились от атаки!")
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
    
    # Проверка состояний
    now = time.time()
    if player.state == "upgrading" and now < player.state_end_time:
        rem = int(player.state_end_time - now)
        builder.row(InlineKeyboardButton(text=f"⏳ Прокачка ({rem}с)", callback_data="status"))
        builder.row(InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_action"))
        return builder.as_markup()
    
    if player.state == "dead" and now < player.state_end_time:
        rem = int((player.state_end_time - now) // 60)
        builder.row(InlineKeyboardButton(text=f"💀 Воскрешение через {rem}м", callback_data="status"))
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
    await message.answer(f"Приветствуем в бесконечной RPG, {player.name}!\nВаша цель - стать богом этого мира.", 
                         reply_markup=get_main_kb(player))

@dp.callback_query(F.data == "stats")
async def show_stats(callback: types.CallbackQuery):
    p = engine.get_player(callback.from_user.id)
    engine.process_regen(p)
    text = (
        f"📊 **Статистика {p.name}**\n"
        f"❤️ HP: {p.stats.hp:.1f}/{p.stats.max_hp:.1f} (+{p.stats.hp_regen}/мин)\n"
        f"💧 MP: {p.stats.mp:.1f}/{p.stats.max_mp:.1f} (+{p.stats.mp_regen}/мин)\n"
        f"🛡 Броня: {p.stats.armor} | ✨ Маг. Щит: {p.stats.magic_shield}\n"
        f"⚔️ Урон: {p.stats.damage} | ⚡️ Скорость: {p.stats.attack_speed}/с\n"
        f"🎯 Крит: {p.stats.crit_chance*100:.1f}% | 💨 Уклон: {p.stats.dodge_chance*100:.1f}%\n"
        f"💰 Золото: {p.gold:.1f}"
    )
    await callback.message.edit_text(text, reply_markup=get_main_kb(p))

@dp.callback_query(F.data == "upgrade_menu")
async def upgrade_menu(callback: types.CallbackQuery):
    p = engine.get_player(callback.from_user.id)
    cost = Config.UPGRADE_BASE_COST + (p.level * Config.UPGRADE_STEP_COST)
    
    builder = InlineKeyboardBuilder()
    stats_to_up = [
        ("Макс. HP", "max_hp"), ("Реген HP", "hp_regen"), 
        ("Урон", "damage"), ("Скорость", "attack_speed"),
        ("Броня", "armor"), ("Маг. Щит", "magic_shield")
    ]
    for name, key in stats_to_up:
        builder.add(InlineKeyboardButton(text=f"{name} ({cost})", callback_data=f"up_{key}"))
    
    builder.adjust(2)
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="stats"))
    await callback.message.edit_text(f"Выберите стат для улучшения.\nСтоимость: {cost} золота.\nВремя: 10 минут.", 
                                     reply_markup=builder.as_markup())

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
    
    # Сохраняем, что именно качаем (упрощенно добавим сразу по завершении, но в идеале нужен таск)
    # Здесь для демонстрации просто запустим таймер
    await callback.message.edit_text(f"⏳ Началась прокачка. Вернитесь через 10 минут.", reply_markup=get_main_kb(p))
    
    async def finish_upgrade():
        await asyncio.sleep(Config.UPGRADE_TIME)
        if p.state == "upgrading":
            if stat_key == "max_hp": p.stats.max_hp += 20
            elif stat_key == "damage": p.stats.damage += 5
            elif stat_key == "attack_speed": p.stats.attack_speed += 0.1
            p.level += 1
            p.state = "idle"
    
    asyncio.create_task(finish_upgrade())

@dp.callback_query(F.data == "find_enemy")
async def find_enemy(callback: types.CallbackQuery):
    p = engine.get_player(callback.from_user.id)
    enemy = engine.generate_enemy(p.level)
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="⚔️ Вступить в бой!", callback_data="battle_start"))
    builder.row(InlineKeyboardButton(text="🏃 Убежать", callback_data="status"))
    
    text = (
        f"👹 Враг: {enemy['name']} (Ур. {enemy['level']})\n"
        f"❤️ HP: {enemy['hp']} | ⚔️ Урон: {enemy['damage']}\n"
        f"⚡️ Скорость: {enemy['attack_speed']}\n"
        f"Согласны на бой?"
    )
    # Сохраним текущего врага в "память" (упрощенно в атрибут игрока)
    p.current_enemy = enemy 
    await callback.message.edit_text(text, reply_markup=builder.as_markup())

@dp.callback_query(F.data == "battle_start")
async def battle_start(callback: types.CallbackQuery):
    p = engine.get_player(callback.from_user.id)
    if not hasattr(p, 'current_enemy'): return
    
    log, win = engine.simulate_battle(p, p.current_enemy)
    result_text = "\n".join(log[-10:]) # Последние 10 строк боя
    
    if win:
        reward = p.current_enemy['gold']
        p.gold += reward
        msg = f"🎉 **ПОБЕДА!**\n\n{result_text}\n\nВы получили {reward} золота!"
        p.state = "idle"
    else:
        p.state = "dead"
        p.state_end_time = time.time() + Config.DEATH_COOLDOWN
        msg = f"💀 **ВЫ ПОГИБЛИ**\n\n{result_text}\n\nВы сможете воскреснуть через час."
    
    await callback.message.edit_text(msg, reply_markup=get_main_kb(p))

@dp.callback_query(F.data == "cancel_action")
async def cancel_action(callback: types.CallbackQuery):
    p = engine.get_player(callback.from_user.id)
    p.state = "idle"
    await callback.answer("Действие отменено (ресурсы не возвращаются)")
    await callback.message.edit_text("Вы вернулись в строй.", reply_markup=get_main_kb(p))

async def main():
    logging.basicConfig(level=logging.INFO)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())