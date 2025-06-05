import sqlite3
import os
import hashlib
from datetime import datetime

DB_FILE = os.getenv("CHAT_DB_PATH", "chat_history.db")

class AuthManager:
    """Simple local authentication using SQLite."""
    def __init__(self, db_path: str = None):
        self.db_path = db_path or DB_FILE
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._init_db()

    def _init_db(self):
        c = self.conn.cursor()
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                password TEXT,
                created_at TEXT
            );
            """
        )
        self.conn.commit()

    def create_user(self, username: str, password: str) -> bool:
        """Create a new user. Returns True if created."""
        hashed = hashlib.sha256(password.encode()).hexdigest()
        try:
            self.conn.execute(
                "INSERT INTO users(username, password, created_at) VALUES(?,?,?)",
                (username, hashed, datetime.utcnow().isoformat()),
            )
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def validate_user(self, username: str, password: str) -> bool:
        """Validate a username/password combination."""
        hashed = hashlib.sha256(password.encode()).hexdigest()
        c = self.conn.cursor()
        c.execute(
            "SELECT password FROM users WHERE username=?",
            (username,),
        )
        row = c.fetchone()
        return row is not None and row[0] == hashed

    def change_password(self, username: str, new_password: str) -> None:
        hashed = hashlib.sha256(new_password.encode()).hexdigest()
        self.conn.execute(
            "UPDATE users SET password=? WHERE username=?",
            (hashed, username),
        )
        self.conn.commit()

    def user_exists(self, username: str) -> bool:
        c = self.conn.cursor()
        c.execute(
            "SELECT 1 FROM users WHERE username=?",
            (username,),
        )
        return c.fetchone() is not None

    def login_with_google(self, email: str) -> bool:
        """Create the user if needed and mark them as logged in."""
        if not self.user_exists(email):
            import secrets
            random_pw = secrets.token_hex(16)
            self.create_user(email, random_pw)
        return True
