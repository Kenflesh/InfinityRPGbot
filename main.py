import logging
import random
import time
import asyncio
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from telegram.constants import ParseMode

# --- КОНФИГУРАЦИЯ ---
TOKEN = os.getenv("BOT_TOKEN")

# Настройка логирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- ДАННЫЕ ИГРЫ ---
players = {}

STATS_NAMES = {
    "phys_atk": "Физ. Атака",
    "mag_atk": "Маг. Атака",
    "defense": "Защита",
    "multi_hit": "Множитель",
    "crit_chance": "Крит. Шанс",
    "dodge": "Уклонение"
}

# --- КЛАССЫ И ЛОГИКА ---

class Item:
    def __init__(self, name, item_type):
        self.id = random.randint(1000, 9999)
        self.name = name
        self.item_type = item_type  # 'weapon', 'armor', 'accessory'
        self.stats = {}  # Текущие бонусы
        self.base_stats = {}  # Базовые значения
        self.upgrade_costs = {} # Рандомные базовые цены улучшения
        self.upgrades = {}  # Количество улучшений
        
        self.generate_random_stats()

    def generate_random_stats(self):
        # Шансы на количество статов (Пункт 7 исходного ТЗ)
        num_stats = 1
        for _ in range(4):
            if random.random() < 0.25:
                num_stats += 1
            else:
                break
        
        available_stats = list(STATS_NAMES.keys())
        chosen_keys = random.sample(available_stats, min(num_stats, len(available_stats)))
        
        for key in chosen_keys:
            base_val = random.randint(1, 5)
            self.base_stats[key] = base_val
            self.stats[key] = base_val
            self.upgrades[key] = 0
            self.upgrade_costs[key] = random.randint(50, 150)

    def get_upgrade_price(self, stat_key):
        return self.upgrade_costs[stat_key] * (self.upgrades[stat_key] + 1)

    def upgrade(self, stat_key):
        self.upgrades[stat_key] += 1
        self.stats[stat_key] += self.base_stats[stat_key]

class Player:
    def __init__(self, user_id, name):
        self.user_id = user_id
        self.name = name
        self.level = 1
        self.exp = 0
        self.gold = 500
        self.hp = 100
        self.max_hp = 100
        self.mana = 50
        self.max_mana = 50
        
        self.inventory = []
        self.equipped = {"weapon": None, "armor": None, "accessory": None}
        
        self.state = "idle"  # idle, training, dead, hunting
        self.timer_end = 0

    def get_total_stats(self):
        total = {k: 0 for k in STATS_NAMES}
        for slot in self.equipped.values():
            if slot:
                for stat, val in slot.stats.items():
                    total[stat] += val
        total["phys_atk"] += 5 + self.level
        total["defense"] += 2 + self.level
        return total

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---

def get_main_menu_kb():
    keyboard = [
        [InlineKeyboardButton("⚔️ Охота", callback_data="hunt_menu"), InlineKeyboardButton("🏋️ Тренировка", callback_data="train")],
        [InlineKeyboardButton("🎒 Инвентарь", callback_data="inventory"), InlineKeyboardButton("🛒 Магазин", callback_data="shop")],
        [InlineKeyboardButton("📊 Статистика", callback_data="stats")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_item_desc(item):
    desc = f"📦 *{item.name}* ({item.item_type})\n"
    for k, v in item.stats.items():
        base = item.base_stats[k]
        upgrades = item.upgrades[k]
        desc += f"• {STATS_NAMES[k]}: {v} (База: {base}, +{upgrades})\n"
    return desc

# --- ОБРАБОТЧИКИ ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in players:
        players[user_id] = Player(user_id, update.effective_user.first_name)
    
    await update.message.reply_text(
        f"Привет, {players[user_id].name}! Добро пожаловать в RPG мир.",
        reply_markup=get_main_menu_kb()
    )

async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    p = players.get(user_id)
    if not p: return

    if p.state in ["training", "dead"] and query.data not in ["check_time", "cancel_wait"]:
        if time.time() >= p.timer_end:
            p.state = "idle"
        else:
            await query.answer("Вы еще заняты!")
            return

    data = query.data

    if data == "main_menu":
        await query.edit_message_text("Главное меню:", reply_markup=get_main_menu_kb())

    elif data == "stats":
        s = p.get_total_stats()
        text = (f"👤 *{p.name}* (Ур. {p.level})\n"
                f"❤️ HP: {p.hp}/{p.max_hp}\n"
                f"✨ MP: {p.mana}/{p.max_mana}\n"
                f"💰 Золото: {p.gold}\n"
                f"📖 Опыт: {p.exp}\n\n"
                f"*Бонусы снаряжения:*\n")
        for k, v in s.items():
            text += f"{STATS_NAMES[k]}: {v}\n"
        
        kb = [[InlineKeyboardButton("Назад", callback_data="main_menu")]]
        await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(kb))

    elif data == "hunt_menu":
        kb = [
            [InlineKeyboardButton("Лес (Легко)", callback_data="fight_1")],
            [InlineKeyboardButton("Пещера (Средне)", callback_data="fight_2")],
            [InlineKeyboardButton("Замок (Сложно)", callback_data="fight_3")],
            [InlineKeyboardButton("Назад", callback_data="main_menu")]
        ]
        await query.edit_message_text("Выберите сложность охоты:", reply_markup=InlineKeyboardMarkup(kb))

    elif data.startswith("fight_"):
        diff = int(data.split("_")[1])
        p.mana = max(0, p.mana - 5)
        enemy_hp = 20 * diff
        enemy_atk = 3 * diff
        logs = [f"⚔️ Начало боя! Ваша мана: {p.mana}/{p.max_mana}"]
        
        p_stats = p.get_total_stats()
        
        while enemy_hp > 0 and p.hp > 0:
            dmg = max(1, p_stats["phys_atk"] - (diff * 2))
            enemy_hp -= dmg
            logs.append(f"Вы ударили монстра на {dmg}. (Осталось: {enemy_hp})")
            if enemy_hp <= 0: break
            
            e_dmg = max(1, enemy_atk - p_stats["defense"] // 2)
            p.hp -= e_dmg
            logs.append(f"Монстр ударил вас на {e_dmg}. (Ваше HP: {p.hp})")
            
        if p.hp <= 0:
            p.state = "dead"
            p.timer_end = time.time() + 60
            p.hp = 0
            await query.edit_message_text("💀 Вы погибли! Ожидайте воскрешения (1 мин).", 
                                         reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Проверить время", callback_data="check_time")]]))
        else:
            gold_gain = 20 * diff
            exp_gain = 15 * diff
            p.gold += gold_gain
            p.exp += exp_gain
            logs.append(f"\n✅ Победа! +{gold_gain}💰, +{exp_gain}📖")
            logs.append(f"Ваше HP: {p.hp}/{p.max_hp}, Мана: {p.mana}/{p.max_mana}")
            
            kb = [[InlineKeyboardButton("Продолжить охоту", callback_data="hunt_menu")],
                  [InlineKeyboardButton("В город", callback_data="main_menu")]]
            await query.edit_message_text("\n".join(logs), reply_markup=InlineKeyboardMarkup(kb))

    elif data == "train":
        p.state = "training"
        p.timer_end = time.time() + 30
        kb = [[InlineKeyboardButton("Проверить время", callback_data="check_time")],
              [InlineKeyboardButton("Отменить", callback_data="cancel_wait")]]
        await query.edit_message_text("🏋️ Вы тренируетесь... (30 сек)", reply_markup=InlineKeyboardMarkup(kb))

    elif data == "check_time":
        rem = int(p.timer_end - time.time())
        if rem <= 0:
            p.state = "idle"
            if p.hp <= 0: p.hp = p.max_hp
            await query.answer("Время вышло! Вы свободны.")
            await query.edit_message_text("Действие завершено. Вы вернулись в город.", reply_markup=get_main_menu_kb())
        else:
            await query.answer(f"Осталось: {rem} сек.", show_alert=True)

    elif data == "cancel_wait":
        if p.state == "dead":
            await query.answer("Смерть нельзя отменить!")
        else:
            p.state = "idle"
            await query.answer("Ожидание отменено.")
            await query.edit_message_text("Главное меню:", reply_markup=get_main_menu_kb())

    elif data == "shop":
        kb = [
            [InlineKeyboardButton(f"Купить Оружие (100💰)", callback_data="buy_weapon")],
            [InlineKeyboardButton(f"Купить Броню (100💰)", callback_data="buy_armor")],
            [InlineKeyboardButton("Назад", callback_data="main_menu")]
        ]
        await query.edit_message_text(f"🛒 Магазин (Ваше золото: {p.gold})\nНовые предметы имеют случайные базовые характеристики!", reply_markup=InlineKeyboardMarkup(kb))

    elif data.startswith("buy_"):
        if p.gold >= 100:
            p.gold -= 100
            t = data.split("_")[1]
            names = {"weapon": "Меч", "armor": "Доспех"}
            new_item = Item(names[t], t)
            p.inventory.append(new_item)
            await query.answer(f"Куплен {new_item.name}!")
            await query.edit_message_text(f"Вы купили {new_item.name}.\n\n{get_item_desc(new_item)}", parse_mode=ParseMode.MARKDOWN, reply_markup=get_main_menu_kb())
        else:
            await query.answer("Недостаточно золота!")

    elif data == "inventory":
        if not p.inventory:
            await query.edit_message_text("Сумка пуста.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Назад", callback_data="main_menu")]]))
            return
        kb = []
        for i, item in enumerate(p.inventory):
            eq = " (Надето)" if item in p.equipped.values() else ""
            kb.append([InlineKeyboardButton(f"{item.name}{eq}", callback_data=f"item_{i}")])
        kb.append([InlineKeyboardButton("Назад", callback_data="main_menu")])
        await query.edit_message_text("Ваши вещи:", reply_markup=InlineKeyboardMarkup(kb))

    elif data.startswith("item_"):
        idx = int(data.split("_")[1])
        item = p.inventory[idx]
        text = get_item_desc(item)
        text += f"\n💰 Ваше золото: {p.gold}"
        
        kb = []
        if p.equipped[item.item_type] == item:
            kb.append([InlineKeyboardButton("Снять", callback_data=f"unequip_{idx}")])
        else:
            kb.append([InlineKeyboardButton("Надеть", callback_data=f"equip_{idx}")])
        
        # Исправление бага с обрезанием названий и лишними точками
        for s_key in item.stats.keys():
            cost = item.get_upgrade_price(s_key)
            # Убираем слово "Улучшить" из самой кнопки, чтобы влезло полное название стата
            btn_text = f"🔼 {STATS_NAMES[s_key]} ({cost}💰)"
            kb.append([InlineKeyboardButton(btn_text, callback_data=f"upg_{idx}_{s_key}")])
            
        kb.append([InlineKeyboardButton("Назад в сумку", callback_data="inventory")])
        await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(kb))

    elif data.startswith("upg_"):
        parts = data.split("_")
        idx = int(parts[1])
        s_key = "_".join(parts[2:]) # Корректно собираем ключ, если в нем есть подчеркивания
        item = p.inventory[idx]
        cost = item.get_upgrade_price(s_key)
        
        if p.gold >= cost:
            p.gold -= cost
            item.upgrade(s_key)
            await query.answer("Успешно улучшено!")
            # Обновляем меню этого же предмета
            await handle_buttons(update, context) 
        else:
            await query.answer(f"Нужно {cost} золота!")

    elif data.startswith("equip_"):
        idx = int(data.split("_")[1])
        item = p.inventory[idx]
        p.equipped[item.item_type] = item
        await query.answer("Экипировано!")
        await handle_buttons(update, context)

    elif data.startswith("unequip_"):
        idx = int(data.split("_")[1])
        item = p.inventory[idx]
        p.equipped[item.item_type] = None
        await query.answer("Снято!")
        await handle_buttons(update, context)

def main():
    if not TOKEN:
        print("Ошибка: Токен не найден в переменных окружения.")
        return

    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(handle_buttons))

    print("Бот запущен...")
    application.run_polling()

if __name__ == "__main__":
    main()
