import os
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
IS_VERCEL = bool(os.getenv("VERCEL"))
STORAGE_BASE = Path("/tmp") if IS_VERCEL else BASE_DIR
DB_PATH = STORAGE_BASE / "users.db"


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            name          TEXT    NOT NULL,
            email         TEXT    UNIQUE NOT NULL,
            password_hash TEXT    NOT NULL,
            is_verified   INTEGER DEFAULT 0,
            created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()
