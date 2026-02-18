import json
from uuid import uuid4

from service.storage.db import SQLiteDB, utc_now_iso


class BotsRepository:
    def __init__(self, db: SQLiteDB):
        self.db = db

    def create_bot(self, owner_client_id: str, bot_type: str, config: dict) -> dict:
        now = utc_now_iso()
        bot_id = str(uuid4())
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO bots (bot_id, owner_client_id, bot_type, config_json, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (bot_id, owner_client_id, bot_type, json.dumps(config), "created", now, now),
            )
        return self.get_bot(bot_id)

    def get_bot(self, bot_id: str) -> dict | None:
        with self.db.connect() as conn:
            row = conn.execute("SELECT * FROM bots WHERE bot_id = ?", (bot_id,)).fetchone()
        if not row:
            return None
        bot = dict(row)
        bot["config"] = json.loads(bot.pop("config_json"))
        return bot

    def update_status(self, bot_id: str, status: str) -> dict | None:
        now = utc_now_iso()
        with self.db.connect() as conn:
            conn.execute("UPDATE bots SET status = ?, updated_at = ? WHERE bot_id = ?", (status, now, bot_id))
        return self.get_bot(bot_id)

    def bot_exists(self, bot_id: str) -> bool:
        with self.db.connect() as conn:
            row = conn.execute("SELECT 1 FROM bots WHERE bot_id = ?", (bot_id,)).fetchone()
        return bool(row)
