import sqlite3
import os
from datetime import datetime

DB_FILE = os.getenv("CHAT_DB_PATH", "chat_history.db")

class StorageManager:
    """
    Manages chat sessions and messages using SQLite.
    Tables:
      - chats(chat_id TEXT PRIMARY KEY, created_at TEXT)
      - messages(msg_id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id TEXT, role TEXT, content TEXT, timestamp TEXT)
    """
    def __init__(self, db_path: str = None):
        self.db_path = db_path or DB_FILE
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._init_db()

    def _init_db(self):
        c = self.conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS chats (
                chat_id TEXT PRIMARY KEY,
                created_at TEXT
            );
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                msg_id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id TEXT,
                role TEXT,
                content TEXT,
                timestamp TEXT,
                FOREIGN KEY(chat_id) REFERENCES chats(chat_id)
            );
        """)
        self.conn.commit()

    def create_chat(self, chat_id: str) -> None:
        """
        Create a new chat session with the given ID.
        """
        now = datetime.utcnow().isoformat()
        c = self.conn.cursor()
        c.execute(
            "INSERT OR IGNORE INTO chats(chat_id, created_at) VALUES(?, ?)",
            (chat_id, now)
        )
        self.conn.commit()

    def append_message(self, chat_id: str, role: str, content: str) -> None:
        """
        Append a message to a chat session.
        """
        now = datetime.utcnow().isoformat()
        c = self.conn.cursor()
        c.execute(
            "INSERT INTO messages(chat_id, role, content, timestamp) VALUES(?, ?, ?, ?)",
            (chat_id, role, content, now)
        )
        self.conn.commit()

    def fetch_history(self, chat_id: str) -> list:
        """
        Fetch all messages for a chat in chronological order.
        """
        c = self.conn.cursor()
        c.execute(
            "SELECT role, content FROM messages WHERE chat_id = ? ORDER BY msg_id ASC",
            (chat_id,)
        )
        rows = c.fetchall()
        return [{"role": r[0], "content": r[1]} for r in rows]

    def list_chats(self) -> list:
        """
        List all chat IDs and creation times.
        """
        c = self.conn.cursor()
        c.execute(
            "SELECT chat_id, created_at FROM chats ORDER BY created_at DESC"
        )
        return c.fetchall()

    def close(self):
        self.conn.close()

# Example usage:
# sm = StorageManager()
# sm.create_chat("session1")
# sm.append_message("session1", "user", "Hello")
# history = sm.fetch_history("session1")
# print(history)
