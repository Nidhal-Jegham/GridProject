import sqlite3
import os
from datetime import datetime

DB_FILE = os.getenv("CHAT_DB_PATH", "chat_history.db")

class StorageManager:
    """
    Manages chat sessions and messages using SQLite, with auto-recovery and persistent titles.

    Tables:
      - chats(chat_id TEXT PRIMARY KEY, created_at TEXT, title TEXT)
      - messages(msg_id INT PRIMARY KEY AUTOINCREMENT, chat_id TEXT, role TEXT, content TEXT, timestamp TEXT)
    """
    def __init__(self, db_path: str = None):
        self.db_path = db_path or DB_FILE
        self._connect_and_init()

    def _connect_and_init(self):
        try:
            self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self.conn.execute("PRAGMA journal_mode=WAL;")
            self.conn.execute("PRAGMA synchronous=NORMAL;")
            cur = self.conn.cursor()
            cur.execute("PRAGMA integrity_check;")
            if cur.fetchone()[0] != 'ok':
                raise sqlite3.DatabaseError("Integrity check failed")
        except (sqlite3.DatabaseError, sqlite3.OperationalError):
            try: self.conn.close()
            except: pass
            corrupt = self.db_path + ".corrupt"
            if os.path.exists(self.db_path):
                os.replace(self.db_path, corrupt)
            self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self.conn.execute("PRAGMA journal_mode=WAL;")
            self.conn.execute("PRAGMA synchronous=NORMAL;")
        finally:
            self._init_db()

    def _init_db(self):
        c = self.conn.cursor()
        # Create chats table
        c.execute("""
            CREATE TABLE IF NOT EXISTS chats (
                chat_id    TEXT PRIMARY KEY,
                created_at TEXT,
                title      TEXT
            );
        """)
        # Create messages table
        c.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                msg_id     INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id    TEXT,
                role       TEXT,
                content    TEXT,
                timestamp  TEXT,
                FOREIGN KEY(chat_id) REFERENCES chats(chat_id)
            );
        """)
        self.conn.commit()

    def create_chat(self, chat_id: str) -> None:
        now = datetime.utcnow().isoformat()
        c = self.conn.cursor()
        c.execute(
            "INSERT OR IGNORE INTO chats(chat_id, created_at) VALUES(?, ?)",
            (chat_id, now)
        )
        self.conn.commit()

    def set_chat_title(self, chat_id: str, title: str) -> None:
        c = self.conn.cursor()
        c.execute(
            "UPDATE chats SET title = ? WHERE chat_id = ?",
            (title, chat_id)
        )
        self.conn.commit()

    def get_chat_title(self, chat_id: str) -> str | None:
        c = self.conn.cursor()
        c.execute(
            "SELECT title FROM chats WHERE chat_id = ?",
            (chat_id,)
        )
        row = c.fetchone()
        return row[0] if row and row[0] else None

    def append_message(self, chat_id: str, role: str, content: str) -> None:
        """
        role can be 'user', 'assistant', or now also 'assistant_think'
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
        Returns all messages in order, including assistant_think entries.
        """
        c = self.conn.cursor()
        c.execute(
            "SELECT role, content FROM messages WHERE chat_id = ? ORDER BY msg_id ASC",
            (chat_id,)
        )
        return [{"role": r, "content": c} for r, c in c.fetchall()]

    def fetch_thinking(self, chat_id: str) -> list:
        """
        Returns only the reasoning steps (assistant_think messages) for this chat.
        """
        c = self.conn.cursor()
        c.execute(
            "SELECT content FROM messages WHERE chat_id = ? AND role = 'assistant_think' ORDER BY msg_id ASC",
            (chat_id,)
        )
        return [row[0] for row in c.fetchall()]

    def list_chats(self) -> list:
        c = self.conn.cursor()
        c.execute(
            "SELECT chat_id, created_at, title FROM chats ORDER BY created_at DESC"
        )
        return c.fetchall()

    def close(self):
        try:
            self.conn.close()
        except:
            pass
