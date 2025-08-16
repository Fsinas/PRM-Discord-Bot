import aiosqlite
import asyncio
import time

INIT_SQL = """
CREATE TABLE IF NOT EXISTS tickets (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  guild_id INTEGER NOT NULL,
  thread_id INTEGER NOT NULL UNIQUE,
  creator_id INTEGER NOT NULL,
  is_private INTEGER NOT NULL,
  status TEXT NOT NULL,
  title TEXT NOT NULL,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  claimed_by INTEGER,
  last_user_message_at INTEGER,
  closed_at INTEGER
);

CREATE TABLE IF NOT EXISTS config_overrides (
  guild_id INTEGER NOT NULL,
  key TEXT NOT NULL,
  value TEXT NOT NULL,
  PRIMARY KEY (guild_id,key)
);

CREATE TABLE IF NOT EXISTS blacklist (
  guild_id INTEGER NOT NULL,
  user_id INTEGER NOT NULL,
  reason TEXT,
  PRIMARY KEY (guild_id,user_id)
);
"""

class Database:
    def __init__(self, path: str):
        self.path = path
        self._lock = asyncio.Lock()

    async def init(self):
        async with aiosqlite.connect(self.path) as db:
            await db.executescript(INIT_SQL)
            await db.commit()

    async def execute(self, sql: str, *params):
        async with self._lock:
            async with aiosqlite.connect(self.path) as db:
                await db.execute(sql, params)
                await db.commit()

    async def fetchone(self, sql: str, *params):
        async with self._lock:
            async with aiosqlite.connect(self.path) as db:
                cur = await db.execute(sql, params)
                row = await cur.fetchone()
                await cur.close()
                return row

    async def fetchall(self, sql: str, *params):
        async with self._lock:
            async with aiosqlite.connect(self.path) as db:
                cur = await db.execute(sql, params)
                rows = await cur.fetchall()
                await cur.close()
                return rows

    async def create_ticket(self, guild_id:int, thread_id:int, creator_id:int, is_private:bool, title:str):
        now=int(time.time())
        await self.execute("""INSERT INTO tickets
            (guild_id,thread_id,creator_id,is_private,status,title,created_at,updated_at,last_user_message_at)
            VALUES (?,?,?,?,?,?,?,?,?)""",
            guild_id,thread_id,creator_id,1 if is_private else 0,"open",title,now,now,now)

    async def update_status(self, thread_id:int, status:str):
        await self.execute("UPDATE tickets SET status=?,updated_at=? WHERE thread_id=?",
                           status,int(time.time()),thread_id)

    async def set_claim(self, thread_id:int, member_id:int|None):
        await self.execute("UPDATE tickets SET claimed_by=?,updated_at=? WHERE thread_id=?",
                           member_id,int(time.time()),thread_id)

    async def close_ticket(self, thread_id:int, status:str):
        now=int(time.time())
        await self.execute("UPDATE tickets SET status=?,closed_at=?,updated_at=? WHERE thread_id=?",
                           status, now, now, thread_id)

    async def get_ticket_by_thread(self, thread_id:int):
        return await self.fetchone("SELECT * FROM tickets WHERE thread_id=?", thread_id)

    async def list_open_tickets_by_user(self, guild_id:int, user_id:int):
        return await self.fetchall("SELECT * FROM tickets WHERE guild_id=? AND creator_id=? AND status IN ('open','in_progress')",
                                   guild_id,user_id)

    async def count_by_status(self, guild_id:int):
        return await self.fetchall("SELECT status, COUNT(*) FROM tickets WHERE guild_id=? GROUP BY status", guild_id)

    async def tickets_stale(self, guild_id:int, older_than:int, private:bool):
        return await self.fetchall("""SELECT thread_id FROM tickets
             WHERE guild_id=? AND is_private=? AND status IN ('open','in_progress')
             AND last_user_message_at < ?""",
             guild_id,1 if private else 0, older_than)

    async def update_last_user_message(self, thread_id:int):
        await self.execute("UPDATE tickets SET last_user_message_at=?, updated_at=? WHERE thread_id=?",
                           int(time.time()), int(time.time()), thread_id)

    async def archive_purge_candidates(self, guild_id:int, older_than:int):
        return await self.fetchall("""SELECT thread_id FROM tickets
            WHERE guild_id=? AND status IN ('closed','solved','rejected') AND closed_at < ?""",
            guild_id, older_than)

    async def add_blacklist(self, guild_id:int, user_id:int, reason:str):
        await self.execute("INSERT OR REPLACE INTO blacklist (guild_id,user_id,reason) VALUES (?,?,?)",
                           guild_id,user_id,reason)

    async def is_blacklisted(self, guild_id:int, user_id:int):
        row = await self.fetchone("SELECT 1 FROM blacklist WHERE guild_id=? AND user_id=?", guild_id,user_id)
        return row is not None