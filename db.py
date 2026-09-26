"""
Baza: har bir ulangan biznes-akkaunt (owner_user_id) uchun business_connection_id,
sozlamalar (online/offline, cooldown, xabar matni) va javob-cooldown tarixi.

Endi hech qanday login sessiyasi yoki shifrlash kerak emas — ulanish butunlay
Telegramning o'z "Chat Automation" (Business Connection) mexanizmi orqali bo'ladi.
"""

import os
import sqlite3
import time
from pathlib import Path

DB_PATH = Path(os.environ.get("DB_PATH", str(Path(__file__).parent / "data.db")))

DEFAULT_COOLDOWN_HOURS = 3.0
DEFAULT_AUTO_REPLY_TEXT = "Salom! Hozirda oflaynman, imkon qadar tezroq javob beraman \U0001F64F"


def get_conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS connections (
                owner_user_id INTEGER PRIMARY KEY,
                business_connection_id TEXT NOT NULL,
                can_reply INTEGER NOT NULL DEFAULT 1,
                is_enabled INTEGER NOT NULL DEFAULT 1,
                connected_at REAL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_connections_bcid ON connections (business_connection_id)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
                owner_user_id INTEGER PRIMARY KEY,
                offline INTEGER NOT NULL DEFAULT 0,
                cooldown_hours REAL NOT NULL DEFAULT 3.0,
                auto_reply_text TEXT NOT NULL DEFAULT ''
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS replied_cache (
                owner_user_id INTEGER,
                chat_id INTEGER,
                last_reply_at REAL,
                PRIMARY KEY (owner_user_id, chat_id)
            )
            """
        )


# --------------------------------------------------------------------------
# Business connections
# --------------------------------------------------------------------------
def upsert_connection(owner_user_id: int, business_connection_id: str, can_reply: bool, is_enabled: bool):
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO connections (owner_user_id, business_connection_id, can_reply, is_enabled, connected_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(owner_user_id) DO UPDATE SET
                business_connection_id = excluded.business_connection_id,
                can_reply = excluded.can_reply,
                is_enabled = excluded.is_enabled,
                connected_at = excluded.connected_at
            """,
            (owner_user_id, business_connection_id, int(can_reply), int(is_enabled), time.time()),
        )


def get_connection(owner_user_id: int):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM connections WHERE owner_user_id = ?", (owner_user_id,)
        ).fetchone()
        if not row:
            return None
        d = dict(row)
        d["can_reply"] = bool(d["can_reply"])
        d["is_enabled"] = bool(d["is_enabled"])
        return d


def get_connection_by_business_id(business_connection_id: str):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM connections WHERE business_connection_id = ?", (business_connection_id,)
        ).fetchone()
        if not row:
            return None
        d = dict(row)
        d["can_reply"] = bool(d["can_reply"])
        d["is_enabled"] = bool(d["is_enabled"])
        return d


# --------------------------------------------------------------------------
# Settings
# --------------------------------------------------------------------------
def ensure_settings(owner_user_id: int):
    with get_conn() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO settings (owner_user_id, offline, cooldown_hours, auto_reply_text)
            VALUES (?, 0, ?, ?)
            """,
            (owner_user_id, DEFAULT_COOLDOWN_HOURS, DEFAULT_AUTO_REPLY_TEXT),
        )


def get_settings(owner_user_id: int) -> dict:
    ensure_settings(owner_user_id)
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM settings WHERE owner_user_id = ?", (owner_user_id,)
        ).fetchone()
        d = dict(row)
        d["offline"] = bool(d["offline"])
        return d


def update_settings(owner_user_id: int, **kwargs):
    ensure_settings(owner_user_id)
    if "offline" in kwargs:
        kwargs["offline"] = int(bool(kwargs["offline"]))
    fields = ", ".join(f"{k} = ?" for k in kwargs)
    values = list(kwargs.values()) + [owner_user_id]
    with get_conn() as conn:
        conn.execute(f"UPDATE settings SET {fields} WHERE owner_user_id = ?", values)


# --------------------------------------------------------------------------
# Reply cooldown cache
# --------------------------------------------------------------------------
def already_replied_recently(owner_user_id: int, chat_id: int) -> bool:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT last_reply_at FROM replied_cache WHERE owner_user_id = ? AND chat_id = ?",
            (owner_user_id, chat_id),
        ).fetchone()
    if row is None:
        return False
    cooldown_hours = get_settings(owner_user_id)["cooldown_hours"]
    return (time.time() - row["last_reply_at"]) < cooldown_hours * 3600


def mark_replied(owner_user_id: int, chat_id: int):
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO replied_cache (owner_user_id, chat_id, last_reply_at)
            VALUES (?, ?, ?)
            ON CONFLICT(owner_user_id, chat_id) DO UPDATE SET last_reply_at = excluded.last_reply_at
            """,
            (owner_user_id, chat_id, time.time()),
        )
