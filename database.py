import aiosqlite
import json
from config import DB_NAME, BASE_STATS

class Database:
    def __init__(self):
        self.db_name = DB_NAME

    async def connect(self):
        self.conn = await aiosqlite.connect(self.db_name)
        await self.init_tables()

    async def init_tables(self):
        async with self.conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                gold INTEGER DEFAULT 0,
                stats TEXT DEFAULT '{}',
                inventory_slots INTEGER DEFAULT 10,
                lock_until INTEGER DEFAULT 0,
                death_until INTEGER DEFAULT 0,
                last_shop_refresh INTEGER DEFAULT 0,
                shop_items TEXT DEFAULT '[]',
                equipped TEXT DEFAULT '{}',
                skills TEXT DEFAULT '[]'
            )
        """):
            pass
        
        async with self.conn.execute("""
            CREATE TABLE IF NOT EXISTS inventory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                item_data TEXT
            )
        """):
            pass
        await self.conn.commit()

    async def get_user(self, user_id):
        async with self.conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            if not row:
                await self.create_user(user_id)
                return await self.get_user(user_id)
            
            # Парсинг данных
            return {
                "user_id": row[0],
                "gold": row[1],
                "stats": json.loads(row[2]) if row[2] else BASE_STATS.copy(),
                "inventory_slots": row[3],
                "lock_until": row[4],
                "death_until": row[5],
                "last_shop_refresh": row[6],
                "shop_items": json.loads(row[7]) if row[7] else [],
                "equipped": json.loads(row[8]) if row[8] else {},
                "skills": json.loads(row[9]) if row[9] else []
            }

    async def create_user(self, user_id):
        await self.conn.execute("INSERT INTO users (user_id, stats) VALUES (?, ?)", 
                                (user_id, json.dumps(BASE_STATS)))
        await self.conn.commit()

    async def update_user(self, user_id, **kwargs):
        sets = []
        values = []
        for key, value in kwargs.items():
            if isinstance(value, (list, dict)):
                value = json.dumps(value)
            sets.append(f"{key} = ?")
            values.append(value)
        values.append(user_id)
        query = f"UPDATE users SET {', '.join(sets)} WHERE user_id = ?"
        await self.conn.execute(query, values)
        await self.conn.commit()

    async def add_item(self, user_id, item_data):
        await self.conn.execute("INSERT INTO inventory (user_id, item_data) VALUES (?, ?)",
                                (user_id, json.dumps(item_data)))
        await self.conn.commit()

    async def get_inventory(self, user_id):
        async with self.conn.execute("SELECT id, item_data FROM inventory WHERE user_id = ?", (user_id,)) as cursor:
            return await cursor.fetchall()

    async def delete_item(self, item_id):
        await self.conn.execute("DELETE FROM inventory WHERE id = ?", (item_id,))
        await self.conn.commit()