import telebot
from telebot import types
import json
import time
import random
import os
import threading

TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
bot = telebot.TeleBot(TOKEN)

DB_FILE = 'database.json'
db_lock = threading.Lock()

# ==========================================
# СЛОВАРЬ ЛОКАЛИЗАЦИИ СТАТОВ
# ==========================================
STAT_RU = {
    "max_hp": "Макс. Здоровье", "hp": "Здоровье", "max_mp": "Макс. Мана", "mp": "Мана",
    "atk": "Физ. Атака", "def": "Физ. Защита", "m_shield": "Магический Щит",
    "crit_chance": "Шанс Крита (%)", "evasion": "Уклонение (%)", "atk_spd": "Скор. Атаки",
    "hp_regen": "Реген Здоровья", "mp_regen": "Реген Маны",
    "drop_chance": "Множитель Дропа", "drop_rarity": "Удача (Качество)",
    "lifesteal": "Вампиризм (%)", "armor_pen": "Пробитие Брони",
    "magic_atk": "Маг. Атака", "magic_res": "Маг. Сопротивление", "thorns": "Шипы (%)"
}

# ==========================================
# КОНФИГ БАЛАНСА И ИГРЫ
# ==========================================
CONFIG = {
    "time_train": 600,       
    "time_death": 3600,      
    "time_expedition": 1800, 
    "time_shop_update": 600, 

    "train_gold_base": 50,
    "train_gold_inc": 15,    
    
    "upgrade_item_base": 100,
    "upgrade_item_inc": 25,  
    
    "upgrade_ability_base": 200,
    "upgrade_ability_inc": 50,

    "inv_slot_price_base": 500,
    "inv_slot_price_inc": 500,

    "stat_inc": {
        "max_hp": 10, "max_mp": 5, "atk": 2, "def": 1, 
        "m_shield": 1, "crit_chance": 0.5, "evasion": 0.5, 
        "atk_spd": 0.1, "hp_regen": 1, "mp_regen": 0.5,
        "drop_chance": 0.1, "drop_rarity": 0.1,
        "lifesteal": 0.5, "armor_pen": 1, "magic_atk": 2, 
        "magic_res": 1, "thorns": 0.5
    },

    "enemy_base_stats": {
        "hp": 50, "atk": 5, "def": 2, "atk_spd": 1.0, "evasion": 2.0,
        "magic_atk": 0, "magic_res": 0
    },
    "enemy_stat_scale": { 
        "hp": 15, "atk": 2.5, "def": 1, "atk_spd": 0.05, "evasion": 0.2,
        "magic_atk": 1.5, "magic_res": 0.5
    },
    
    "rarity_multipliers": {
        "common": {"mult": 1.0, "weight": 100},
        "uncommon": {"mult": 1.5, "weight": 40},
        "rare": {"mult": 2.0, "weight": 15},
        "epic": {"mult": 3.0, "weight": 5},
        "legendary": {"mult": 5.0, "weight": 1}
    }
}

# ==========================================
# БАЗА ДАННЫХ И СОСТОЯНИЯ
# ==========================================
db = {}

def load_db():
    global db
    with db_lock:
        if os.path.exists(DB_FILE):
            with open(DB_FILE, 'r', encoding='utf-8') as f:
                db = json.load(f)
        else:
            db = {"players": {}, "shop": {"assortment": [], "last_update": 0}}
            _save_db_unlocked()

def save_db():
    with db_lock:
        _save_db_unlocked()

def _save_db_unlocked():
    with open(DB_FILE, 'w', encoding='utf-8') as f:
        json.dump(db, f, ensure_ascii=False, indent=4)

# ==========================================
# КЛАСС ИГРОКА И ЛОГИКА
# ==========================================
class Player:
    def __init__(self, uid, name):
        self.uid = str(uid)
        self.name = name
        self.gold = 100
        self.level = 1 
        
        self.stats = {
            "max_hp": 100, "hp": 100, "max_mp": 50, "mp": 50,
            "atk": 10, "def": 5, "m_shield": 0, 
            "crit_chance": 5.0, "evasion": 5.0, "atk_spd": 1.0, 
            "hp_regen": 1.0, "mp_regen": 1.0,
            "drop_chance": 1.0, "drop_rarity": 1.0,
            "lifesteal": 0.0, "armor_pen": 0,
            "magic_atk": 0, "magic_res": 0, "thorns": 0.0
        }
        self.stat_levels = {k: 0 for k in self.stats.keys()}
        
        self.inv_slots = 10
        self.inventory = [] 
        self.equip = {"weapon": None, "armor": None, "accessory": None}
        
        self.abilities = [] 
        self.active_abilities = [None, None] 
        
        self.state = 'idle'
        self.state_end_time = 0
        self.training_stat = None
        self.target_hunt_level = 1
        self.last_regen_time = time.time()

    @classmethod
    def from_dict(cls, data):
        p = cls(data['uid'], data['name'])
        for k, v in data.items():
            if k == 'stats' or k == 'stat_levels':
                for stat_key in p.stats.keys():
                    if stat_key not in v:
                        v[stat_key] = 0.0 if 'chance' in stat_key or 'regen' in stat_key or 'steal' in stat_key or 'thorns' in stat_key else 0
            setattr(p, k, v)
        if not hasattr(p, 'target_hunt_level'): p.target_hunt_level = p.level
        if not hasattr(p, 'last_regen_time'): p.last_regen_time = time.time()
        return p

def get_player(user_id, name="Hero"):
    uid = str(user_id)
    with db_lock:
        if uid not in db['players']:
            db['players'][uid] = Player(uid, name).__dict__
            _save_db_unlocked()
        data = db['players'][uid]
    return Player.from_dict(data)

def save_player(player):
    with db_lock:
        db['players'][player.uid] = player.__dict__
        _save_db_unlocked()

def apply_passive_regen(player):
    now = time.time()
    delta = now - player.last_regen_time
    if delta >= 60:
        mins = int(delta / 60)
        t_stats = get_total_stats(player)
        
        player.stats['hp'] = min(t_stats['max_hp'], player.stats['hp'] + (t_stats['hp_regen'] * mins))
        player.stats['mp'] = min(t_stats['max_mp'], player.stats['mp'] + (t_stats['mp_regen'] * mins))
        
        player.last_regen_time = now - (delta % 60)
        save_player(player)

# ==========================================
# ФОНОВЫЙ ПОТОК (ОБРАБОТКА ТАЙМЕРОВ)
# ==========================================
def background_worker():
    while True:
        time.sleep(10)
        now = time.time()
        changed = False
        with db_lock:
            for uid, p_data in list(db['players'].items()):
                player = Player.from_dict(p_data)
                
                # Проверка завершения таймеров (только если время вышло)
                if player.state != 'idle' and now >= player.state_end_time:
                    if player.state == 'dead':
                        player.stats['hp'] = player.stats['max_hp']
                        bot.send_message(uid, "👼 Вы воскресли и готовы к новым битвам!")
                    
                    elif player.state == 'training':
                        stat = player.training_stat
                        player.stats[stat] += CONFIG["stat_inc"].get(stat, 1)
                        player.stat_levels[stat] += 1
                        if stat in ["max_hp", "max_mp"]:
                            player.stats[stat.replace("max_", "")] = player.stats[stat] 
                        bot.send_message(uid, f"🏋️‍♂️ Тренировка завершена! Характеристика **{STAT_RU.get(stat, stat)}** улучшена.", parse_mode="Markdown")
                    
                    elif player.state == 'expedition':
                        gold_found = random.randint(50, 150) + (player.level * 10)
                        player.gold += gold_found
                        msg = f"🧭 Экспедиция завершена!\nВы нашли: 💰 {gold_found} золота."
                        
                        if random.random() < (0.3 * player.stats["drop_chance"]):
                            item = generate_item(player.level, player.stats["drop_rarity"])
                            if len(player.inventory) < player.inv_slots:
                                player.inventory.append(item)
                                msg += f"\nТакже вы нашли предмет: 📦 {item['name']}"
                            else:
                                msg += "\nВы нашли предмет, но в инвентаре нет места!"
                        bot.send_message(uid, msg)

                    player.state = 'idle'
                    player.training_stat = None
                    db['players'][uid] = player.__dict__
                    changed = True
                    
        if changed:
            save_db()

# Запускаем фоновый поток
threading.Thread(target=background_worker, daemon=True).start()

# ==========================================
# ГЕНЕРАТОРЫ И МАГАЗИН
# ==========================================
def get_random_rarity(rarity_bonus=1.0):
    weights = [v["weight"] for v in CONFIG["rarity_multipliers"].values()]
    weights[0] = max(10, int(weights[0] / rarity_bonus)) 
    keys = list(CONFIG["rarity_multipliers"].keys())
    return random.choices(keys, weights=weights, k=1)[0]

def generate_enemy(level):
    variance = random.uniform(0.8, 1.2) 
    
    e_stats = {k: int((CONFIG["enemy_base_stats"][k] + (level * CONFIG["enemy_stat_scale"].get(k, 0))) * variance) 
               for k in ["hp", "atk", "def", "magic_atk", "magic_res"]}
    e_stats["atk_spd"] = max(0.5, CONFIG["enemy_base_stats"]["atk_spd"] + (level * CONFIG["enemy_stat_scale"]["atk_spd"]) * variance)
    e_stats["evasion"] = min(50.0, CONFIG["enemy_base_stats"]["evasion"] + (level * CONFIG["enemy_stat_scale"]["evasion"]) * variance)
    
    names = ["Гоблин", "Скелет", "Орк", "Разбойник", "Волк", "Голем", "Демон"]
    prefixes = ["Слабый", "Обычный", "Свирепый", "Древний", "Элитный"]
    
    return {
        "name": f"{random.choice(prefixes)} {random.choice(names)}",
        "level": level,
        "max_hp": e_stats["hp"],
        "hp": e_stats["hp"],
        "atk": e_stats["atk"],
        "def": e_stats["def"],
        "magic_atk": e_stats["magic_atk"],
        "magic_res": e_stats["magic_res"],
        "atk_spd": e_stats["atk_spd"],
        "evasion": e_stats["evasion"]
    }

def generate_item(level, rarity_bonus=1.0):
    i_type = random.choice(["weapon", "armor", "accessory"])
    rarity_key = get_random_rarity(rarity_bonus)
    rarity_data = CONFIG["rarity_multipliers"][rarity_key]
    
    base_val = int((level * 2) * rarity_data["mult"])
    
    if i_type == "weapon":
        stat = random.choice(["atk", "magic_atk", "armor_pen"])
        name = f"Оружие ур.{level}"
    elif i_type == "armor":
        stat = random.choice(["def", "magic_res", "max_hp"])
        name = f"Броня ур.{level}"
    else:
        stat = random.choice(["crit_chance", "evasion", "lifesteal", "thorns"])
        name = f"Амулет ур.{level}"
        
    return {
        "id": "i_" + str(time.time()).replace(".", "") + str(random.randint(10,99)),
        "name": name,
        "type": i_type,
        "level": level,
        "rarity": rarity_key,
        "stat": stat,
        "value": base_val,
        "price": int((level * 10) * rarity_data["mult"])
    }

def generate_ability(level, rarity_bonus=1.0):
    rarity_key = get_random_rarity(rarity_bonus)
    rarity_data = CONFIG["rarity_multipliers"][rarity_key]
    
    a_type = random.choice(["heal", "power_strike", "magic_blast"])
    val = int((level * 5) * rarity_data["mult"])
    mp_cost = int(10 + (level * 2))
    
    names = {"heal": "Исцеление", "power_strike": "Мощный Удар", "magic_blast": "Взрыв Магии"}
    
    return {
        "id": "a_" + str(time.time()).replace(".", "") + str(random.randint(10,99)),
        "name": f"{names[a_type]} ур.{level}",
        "type": a_type,
        "level": level,
        "rarity": rarity_key,
        "value": val,
        "mp_cost": mp_cost,
        "price": int((level * 20) * rarity_data["mult"])
    }

def update_shop_if_needed(player_level):
    now = time.time()
    if now - db["shop"]["last_update"] > CONFIG["time_shop_update"]:
        db["shop"]["assortment"] = []
        shop_lvl = max(1, player_level + random.randint(0, 5))
        for _ in range(3):
            db["shop"]["assortment"].append({"item": generate_item(shop_lvl), "sold": False})
        for _ in range(2):
            db["shop"]["assortment"].append({"ability": generate_ability(shop_lvl), "sold": False})
            
        db["shop"]["last_update"] = now
        save_db()

# ==========================================
# БОЕВАЯ СИСТЕМА (В РЕАЛЬНОМ ВРЕМЕНИ)
# ==========================================
def get_total_stats(player):
    total = player.stats.copy()
    for eq_type, item in player.equip.items():
        if item:
            total[item["stat"]] += item["value"]
    return total

def simulate_combat_realtime(player, enemy):
    p_stats = get_total_stats(player)
    e_stats = enemy.copy()
    
    log = [f"⚔️ **Бой начался!** {player.name} против {enemy['name']} (Ур.{enemy['level']})"]
    
    # Кулдаун атаки зависит от скорости: 1.0 / atk_spd = секунды между ударами
    p_cooldown = 1.0 / max(0.1, p_stats["atk_spd"])
    e_cooldown = 1.0 / max(0.1, e_stats["atk_spd"])
    
    tick = 0.1 # Шаг симуляции 0.1 сек
    time_elapsed = 0.0
    max_time = 180.0 # Ограничение боя в 3 минуты реального времени
    
    while p_stats["hp"] > 0 and e_stats["hp"] > 0 and time_elapsed < max_time:
        
        # Регенерация раз в 1 секунду (равна regen / 60)
        if abs((time_elapsed % 1.0) - 0.0) < 0.05:
            p_stats["hp"] = min(p_stats["max_hp"], p_stats["hp"] + p_stats["hp_regen"] / 60.0)
            p_stats["mp"] = min(p_stats["max_mp"], p_stats["mp"] + p_stats["mp_regen"] / 60.0)
            
        p_cooldown -= tick
        e_cooldown -= tick
        
        # --- УДАР ИГРОКА ---
        if p_cooldown <= 0 and p_stats["hp"] > 0:
            p_cooldown += 1.0 / max(0.1, p_stats["atk_spd"])
            
            # Способности
            ability_used = False
            for ab in player.active_abilities:
                if ab and p_stats["mp"] >= ab["mp_cost"]:
                    p_stats["mp"] -= ab["mp_cost"]
                    ability_used = True
                    if ab["type"] == "heal":
                        heal_amt = ab["value"]
                        p_stats["hp"] = min(p_stats["max_hp"], p_stats["hp"] + heal_amt)
                        log.append(f"[{time_elapsed:.1f}с] ✨ {ab['name']}: исцеление +{heal_amt} ХП!")
                    elif ab["type"] == "power_strike":
                        dmg = max(1, ab["value"] + p_stats["atk"] - e_stats["def"])
                        e_stats["hp"] -= dmg
                        log.append(f"[{time_elapsed:.1f}с] 💥 {ab['name']}: {dmg} урона!")
                    elif ab["type"] == "magic_blast":
                        dmg = max(1, ab["value"] + p_stats["magic_atk"] - e_stats["magic_res"])
                        e_stats["hp"] -= dmg
                        log.append(f"[{time_elapsed:.1f}с] 🔮 {ab['name']}: {dmg} маг. урона!")
                    break 
            
            # Обычный удар
            if not ability_used and e_stats["hp"] > 0:
                if random.random() * 100 > e_stats["evasion"]:
                    eff_def = max(0, e_stats["def"] - p_stats["armor_pen"])
                    dmg = max(0, p_stats["atk"] - eff_def)
                    magic_dmg = max(0, p_stats["magic_atk"] - e_stats["magic_res"])
                    total_dmg = dmg + magic_dmg
                    if total_dmg <= 0: total_dmg = 1
                    
                    if random.random() * 100 < p_stats["crit_chance"]:
                        total_dmg *= 2
                        log.append(f"[{time_elapsed:.1f}с] 🔥 КРИТ! Вы нанесли {total_dmg:.1f} урона.")
                    else:
                        log.append(f"[{time_elapsed:.1f}с] 🗡 Вы нанесли {total_dmg:.1f} урона.")
                        
                    e_stats["hp"] -= total_dmg
                    
                    if p_stats["lifesteal"] > 0:
                        ls_heal = total_dmg * (p_stats["lifesteal"] / 100.0)
                        p_stats["hp"] = min(p_stats["max_hp"], p_stats["hp"] + ls_heal)
                else:
                    log.append(f"[{time_elapsed:.1f}с] 💨 Враг уклонился!")

        # --- УДАР ВРАГА ---
        if e_stats["hp"] > 0 and e_cooldown <= 0:
            e_cooldown += 1.0 / max(0.1, e_stats["atk_spd"])
            
            if random.random() * 100 > p_stats["evasion"]:
                eff_def = p_stats["def"]
                dmg = max(0, e_stats["atk"] - eff_def)
                magic_dmg = max(0, e_stats["magic_atk"] - p_stats["magic_res"])
                total_dmg = dmg + magic_dmg
                if total_dmg <= 0: total_dmg = 1

                if p_stats["m_shield"] > 0:
                    absorbed = min(total_dmg, p_stats["m_shield"])
                    p_stats["m_shield"] -= absorbed
                    total_dmg -= absorbed
                
                p_stats["hp"] -= total_dmg
                log.append(f"[{time_elapsed:.1f}с] 🩸 Враг нанес {total_dmg:.1f} урона.")
                
                if p_stats["thorns"] > 0 and total_dmg > 0:
                    thorns_dmg = total_dmg * (p_stats["thorns"] / 100.0)
                    e_stats["hp"] -= thorns_dmg
                    log.append(f"[{time_elapsed:.1f}с] 🌵 Шипы вернули {thorns_dmg:.1f} урона.")
            else:
                log.append(f"[{time_elapsed:.1f}с] 🌀 Вы уклонились!")

        time_elapsed += tick

    player.stats["hp"] = max(0, p_stats["hp"]) 
    player.stats["mp"] = max(0, p_stats["mp"])
    
    if time_elapsed >= max_time:
        return False, log, "⏳ Время боя вышло! Враг сбежал, а вы истощены."
    elif player.stats["hp"] <= 0:
        return False, log, "💀 Вы погибли! Восстановление займет 1 час."
    else:
        return True, log, "🏆 Вы победили!"

# ==========================================
# UI И КЛАВИАТУРЫ
# ==========================================
def main_menu_kbd():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🗡 Охота", callback_data="menu_hunt"),
        types.InlineKeyboardButton("🏋️ Тренировка", callback_data="menu_train")
    )
    markup.add(
        types.InlineKeyboardButton("🎒 Инвентарь", callback_data="menu_inv"),
        types.InlineKeyboardButton("✨ Навыки", callback_data="menu_skills")
    )
    markup.add(
        types.InlineKeyboardButton("🏪 Магазин", callback_data="menu_shop"),
        types.InlineKeyboardButton("🧭 Экспедиция", callback_data="menu_exped")
    )
    markup.add(types.InlineKeyboardButton("👤 Герой", callback_data="menu_profile"))
    return markup

def cancel_action_kbd():
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("❌ Отменить действие", callback_data="cancel_action"))
    return markup

def paginate_stats_kbd(player, page=0):
    stats = list(player.stat_levels.keys())
    per_page = 6
    total_pages = (len(stats) + per_page - 1) // per_page
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    start = page * per_page
    end = start + per_page
    
    buttons = []
    for stat in stats[start:end]:
        lvl = player.stat_levels[stat]
        cost = CONFIG["train_gold_base"] + (lvl * CONFIG["train_gold_inc"])
        stat_name = STAT_RU.get(stat, stat)
        buttons.append(types.InlineKeyboardButton(f"{stat_name} (Ур.{lvl}) - 💰 {cost}", callback_data=f"train_{stat}"))
    markup.add(*buttons)
    
    nav_buttons = []
    if page > 0:
        nav_buttons.append(types.InlineKeyboardButton("⬅️ Пред.", callback_data=f"trainpage_{page-1}"))
    if page < total_pages - 1:
        nav_buttons.append(types.InlineKeyboardButton("След. ➡️", callback_data=f"trainpage_{page+1}"))
        
    if nav_buttons:
        markup.add(*nav_buttons)
        
    markup.add(types.InlineKeyboardButton("🔙 В меню", callback_data="menu_profile"))
    return markup

def hunt_menu_kbd(level):
    markup = types.InlineKeyboardMarkup(row_width=3)
    markup.add(
        types.InlineKeyboardButton("◀️", callback_data="hunt_dec"),
        types.InlineKeyboardButton(f"Ур. {level}", callback_data="hunt_set"),
        types.InlineKeyboardButton("▶️", callback_data="hunt_inc")
    )
    markup.add(types.InlineKeyboardButton("⚔️ Начать поиск", callback_data="hunt_start"))
    markup.add(types.InlineKeyboardButton("🔙 Назад", callback_data="menu_profile"))
    return markup

# ==========================================
# ОБРАБОТЧИКИ СООБЩЕНИЙ
# ==========================================
@bot.message_handler(commands=['start'])
def start_game(message):
    load_db()
    player = get_player(message.from_user.id, message.from_user.first_name)
    bot.send_message(message.chat.id, 
                     f"Добро пожаловать в Endless RPG, {player.name}!\nЭто мир бесконечного развития. Твоя сила ограничивается только твоим временем.",
                     reply_markup=main_menu_kbd())

@bot.message_handler(commands=['relive'])
def command_relive(message):
    load_db()
    player = get_player(message.from_user.id)
    if player.state == 'dead':
        player.state = 'idle'
        player.state_end_time = 0
        player.stats['hp'] = player.stats['max_hp']
        save_player(player)
        bot.send_message(message.chat.id, "✨ Силой магии разработчика вы мгновенно воскресли!", reply_markup=main_menu_kbd())
    else:
        bot.send_message(message.chat.id, "Вы и так живы!")

def set_hunt_level_handler(message, uid):
    try:
        lvl = int(message.text)
        if lvl > 0:
            player = get_player(uid)
            player.target_hunt_level = lvl
            save_player(player)
            bot.send_message(message.chat.id, f"Уровень угрозы установлен на {lvl}.", reply_markup=hunt_menu_kbd(lvl))
        else:
            bot.send_message(message.chat.id, "Число должно быть больше нуля.", reply_markup=hunt_menu_kbd(1))
    except ValueError:
        bot.send_message(message.chat.id, "Ошибка ввода. Ожидалось число.", reply_markup=hunt_menu_kbd(1))

@bot.callback_query_handler(func=lambda call: True)
def handle_query(call):
    load_db()
    player = get_player(call.from_user.id)
    apply_passive_regen(player)
    
    if call.data == "cancel_action":
        if player.state in ['training', 'expedition']:
            player.state = 'idle'
            player.state_end_time = 0
            player.training_stat = None
            save_player(player)
            bot.edit_message_text("Действие отменено.", call.message.chat.id, call.message.message_id, reply_markup=main_menu_kbd())
        else:
            bot.answer_callback_query(call.id, "Отменять нечего.")
        return

    # Проверка на занятость/смерть
    if player.state != 'idle':
        time_left = int((player.state_end_time - time.time()) / 60)
        if player.state == 'dead':
            bot.answer_callback_query(call.id, f"Вы мертвы. Воскрешение через: ~{time_left} мин.", show_alert=True)
        else:
            state_rus = {"training": "Тренируетесь", "expedition": "В экспедиции"}.get(player.state, player.state)
            bot.answer_callback_query(call.id, f"Вы заняты ({state_rus}). Осталось: ~{time_left} мин.", show_alert=True)
        return

    # ================= ПРОФИЛЬ =================
    if call.data == "menu_profile":
        t_stats = get_total_stats(player)
        text = f"👤 **Профиль: {player.name} (Ур.{player.level})**\n💰 Золото: {player.gold}\n\n"
        text += f"❤️ {STAT_RU['hp']}: {player.stats['hp']:.1f}/{t_stats['max_hp']} (+{t_stats['hp_regen']}/мин)\n"
        text += f"💧 {STAT_RU['mp']}: {player.stats['mp']:.1f}/{t_stats['max_mp']} (+{t_stats['mp_regen']}/мин)\n"
        text += f"⚔️ {STAT_RU['atk']}: {t_stats['atk']} | 🔮 {STAT_RU['magic_atk']}: {t_stats['magic_atk']}\n"
        text += f"🛡 {STAT_RU['def']}: {t_stats['def']} | 💠 {STAT_RU['magic_res']}: {t_stats['magic_res']}\n"
        text += f"💥 {STAT_RU['crit_chance']}: {t_stats['crit_chance']}% | 💨 {STAT_RU['evasion']}: {t_stats['evasion']}%\n"
        text += f"🦇 {STAT_RU['lifesteal']}: {t_stats['lifesteal']}% | 🌵 {STAT_RU['thorns']}: {t_stats['thorns']}%\n"
        text += f"🪓 {STAT_RU['armor_pen']}: {t_stats['armor_pen']} | 🛡 {STAT_RU['m_shield']}: {t_stats['m_shield']}\n"
        text += f"⚡️ {STAT_RU['atk_spd']}: {t_stats['atk_spd']} | 🍀 {STAT_RU['drop_chance']}: x{t_stats['drop_chance']}\n"
        
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=main_menu_kbd())

    # ================= ТРЕНИРОВКА =================
    elif call.data == "menu_train" or call.data.startswith("trainpage_"):
        page = 0 if call.data == "menu_train" else int(call.data.split("_")[1])
        bot.edit_message_text("Выберите характеристику для тренировки (10 минут):", call.message.chat.id, call.message.message_id, reply_markup=paginate_stats_kbd(player, page))

    elif call.data.startswith("train_"):
        stat = call.data.split("_", 1)[1]
        cost = CONFIG["train_gold_base"] + (player.stat_levels[stat] * CONFIG["train_gold_inc"])
        if player.gold >= cost:
            player.gold -= cost
            player.state = 'training'
            player.training_stat = stat
            player.state_end_time = time.time() + CONFIG["time_train"]
            save_player(player)
            bot.edit_message_text(f"Вы начали тренировку **{STAT_RU.get(stat, stat)}**. Вернитесь через 10 минут.", call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=cancel_action_kbd())
        else:
            bot.answer_callback_query(call.id, "Недостаточно золота!", show_alert=True)

    # ================= ОХОТА =================
    elif call.data == "menu_hunt":
        bot.edit_message_text("⚔️ Установите уровень угрозы для поиска врагов:", call.message.chat.id, call.message.message_id, reply_markup=hunt_menu_kbd(player.target_hunt_level))

    elif call.data == "hunt_dec":
        if player.target_hunt_level > 1:
            player.target_hunt_level -= 1
            save_player(player)
            bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=hunt_menu_kbd(player.target_hunt_level))
        else:
            bot.answer_callback_query(call.id, "Минимальный уровень: 1")

    elif call.data == "hunt_inc":
        player.target_hunt_level += 1
        save_player(player)
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=hunt_menu_kbd(player.target_hunt_level))

    elif call.data == "hunt_set":
        msg = bot.send_message(call.message.chat.id, "Отправьте числом желаемый уровень угрозы:")
        bot.register_next_step_handler(msg, set_hunt_level_handler, player.uid)

    elif call.data == "hunt_start":
        enemy = generate_enemy(player.target_hunt_level)
        
        is_win, log, result_msg = simulate_combat_realtime(player, enemy)
        
        if is_win:
            gold_drop = int((10 + enemy["level"] * 5) * player.stats["drop_chance"])
            player.gold += gold_drop
            result_msg += f"\nВы получили: 💰 {gold_drop} золота."
            
            if random.random() < (0.2 * player.stats["drop_chance"]):
                if len(player.inventory) < player.inv_slots:
                    item = generate_item(enemy["level"], player.stats["drop_rarity"])
                    player.inventory.append(item)
                    result_msg += f"\n📦 Выпал предмет: {item['name']}"
                else:
                    result_msg += "\n📦 Предмет выпал, но инвентарь полон!"
                    
            if random.random() < (0.05 * player.stats["drop_chance"]):
                skill = generate_ability(enemy["level"], player.stats["drop_rarity"])
                player.abilities.append(skill)
                result_msg += f"\n✨ Изучен навык: {skill['name']}!"
                    
            player.level += 1 
        elif "погибли" in result_msg:
            player.state = 'dead'
            player.state_end_time = time.time() + CONFIG["time_death"]
            
        save_player(player)
        
        log_text = "\n".join(log)
        if len(log_text) > 2500:
            log_text = log_text[:1200] + "\n... [БОЙ СЛИШКОМ ДОЛГИЙ] ...\n" + log_text[-1200:]
            
        bot.edit_message_text(f"{log_text}\n\n**{result_msg}**", call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=main_menu_kbd() if is_win else cancel_action_kbd())

    # ================= ИНВЕНТАРЬ =================
    elif call.data == "menu_inv":
        text = f"🎒 **Инвентарь ({len(player.inventory)}/{player.inv_slots})**\n\n"
        markup = types.InlineKeyboardMarkup()
        
        # Экипированные предметы
        for slot, item in player.equip.items():
            slot_ru = {"weapon": "Оружие", "armor": "Броня", "accessory": "Амулет"}[slot]
            if item:
                stat_ru = STAT_RU.get(item['stat'], item['stat'])
                markup.add(types.InlineKeyboardButton(f"[{slot_ru}] {item['name']} | Снять", callback_data=f"unequip_{slot}"))
            else:
                text += f"[{slot_ru}]: Пусто\n"
                
        text += "\nВ сумке:\n"
        for i, item in enumerate(player.inventory):
            stat_ru = STAT_RU.get(item['stat'], item['stat'])
            markup.add(types.InlineKeyboardButton(f"{item['name']} (+{item['value']} {stat_ru})", callback_data=f"item_{i}"))
            
        markup.add(types.InlineKeyboardButton("🔙 Назад", callback_data="menu_profile"))
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    elif call.data.startswith("unequip_"):
        slot = call.data.split("_")[1]
        item = player.equip[slot]
        if item:
            if len(player.inventory) < player.inv_slots:
                player.inventory.append(item)
                player.equip[slot] = None
                save_player(player)
                bot.answer_callback_query(call.id, f"Предмет снят!")
                call.data = "menu_inv"
                handle_query(call)
            else:
                bot.answer_callback_query(call.id, "В инвентаре нет места!", show_alert=True)

    elif call.data.startswith("item_"):
        idx = int(call.data.split("_")[1])
        if idx >= len(player.inventory):
            return
            
        item = player.inventory[idx]
        stat_ru = STAT_RU.get(item['stat'], item['stat'])
        type_ru = {"weapon": "Оружие", "armor": "Броня", "accessory": "Амулет"}[item['type']]
        text = f"📦 **{item['name']}**\nТип: {type_ru}\nУлучшает: {stat_ru} +{item['value']}\nУровень предмета: {item['level']}"
        
        upg_cost = CONFIG["upgrade_item_base"] + (item['level'] * CONFIG["upgrade_item_inc"])
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("Надеть", callback_data=f"equip_{idx}"))
        markup.add(types.InlineKeyboardButton(f"Улучшить (💰 {upg_cost})", callback_data=f"upgitem_{idx}"))
        markup.add(types.InlineKeyboardButton("Продать (💰 50%)", callback_data=f"sellitem_{idx}"))
        markup.add(types.InlineKeyboardButton("🔙 В инвентарь", callback_data="menu_inv"))
        
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    elif call.data.startswith("equip_"):
        idx = int(call.data.split("_")[1])
        item = player.inventory.pop(idx) 
        old_equip = player.equip[item['type']]
        player.equip[item['type']] = item
        if old_equip:
            player.inventory.append(old_equip) 
        save_player(player)
        bot.answer_callback_query(call.id, f"Экипировано: {item['name']}")
        call.data = "menu_inv"
        handle_query(call)

    elif call.data.startswith("upgitem_"):
        idx = int(call.data.split("_")[1])
        item = player.inventory[idx]
        upg_cost = CONFIG["upgrade_item_base"] + (item['level'] * CONFIG["upgrade_item_inc"])
        
        if player.gold >= upg_cost:
            player.gold -= upg_cost
            item['level'] += 1
            inc = 5 * CONFIG["rarity_multipliers"][item['rarity']]["mult"]
            item['value'] += int(inc) 
            save_player(player)
            bot.answer_callback_query(call.id, "Предмет улучшен!")
            call.data = f"item_{idx}"
            handle_query(call)
        else:
            bot.answer_callback_query(call.id, "Недостаточно золота!", show_alert=True)

    elif call.data.startswith("sellitem_"):
        idx = int(call.data.split("_")[1])
        item = player.inventory.pop(idx)
        earn = max(10, item.get("price", 50) // 2)
        player.gold += earn
        save_player(player)
        bot.answer_callback_query(call.id, f"Продано за {earn} золота.")
        call.data = "menu_inv"
        handle_query(call)

    # ================= НАВЫКИ =================
    elif call.data == "menu_skills":
        text = f"✨ **Ваши Навыки**\n\nАктивные:\n"
        for i, ab in enumerate(player.active_abilities):
            text += f"Слот {i+1}: {ab['name'] if ab else 'Пусто'} (МП: {ab['mp_cost'] if ab else 0})\n"
            
        markup = types.InlineKeyboardMarkup()
        for i, ab in enumerate(player.abilities):
            markup.add(types.InlineKeyboardButton(f"{ab['name']} (МП: {ab['mp_cost']})", callback_data=f"skill_{i}"))
        markup.add(types.InlineKeyboardButton("Снять навыки", callback_data="unequip_skills"))
        markup.add(types.InlineKeyboardButton("🔙 Назад", callback_data="menu_profile"))
        
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    elif call.data == "unequip_skills":
        player.active_abilities = [None, None]
        save_player(player)
        bot.answer_callback_query(call.id, "Все навыки сняты.")
        call.data = "menu_skills"
        handle_query(call)

    elif call.data.startswith("skill_"):
        idx = int(call.data.split("_")[1])
        if idx >= len(player.abilities): return
            
        ab = player.abilities[idx]
        type_ru = {"heal": "Исцеление", "power_strike": "Физ. Урон", "magic_blast": "Маг. Урон"}[ab['type']]
        text = f"✨ **{ab['name']}**\nТип: {type_ru}\nСила: {ab['value']}\nСтоимость МП: {ab['mp_cost']}\nУровень: {ab['level']}"
        
        upg_cost = CONFIG["upgrade_ability_base"] + (ab['level'] * CONFIG["upgrade_ability_inc"])
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("В Слот 1", callback_data=f"eqskill_0_{idx}"),
                   types.InlineKeyboardButton("В Слот 2", callback_data=f"eqskill_1_{idx}"))
        markup.add(types.InlineKeyboardButton(f"Улучшить (💰 {upg_cost})", callback_data=f"upgskill_{idx}"))
        markup.add(types.InlineKeyboardButton("🔙 В навыки", callback_data="menu_skills"))
        
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    elif call.data.startswith("eqskill_"):
        parts = call.data.split("_")
        slot_idx = int(parts[1])
        skill_idx = int(parts[2])
        player.active_abilities[slot_idx] = player.abilities[skill_idx]
        save_player(player)
        bot.answer_callback_query(call.id, f"Навык экипирован в Слот {slot_idx+1}!")
        call.data = "menu_skills"
        handle_query(call)

    elif call.data.startswith("upgskill_"):
        idx = int(call.data.split("_")[1])
        ab = player.abilities[idx]
        upg_cost = CONFIG["upgrade_ability_base"] + (ab['level'] * CONFIG["upgrade_ability_inc"])
        
        if player.gold >= upg_cost:
            player.gold -= upg_cost
            ab['level'] += 1
            inc = 5 * CONFIG["rarity_multipliers"][ab['rarity']]["mult"]
            ab['value'] += int(inc)
            save_player(player)
            bot.answer_callback_query(call.id, "Навык улучшен!")
            call.data = f"skill_{idx}"
            handle_query(call)
        else:
            bot.answer_callback_query(call.id, "Недостаточно золота!", show_alert=True)

    # ================= ЭКСПЕДИЦИЯ =================
    elif call.data == "menu_exped":
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("Отправиться (30 мин)", callback_data="start_exped"))
        markup.add(types.InlineKeyboardButton("🔙 Назад", callback_data="menu_profile"))
        bot.edit_message_text("🧭 **Экспедиция**\nБезопасный поиск золота и ресурсов. Вы не сможете сражаться или тренироваться в это время.", call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    elif call.data == "start_exped":
        player.state = 'expedition'
        player.state_end_time = time.time() + CONFIG["time_expedition"]
        save_player(player)
        bot.edit_message_text("Вы отправились в экспедицию. Вернитесь через 30 минут.", call.message.chat.id, call.message.message_id, reply_markup=cancel_action_kbd())

    # ================= МАГАЗИН =================
    elif call.data == "menu_shop":
        update_shop_if_needed(player.level)
        cost_slot = CONFIG["inv_slot_price_base"] + ( (player.inv_slots - 10) * CONFIG["inv_slot_price_inc"] )
        
        text = "🏪 **Магазин (обновляется каждые 10 мин)**\nАссортимент:\n"
        markup = types.InlineKeyboardMarkup(row_width=1)
        
        for i, entry in enumerate(db["shop"]["assortment"]):
            if entry["sold"]: continue
            if "item" in entry:
                it = entry["item"]
                stat_ru = STAT_RU.get(it['stat'], it['stat'])
                markup.add(types.InlineKeyboardButton(f"📦 {it['name']} (+{it['value']} {stat_ru}) - 💰 {it['price']}", callback_data=f"buy_assort_{i}"))
            elif "ability" in entry:
                ab = entry["ability"]
                markup.add(types.InlineKeyboardButton(f"✨ {ab['name']} - 💰 {ab['price']}", callback_data=f"buy_assort_{i}"))

        markup.add(types.InlineKeyboardButton(f"Купить слот инвентаря (💰 {cost_slot})", callback_data="buy_slot"))
        markup.add(types.InlineKeyboardButton("Восстановить ХП/МП (💰 50)", callback_data="buy_heal"))
        markup.add(types.InlineKeyboardButton("🔙 Назад", callback_data="menu_profile"))
        
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    elif call.data.startswith("buy_assort_"):
        idx = int(call.data.split("_")[2])
        entry = db["shop"]["assortment"][idx]
        
        if entry["sold"]:
            bot.answer_callback_query(call.id, "Уже продано!")
            return
            
        obj = entry.get("item") or entry.get("ability")
        if player.gold >= obj["price"]:
            if "item" in entry:
                if len(player.inventory) < player.inv_slots:
                    player.gold -= obj["price"]
                    player.inventory.append(obj)
                    entry["sold"] = True
                    save_player(player)
                    bot.answer_callback_query(call.id, "Предмет куплен!")
                else:
                    bot.answer_callback_query(call.id, "Инвентарь полон!", show_alert=True)
                    return
            else:
                player.gold -= obj["price"]
                player.abilities.append(obj)
                entry["sold"] = True
                save_player(player)
                bot.answer_callback_query(call.id, "Навык куплен!")
            
            call.data = "menu_shop"
            handle_query(call)
        else:
            bot.answer_callback_query(call.id, "Недостаточно золота!", show_alert=True)

    elif call.data == "buy_slot":
        cost_slot = CONFIG["inv_slot_price_base"] + ( (player.inv_slots - 10) * CONFIG["inv_slot_price_inc"] )
        if player.gold >= cost_slot:
            player.gold -= cost_slot
            player.inv_slots += 1
            save_player(player)
            bot.answer_callback_query(call.id, "Слот куплен!")
            call.data = "menu_shop"
            handle_query(call)
        else:
            bot.answer_callback_query(call.id, "Недостаточно золота!", show_alert=True)
            
    elif call.data == "buy_heal":
        if player.gold >= 50:
            player.gold -= 50
            player.stats['hp'] = get_total_stats(player)['max_hp']
            player.stats['mp'] = get_total_stats(player)['max_mp']
            save_player(player)
            bot.answer_callback_query(call.id, "Здоровье и мана восстановлены!")
            call.data = "menu_shop"
            handle_query(call)
        else:
            bot.answer_callback_query(call.id, "Недостаточно золота!", show_alert=True)

if __name__ == '__main__':
    print("Бот запускается...")
    load_db()
    bot.infinity_polling(timeout=10, long_polling_timeout=5)
