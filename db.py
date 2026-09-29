"""
Baza: Supabase (yoki istalgan) Postgres orqali. Har bir ulangan biznes-akkaunt
(owner_user_id) uchun business_connection_id, sozlamalar (online/offline,
cooldown, xabar matni) va javob-cooldown tarixi saqlanadi.

Bu Render'ning bepul Web Service'i o'chib-yonganda (yoki qayta deploy
qilinganda) ma'lumot yo'qolmasligi uchun — chunki bepul Render'da mahalliy
fayl (SQLite) saqlanib qolishi kafolatlanmaydi, tashqi Postgres esa doimiy.
"""

import logging
import os
import time

import psycopg2
import psycopg2.extras
import psycopg2.pool

logger = logging.getLogger("autoreplyer.db")

DEFAULT_COOLDOWN_HOURS = 3.0
DEFAULT_AUTO_REPLY_TEXT = "Salom! Hozirda oflaynman, imkon qadar tezroq javob beraman \U0001F64F"

# update_settings() orqali o'zgartirish mumkin bo'lgan ustunlar ro'yxati.
# Bu whitelist — kwargs orqali ixtiyoriy SQL ustun nomi yuborib bo'lmasligini
# kafolatlaydi (funksiya kelajakda tashqi/umumiyroq ishlatilib qolsa ham xavfsiz).
ALLOWED_SETTINGS_FIELDS = {
    "offline",
    "cooldown_hours",
    "auto_reply_text",
    "bio_countdown_target",
    "birthday_month",
    "birthday_day",
}

_pool: "psycopg2.pool.SimpleConnectionPool | None" = None


def _get_pool() -> "psycopg2.pool.SimpleConnectionPool":
    """Connection pool'ni "lazy" (birinchi so'rovda) yaratadi — shu bilan
    DATABASE_URL faqat chindan bazaga murojaat qilinganda o'qiladi. Bu
    modulni (masalan testlarda) DATABASE_URL o'rnatilmagan holda ham xavfsiz
    import qilish imkonini beradi."""
    global _pool
    if _pool is None:
        database_url = os.environ["DATABASE_URL"]
        try:
            _pool = psycopg2.pool.SimpleConnectionPool(1, 10, dsn=database_url)
        except Exception:
            logger.exception("Bazaga ulanib bo'lmadi (DATABASE_URL noto'g'ri yoki server javob bermayapti)")
            raise
        logger.info("Baza connection pool yaratildi")
    return _pool


class _PooledConnection:
    """Pool'dan bitta ulanishni olib, `with` bloki tugagach avtomatik
    qaytaradigan yordamchi. Ulanish uzilgan/buzilgan bo'lsa pool'ga
    qaytarmasdan yopib tashlaydi, shunda keyingi so'rov yangi ulanish oladi."""

    def __enter__(self):
        self._pool = _get_pool()
        self._conn = self._pool.getconn()
        self._conn.autocommit = True
        return self._conn

    def __exit__(self, exc_type, exc, tb):
        if exc_type is not None:
            try:
                self._conn.close()
            except Exception:
                logger.warning("Buzilgan ulanishni yopishda xato", exc_info=True)
            self._pool.putconn(self._conn, close=True)
        else:
            self._pool.putconn(self._conn)
        return False


def get_conn():
    """Eski kod bilan moslik uchun: `with get_conn() as conn:` shaklida
    ishlatiladi — pool'dan bitta ulanish beradi va bloki tugagach qaytaradi."""
    return _PooledConnection()


def init_db():
    with get_conn() as conn, conn.cursor() as cur:
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
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS broadcast_jobs (
                id SERIAL PRIMARY KEY,
                source_chat_id BIGINT NOT NULL,
                source_message_id BIGINT NOT NULL,
                status TEXT NOT NULL DEFAULT 'running',
                last_user_id BIGINT NOT NULL DEFAULT 0,
                total_count INTEGER NOT NULL DEFAULT 0,
                sent_count INTEGER NOT NULL DEFAULT 0,
                failed_count INTEGER NOT NULL DEFAULT 0,
                created_at DOUBLE PRECISION,
                updated_at DOUBLE PRECISION
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS broadcast_failures (
                job_id INTEGER NOT NULL,
                user_id BIGINT NOT NULL,
                error_text TEXT,
                failed_at DOUBLE PRECISION,
                PRIMARY KEY (job_id, user_id)
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
    with get_conn() as conn, conn.cursor() as cur:
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
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM connections WHERE owner_user_id = %s", (owner_user_id,))
        row = cur.fetchone()
        return dict(row) if row else None


def get_connection_by_business_id(business_connection_id: str):
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            "SELECT * FROM connections WHERE business_connection_id = %s", (business_connection_id,)
        )
        row = cur.fetchone()
        return dict(row) if row else None


# --------------------------------------------------------------------------
# Settings
# --------------------------------------------------------------------------
def ensure_settings(owner_user_id: int):
    with get_conn() as conn, conn.cursor() as cur:
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
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM settings WHERE owner_user_id = %s", (owner_user_id,))
        return dict(cur.fetchone())


def update_settings(owner_user_id: int, **kwargs):
    invalid = set(kwargs) - ALLOWED_SETTINGS_FIELDS
    if invalid:
        raise ValueError(f"Ruxsat etilmagan settings ustuni: {invalid}")
    ensure_settings(owner_user_id)
    fields = ", ".join(f"{k} = %s" for k in kwargs)
    values = list(kwargs.values()) + [owner_user_id]
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(f"UPDATE settings SET {fields} WHERE owner_user_id = %s", values)


# --------------------------------------------------------------------------
# Reply cooldown cache
# --------------------------------------------------------------------------
def already_replied_recently(owner_user_id: int, chat_id: int) -> bool:
    with get_conn() as conn, conn.cursor() as cur:
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
    with get_conn() as conn, conn.cursor() as cur:
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
    with get_conn() as conn, conn.cursor() as cur:
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
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM referrals WHERE inviter_user_id = %s", (inviter_user_id,)
        )
        return cur.fetchone()[0]


def get_all_referral_counts():
    """[(inviter_user_id, count), ...] — ko'p taklif qilganlar oldinda."""
    with get_conn() as conn, conn.cursor() as cur:
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
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO users (user_id, first_seen)
            VALUES (%s, %s)
            ON CONFLICT (user_id) DO NOTHING
            """,
            (user_id, time.time()),
        )


def get_user_count() -> int:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM users")
        return cur.fetchone()[0]


def get_user_ids_after(last_user_id: int, limit: int = 200):
    """Keyset pagination: `last_user_id`dan katta bo'lgan keyingi `limit` ta
    foydalanuvchi ID'sini qaytaradi. Bu butun jadvalni bir vaqtda xotiraga
    yuklamaslik uchun — 100,000+ foydalanuvchida ham xotira muammosi
    tug'dirmaydi, chunki har safar faqat kichik bo'lak o'qiladi."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT user_id FROM users WHERE user_id > %s ORDER BY user_id LIMIT %s",
            (last_user_id, limit),
        )
        return [row[0] for row in cur.fetchall()]


def get_all_user_ids():
    """Eslatma: faqat /stats kabi kichik hajmli ehtiyojlar uchun — katta
    ro'yxatlarni (masalan reklama yuborishda) get_user_ids_after() bilan
    bo'lib-bo'lib o'qing."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT user_id FROM users ORDER BY user_id")
        return [row[0] for row in cur.fetchall()]


# --------------------------------------------------------------------------
# Reklama (broadcast) job — fonda ishlaydi va qayta ishga tushirilsa davom
# ettirila oladi (resumable), muvaffaqiyatsiz bo'lganlar alohida saqlanadi.
# --------------------------------------------------------------------------
def create_broadcast_job(source_chat_id: int, source_message_id: int, total_count: int) -> int:
    now = time.time()
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO broadcast_jobs
                (source_chat_id, source_message_id, status, last_user_id, total_count, created_at, updated_at)
            VALUES (%s, %s, 'running', 0, %s, %s, %s)
            RETURNING id
            """,
            (source_chat_id, source_message_id, total_count, now, now),
        )
        return cur.fetchone()[0]


def update_broadcast_progress(job_id: int, last_user_id: int, sent_delta: int, failed_delta: int):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            UPDATE broadcast_jobs
            SET last_user_id = %s,
                sent_count = sent_count + %s,
                failed_count = failed_count + %s,
                updated_at = %s
            WHERE id = %s
            """,
            (last_user_id, sent_delta, failed_delta, time.time(), job_id),
        )


def set_broadcast_status(job_id: int, status: str):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE broadcast_jobs SET status = %s, updated_at = %s WHERE id = %s",
            (status, time.time(), job_id),
        )


def record_broadcast_failure(job_id: int, user_id: int, error_text: str):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO broadcast_failures (job_id, user_id, error_text, failed_at)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (job_id, user_id) DO NOTHING
            """,
            (job_id, user_id, error_text, time.time()),
        )


def get_latest_broadcast_job():
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM broadcast_jobs ORDER BY id DESC LIMIT 1")
        row = cur.fetchone()
        return dict(row) if row else None


def get_running_broadcast_jobs():
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM broadcast_jobs WHERE status = 'running'")
        return [dict(r) for r in cur.fetchall()]


def get_broadcast_failed_user_ids(job_id: int):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT user_id FROM broadcast_failures WHERE job_id = %s", (job_id,))
        return [row[0] for row in cur.fetchall()]


# --------------------------------------------------------------------------
# BIO hisoblagich
# --------------------------------------------------------------------------
def get_all_bio_targets():
    """BIO'sini avtomatik yangilash kerak bo'lgan barcha ulanishlar."""
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
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
