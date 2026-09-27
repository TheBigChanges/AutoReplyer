"""
Baza: Supabase (yoki istalgan) Postgres orqali. Har bir ulangan biznes-akkaunt
(owner_user_id) uchun business_connection_id, sozlamalar (online/offline,
cooldown, xabar matni) va javob-cooldown tarixi saqlanadi.

Bu Render'ning bepul Web Service'i o'chib-yonganda (yoki qayta deploy
qilinganda) ma'lumot yo'qolmasligi uchun — chunki bepul Render'da mahalliy
fayl (SQLite) saqlanib qolishi kafolatlanmaydi, tashqi Postgres esa doimiy.
"""

import os
import time

import psycopg2
import psycopg2.extras

DATABASE_URL = os.environ["DATABASE_URL"]

DEFAULT_COOLDOWN_HOURS = 3.0
DEFAULT_AUTO_REPLY_TEXT = "Salom! Hozirda oflaynman, imkon qadar tezroq javob beraman \U0001F64F"

_conn = None


def get_conn():
    """Ulanishni qaytaradi, agar o'chib qolgan/uzilgan bo'lsa qayta ulaydi."""
    global _conn
    if _conn is not None and not _conn.closed:
        try:
            with _conn.cursor() as cur:
                cur.execute("SELECT 1")
            return _conn
        except Exception:
            try:
                _conn.close()
            except Exception:
                pass
            _conn = None

    _conn = psycopg2.connect(DATABASE_URL)
    _conn.autocommit = True
    return _conn


def init_db():
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS connections (
                owner_user_id BIGINT PRIMARY KEY,
                business_connection_id TEXT NOT NULL,
                can_reply BOOLEAN NOT NULL DEFAULT TRUE,
                is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
                connected_at DOUBLE PRECISION
            )
            """
        )
        cur.execute(
            "ALTER TABLE connections ADD COLUMN IF NOT EXISTS can_edit_bio BOOLEAN NOT NULL DEFAULT FALSE"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_connections_bcid ON connections (business_connection_id)"
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
                owner_user_id BIGINT PRIMARY KEY,
                offline BOOLEAN NOT NULL DEFAULT FALSE,
                cooldown_hours DOUBLE PRECISION NOT NULL DEFAULT 3.0,
                auto_reply_text TEXT NOT NULL DEFAULT ''
            )
            """
        )
        cur.execute(
            "ALTER TABLE settings ADD COLUMN IF NOT EXISTS bio_countdown_target TEXT"
        )
        cur.execute(
            "ALTER TABLE settings ADD COLUMN IF NOT EXISTS birthday_month INTEGER"
        )
        cur.execute(
            "ALTER TABLE settings ADD COLUMN IF NOT EXISTS birthday_day INTEGER"
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS replied_cache (
                owner_user_id BIGINT,
                chat_id BIGINT,
                last_reply_at DOUBLE PRECISION,
                PRIMARY KEY (owner_user_id, chat_id)
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS referrals (
                referred_user_id BIGINT PRIMARY KEY,
                inviter_user_id BIGINT NOT NULL,
                created_at DOUBLE PRECISION
            )
            """
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_referrals_inviter ON referrals (inviter_user_id)"
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                first_seen DOUBLE PRECISION
            )
            """
        )
        # Bu funksiya qo'shilishidan oldin ham botdan foydalangan odamlarni
        # (connections/settings/referrals'da qolgan) bir martalik "orqaga qarab"
        # to'ldirish — hisoblash noto'g'ri chiqmasligi uchun.
        for query in (
            "INSERT INTO users (user_id, first_seen) SELECT owner_user_id, extract(epoch from now()) FROM settings ON CONFLICT (user_id) DO NOTHING",
            "INSERT INTO users (user_id, first_seen) SELECT owner_user_id, extract(epoch from now()) FROM connections ON CONFLICT (user_id) DO NOTHING",
            "INSERT INTO users (user_id, first_seen) SELECT referred_user_id, extract(epoch from now()) FROM referrals ON CONFLICT (user_id) DO NOTHING",
            "INSERT INTO users (user_id, first_seen) SELECT inviter_user_id, extract(epoch from now()) FROM referrals ON CONFLICT (user_id) DO NOTHING",
        ):
            cur.execute(query)


# --------------------------------------------------------------------------
# Business connections
# --------------------------------------------------------------------------
def upsert_connection(
    owner_user_id: int,
    business_connection_id: str,
    can_reply: bool,
    is_enabled: bool,
    can_edit_bio: bool = False,
):
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO connections (owner_user_id, business_connection_id, can_reply, is_enabled, can_edit_bio, connected_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (owner_user_id) DO UPDATE SET
                business_connection_id = EXCLUDED.business_connection_id,
                can_reply = EXCLUDED.can_reply,
                is_enabled = EXCLUDED.is_enabled,
                can_edit_bio = EXCLUDED.can_edit_bio,
                connected_at = EXCLUDED.connected_at
            """,
            (owner_user_id, business_connection_id, can_reply, is_enabled, can_edit_bio, time.time()),
        )


def get_connection(owner_user_id: int):
    conn = get_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM connections WHERE owner_user_id = %s", (owner_user_id,))
        row = cur.fetchone()
        return dict(row) if row else None


def get_connection_by_business_id(business_connection_id: str):
    conn = get_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            "SELECT * FROM connections WHERE business_connection_id = %s", (business_connection_id,)
        )
        row = cur.fetchone()
        return dict(row) if row else None


# --------------------------------------------------------------------------
# Settings
# --------------------------------------------------------------------------
def ensure_settings(owner_user_id: int):
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO settings (owner_user_id, offline, cooldown_hours, auto_reply_text)
            VALUES (%s, FALSE, %s, %s)
            ON CONFLICT (owner_user_id) DO NOTHING
            """,
            (owner_user_id, DEFAULT_COOLDOWN_HOURS, DEFAULT_AUTO_REPLY_TEXT),
        )


def get_settings(owner_user_id: int) -> dict:
    ensure_settings(owner_user_id)
    conn = get_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM settings WHERE owner_user_id = %s", (owner_user_id,))
        return dict(cur.fetchone())


def update_settings(owner_user_id: int, **kwargs):
    ensure_settings(owner_user_id)
    fields = ", ".join(f"{k} = %s" for k in kwargs)
    values = list(kwargs.values()) + [owner_user_id]
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute(f"UPDATE settings SET {fields} WHERE owner_user_id = %s", values)


# --------------------------------------------------------------------------
# Reply cooldown cache
# --------------------------------------------------------------------------
def already_replied_recently(owner_user_id: int, chat_id: int) -> bool:
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT last_reply_at FROM replied_cache WHERE owner_user_id = %s AND chat_id = %s",
            (owner_user_id, chat_id),
        )
        row = cur.fetchone()
    if row is None:
        return False
    cooldown_hours = get_settings(owner_user_id)["cooldown_hours"]
    return (time.time() - row[0]) < cooldown_hours * 3600


def mark_replied(owner_user_id: int, chat_id: int):
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO replied_cache (owner_user_id, chat_id, last_reply_at)
            VALUES (%s, %s, %s)
            ON CONFLICT (owner_user_id, chat_id) DO UPDATE SET last_reply_at = EXCLUDED.last_reply_at
            """,
            (owner_user_id, chat_id, time.time()),
        )


# --------------------------------------------------------------------------
# Referrallar
# --------------------------------------------------------------------------
def record_referral(referred_user_id: int, inviter_user_id: int) -> bool:
    """Yangi referralni yozadi. Agar bu odam allaqachon ro'yxatdan o'tgan bo'lsa
    yoki o'zini-o'zi taklif qilmoqchi bo'lsa — False qaytaradi (hisoblanmaydi)."""
    if referred_user_id == inviter_user_id:
        return False
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO referrals (referred_user_id, inviter_user_id, created_at)
            VALUES (%s, %s, %s)
            ON CONFLICT (referred_user_id) DO NOTHING
            """,
            (referred_user_id, inviter_user_id, time.time()),
        )
        return cur.rowcount > 0


def get_referral_count(inviter_user_id: int) -> int:
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM referrals WHERE inviter_user_id = %s", (inviter_user_id,)
        )
        return cur.fetchone()[0]


def get_all_referral_counts():
    """[(inviter_user_id, count), ...] — ko'p taklif qilganlar oldinda."""
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT inviter_user_id, COUNT(*) AS cnt
            FROM referrals
            GROUP BY inviter_user_id
            ORDER BY cnt DESC
            """
        )
        return cur.fetchall()


# --------------------------------------------------------------------------
# Foydalanuvchilar (admin /stats va /reklama uchun)
# --------------------------------------------------------------------------
def record_user(user_id: int):
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO users (user_id, first_seen)
            VALUES (%s, %s)
            ON CONFLICT (user_id) DO NOTHING
            """,
            (user_id, time.time()),
        )


def get_user_count() -> int:
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM users")
        return cur.fetchone()[0]


def get_all_user_ids():
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("SELECT user_id FROM users ORDER BY user_id")
        return [row[0] for row in cur.fetchall()]


# --------------------------------------------------------------------------
# BIO hisoblagich
# --------------------------------------------------------------------------
def get_all_bio_targets():
    """BIO'sini avtomatik yangilash kerak bo'lgan barcha ulanishlar."""
    conn = get_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT c.owner_user_id, c.business_connection_id,
                   s.bio_countdown_target, s.birthday_month, s.birthday_day
            FROM connections c
            JOIN settings s ON s.owner_user_id = c.owner_user_id
            WHERE c.is_enabled = TRUE AND c.can_edit_bio = TRUE
              AND s.bio_countdown_target IS NOT NULL
            """
        )
        return [dict(r) for r in cur.fetchall()]
