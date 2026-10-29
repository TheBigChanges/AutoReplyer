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
import threading
import time

import psycopg2
import psycopg2.errors
import psycopg2.extras
import psycopg2.pool

import automation
from logic import DEFAULT_SLEEP_MESSAGE


class BroadcastAlreadyRunningError(Exception):
    """Bir vaqtning o'zida faqat bitta reklama job 'running' holatida bo'lishi
    mumkin — buni bazaning o'zi (partial unique index) kafolatlaydi, shuning
    uchun bu xato chiqsa, bu haqiqiy race condition emas, balki shunchaki
    boshqa reklama allaqachon ishlab turgani degani."""

logger = logging.getLogger("autoreplyer.db")

_UNSET = object()  # record_user(): "bu maydon berilmagan" (None — "bu maydon bo'sh" dan farq qiladi)

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
    "sleep_mode_enabled",
    "sleep_start_minutes",
    "sleep_end_minutes",
    "sleep_reply_text",
    "bio_updated_on",
    "ai_enabled",
    "ai_info",
    "ai_role",
    "name_clock_enabled",
    "name_clock_tz",
    "name_clock_first",
    "name_clock_last",
    "name_clock_applied",
    "clock_bio_ad",
    "clock_bio_notified",
    "faq_enabled",
    "kb_enabled",
    "scheduler_enabled",
    "name_clock_style",
}

POOL_MAX_CONNECTIONS = 10
_pool_init_lock = threading.Lock()
_pool: "psycopg2.pool.ThreadedConnectionPool | None" = None


def _get_pool() -> "psycopg2.pool.ThreadedConnectionPool":
    """Connection pool'ni "lazy" (birinchi so'rovda) yaratadi — shu bilan
    DATABASE_URL faqat chindan bazaga murojaat qilinganda o'qiladi. Bu
    modulni (masalan testlarda) DATABASE_URL o'rnatilmagan holda ham xavfsiz
    import qilish imkonini beradi."""
    global _pool
    if _pool is None:
        with _pool_init_lock:  # bir vaqtda ikki oqim ikkita pool yaratmasligi uchun
            if _pool is None:
                database_url = os.environ["DATABASE_URL"]
                try:
                    # ThreadedConnectionPool — ko'p oqimli (asyncio.to_thread) ishlatish uchun xavfsiz
                    _pool = psycopg2.pool.ThreadedConnectionPool(1, POOL_MAX_CONNECTIONS, dsn=database_url)
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
        # Faqat chindan ham ULANISH buzilgan bo'lsa (tarmoq uzilishi va h.k.)
        # ulanishni tashlab yuboramiz. Oddiy SQL xatosi (masalan constraint
        # buzilishi — UniqueViolation) autocommit rejimida ulanishni
        # "ifloslantirmaydi", shuning uchun uni pool'ga qaytarib, bekorga
        # yangi ulanish ochishdan saqlanamiz.
        is_connection_broken = exc_type is not None and issubclass(
            exc_type, (psycopg2.OperationalError, psycopg2.InterfaceError)
        )
        if is_connection_broken:
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
            "ALTER TABLE connections ADD COLUMN IF NOT EXISTS can_edit_name BOOLEAN NOT NULL DEFAULT FALSE"
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
        # AI-Yordamchi
        cur.execute("ALTER TABLE settings ADD COLUMN IF NOT EXISTS ai_enabled BOOLEAN NOT NULL DEFAULT FALSE")
        cur.execute("ALTER TABLE settings ADD COLUMN IF NOT EXISTS ai_info TEXT")
        cur.execute("ALTER TABLE settings ADD COLUMN IF NOT EXISTS ai_role TEXT")
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_usage (
                owner_user_id BIGINT NOT NULL,
                day TEXT NOT NULL,
                count INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (owner_user_id, day)
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_chat_history (
                id BIGSERIAL PRIMARY KEY,
                owner_user_id BIGINT NOT NULL,
                chat_id BIGINT NOT NULL,
                role TEXT NOT NULL,
                text TEXT NOT NULL,
                created_at DOUBLE PRECISION NOT NULL
            )
            """
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_ai_history_chat ON ai_chat_history (owner_user_id, chat_id, id)"
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_chat_pause (
                owner_user_id BIGINT NOT NULL,
                chat_id BIGINT NOT NULL,
                paused_until DOUBLE PRECISION NOT NULL,
                PRIMARY KEY (owner_user_id, chat_id)
            )
            """
        )
        # Ism soati ("Ism | 12:30")
        cur.execute("ALTER TABLE settings ADD COLUMN IF NOT EXISTS name_clock_enabled BOOLEAN NOT NULL DEFAULT FALSE")
        cur.execute("ALTER TABLE settings ADD COLUMN IF NOT EXISTS name_clock_tz TEXT")
        cur.execute("ALTER TABLE settings ADD COLUMN IF NOT EXISTS name_clock_first TEXT")
        cur.execute("ALTER TABLE settings ADD COLUMN IF NOT EXISTS name_clock_last TEXT")
        cur.execute("ALTER TABLE settings ADD COLUMN IF NOT EXISTS name_clock_applied TEXT")
        cur.execute("ALTER TABLE settings ADD COLUMN IF NOT EXISTS clock_bio_ad BOOLEAN NOT NULL DEFAULT FALSE")
        # Bepul tarifda ism soati BIO ruxsatisiz ishlamaydi: egasiga "to'xtatildi" xabari yuborilganmi (qayta-qayta yubormaslik uchun)
        cur.execute("ALTER TABLE settings ADD COLUMN IF NOT EXISTS clock_bio_notified BOOLEAN NOT NULL DEFAULT FALSE")
        cur.execute("ALTER TABLE settings ADD COLUMN IF NOT EXISTS faq_enabled BOOLEAN NOT NULL DEFAULT TRUE")
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS faq_entries (
                id BIGSERIAL PRIMARY KEY,
                owner_user_id BIGINT NOT NULL,
                question TEXT NOT NULL,
                keywords TEXT[] NOT NULL DEFAULT '{}',
                answer TEXT NOT NULL,
                is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_faq_owner ON faq_entries(owner_user_id)")
        # Automation Engine: har egasining qoidalari alohida (hamma so'rov owner_user_id bilan cheklangan).
        # Yangi qoida DOIM o'chirilgan holatda yaratiladi (is_enabled = FALSE).
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS automation_rules (
                id BIGSERIAL PRIMARY KEY,
                owner_user_id BIGINT NOT NULL,
                name TEXT NOT NULL,
                conditions JSONB NOT NULL,
                action JSONB NOT NULL,
                priority INTEGER NOT NULL DEFAULT 100,
                is_enabled BOOLEAN NOT NULL DEFAULT FALSE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_automation_owner ON automation_rules(owner_user_id, is_enabled, priority, id)"
        )
        # v1.2: qoida bo'yicha statistika (faqat son va vaqt — mijoz xabarlari/chat ID saqlanmaydi)
        cur.execute("ALTER TABLE automation_rules ADD COLUMN IF NOT EXISTS sent_count BIGINT NOT NULL DEFAULT 0")
        cur.execute("ALTER TABLE automation_rules ADD COLUMN IF NOT EXISTS last_sent_at TIMESTAMPTZ")
        # O'chirilgan qoidalarning javoblari yo'qolmasligi uchun egasi bo'yicha tarixiy jami + hisob boshlangan sana
        cur.execute(
            "CREATE TABLE IF NOT EXISTS automation_deleted_totals (owner_user_id BIGINT PRIMARY KEY, sent_count BIGINT NOT NULL DEFAULT 0)"
        )
        cur.execute("CREATE TABLE IF NOT EXISTS automation_meta (key TEXT PRIMARY KEY, value TIMESTAMPTZ NOT NULL DEFAULT NOW())")
        cur.execute("INSERT INTO automation_meta (key) VALUES ('counters_since') ON CONFLICT (key) DO NOTHING")
        # AI Knowledge Base: har egasining ma'lumotlari alohida (hamma so'rov owner_user_id bilan cheklangan)
        cur.execute("ALTER TABLE settings ADD COLUMN IF NOT EXISTS kb_enabled BOOLEAN NOT NULL DEFAULT TRUE")
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS knowledge_entries (
                id BIGSERIAL PRIMARY KEY,
                owner_user_id BIGINT NOT NULL,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                keywords TEXT[] NOT NULL DEFAULT '{}',
                is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_kb_owner ON knowledge_entries(owner_user_id)")
        # Analytics: faqat soatlik hisoblagichlar (xabar matni, chat ID, mijoz ma'lumoti SAQLANMAYDI)
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS analytics_hourly (
                owner_user_id BIGINT NOT NULL,
                bucket BIGINT NOT NULL,
                kind TEXT NOT NULL,
                count INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (owner_user_id, bucket, kind)
            )
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_analytics_bucket ON analytics_hourly(bucket)")
        # Smart Auto-Reply Scheduler: haftalik jadvallar (days — bitmask, 0-bit = Dushanba; text NULL = standart matn)
        cur.execute("ALTER TABLE settings ADD COLUMN IF NOT EXISTS scheduler_enabled BOOLEAN NOT NULL DEFAULT TRUE")
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS schedule_rules (
                id BIGSERIAL PRIMARY KEY,
                owner_user_id BIGINT NOT NULL,
                days SMALLINT NOT NULL,
                start_min INTEGER NOT NULL,
                end_min INTEGER NOT NULL,
                text TEXT,
                is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_schedule_owner ON schedule_rules(owner_user_id)")
        cur.execute("ALTER TABLE settings ADD COLUMN IF NOT EXISTS name_clock_style TEXT")
        cur.execute(
            "ALTER TABLE settings ADD COLUMN IF NOT EXISTS birthday_month INTEGER"
        )
        cur.execute(
            "ALTER TABLE settings ADD COLUMN IF NOT EXISTS birthday_day INTEGER"
        )
        cur.execute(
            "ALTER TABLE settings ADD COLUMN IF NOT EXISTS sleep_mode_enabled BOOLEAN NOT NULL DEFAULT FALSE"
        )
        cur.execute(
            "ALTER TABLE settings ADD COLUMN IF NOT EXISTS sleep_start_minutes INTEGER NOT NULL DEFAULT 1380"
        )
        cur.execute(
            "ALTER TABLE settings ADD COLUMN IF NOT EXISTS sleep_end_minutes INTEGER NOT NULL DEFAULT 420"
        )
        cur.execute(
            "ALTER TABLE settings ADD COLUMN IF NOT EXISTS sleep_reply_text TEXT NOT NULL DEFAULT ''"
        )
        # BIO oxirgi marta qaysi sanada (Toshkent, ISO "YYYY-MM-DD") muvaffaqiyatli
        # yangilangani. Server 00:05 da o'chiq bo'lib qolsa, startup'da faqat
        # shu sana bugundan eski bo'lganlarni "yetkazib" yangilash uchun.
        cur.execute(
            "ALTER TABLE settings ADD COLUMN IF NOT EXISTS bio_updated_on TEXT"
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
        # Admin /block uchun: @username bo'yicha topish va ro'yxatda ko'rsatish
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS username TEXT")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS full_name TEXT")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_users_username_lower ON users (lower(username))")
        # Telegramdan ism/username olishga oxirgi urinish vaqti (eski foydalanuvchilarni
        # to'ldirish uchun; muvaffaqiyatsiz bo'lsa har restartda qayta-qayta urinmaslik uchun)
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS info_checked_at DOUBLE PRECISION")
        # Foydalanuvchi tanlagan til ('uz' | 'en' | 'ru'); NULL — hali tanlamagan (eski foydalanuvchilar)
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS lang TEXT")
        # Tarif: NULL = bepul (hamma shu tarifdan boshlaydi)
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS plan TEXT")
        # Tarif tugash vaqti (epoch); NULL — muddatsiz
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS plan_expires_at DOUBLE PRECISION")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_users_first_seen ON users (first_seen DESC)")
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS blocked_users (
                user_id BIGINT PRIMARY KEY,
                reason TEXT NOT NULL DEFAULT '',
                blocked_by BIGINT,
                blocked_at DOUBLE PRECISION
            )
            """
        )
        # "Fikr/taklif" — foydalanuvchilardan adminga kelgan xabarlar (spamga qarshi limit uchun)
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS feedback_messages (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                message TEXT NOT NULL,
                created_at DOUBLE PRECISION
            )
            """
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_feedback_user ON feedback_messages (user_id, created_at)"
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS block_appeals (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                message TEXT NOT NULL,
                created_at DOUBLE PRECISION
            )
            """
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_block_appeals_user ON block_appeals (user_id, created_at)"
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
            # NULL bo'lsa — bu oddiy, hamma foydalanuvchiga ketadigan job.
            # Son bo'lsa — bu o'sha ID'li job'ning FAQAT muvaffaqiyatsiz
            # (broadcast_failures) foydalanuvchilariga qaratilgan retry job.
            # Bu qiymat bazada saqlangani uchun, server restart bo'lib
            # resume_pending_broadcasts() qayta ishga tushirganda ham,
            # retry job hamon faqat o'sha cheklangan ro'yxatdan davom
            # etadi — RAM'dagi vaqtinchalik ro'yxatga bog'liq emas.
            "ALTER TABLE broadcast_jobs ADD COLUMN IF NOT EXISTS retry_of_job_id INTEGER"
        )
        # Bir martalik tozalash: agar shu tuzatishdan OLDIN (bug tufayli) bir
        # nechta 'running' job qolib ketgan bo'lsa, pastdagi UNIQUE INDEX
        # yaratishning o'zi xato berib qoladi — shuning uchun avval faqat ENG
        # YANGI running job'ni qoldirib, qolganlarini 'failed'ga o'tkazamiz
        # (kerak bo'lsa adminga /reklama_retry orqali alohida qayta urinish imkoni qoladi).
        cur.execute(
            """
            UPDATE broadcast_jobs
            SET status = 'failed', updated_at = %s
            WHERE status = 'running' AND id NOT IN (
                SELECT id FROM broadcast_jobs WHERE status = 'running' ORDER BY id DESC LIMIT 1
            )
            """,
            (time.time(),),
        )
        cur.execute(
            # MUHIM: bu — ikkita /reklama bir vaqtda ketib qolishining oldini
            # oluvchi haqiqiy himoya. Oddiy "avval tekshir, keyin yoz" (TOCTOU)
            # usuli ikkita tezkor so'rov bir-biriga yugurib qolsa yetarli emas;
            # partial unique index esa bazaning o'zida "status='running' bo'lgan
            # qator ko'pi bilan bitta bo'lsin" qoidasini majburlaydi — ikkinchi
            # urinish INSERT/UPDATE darajasida rad etiladi.
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_single_running_broadcast "
            "ON broadcast_jobs (status) WHERE status = 'running'"
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

        # Smart Onboarding: bu ustun BIRINCHI marta qo'shilganda barcha mavjud
        # foydalanuvchilar 'legacy' bo'ladi (ularga onboarding ko'rsatilmaydi).
        # Shundan keyin default 'welcome' ga almashtiriladi — yangi qatorlar shundan boshlaydi.
        # (Tartib muhim: backfill'dan KEYIN, shunda orqaga qarab qo'shilganlar ham legacy.)
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS onboarding_step TEXT DEFAULT 'legacy'")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS onboarding_started_at DOUBLE PRECISION")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS onboarding_completed_at DOUBLE PRECISION")
        cur.execute("ALTER TABLE users ALTER COLUMN onboarding_step SET DEFAULT 'welcome'")


# --------------------------------------------------------------------------
# Business connections
# --------------------------------------------------------------------------
def upsert_connection(
    owner_user_id: int,
    business_connection_id: str,
    can_reply: bool,
    is_enabled: bool,
    can_edit_bio: bool = False,
    can_edit_name: bool = False,
):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO connections
                (owner_user_id, business_connection_id, can_reply, is_enabled, can_edit_bio, can_edit_name, connected_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (owner_user_id) DO UPDATE SET
                business_connection_id = EXCLUDED.business_connection_id,
                can_reply = EXCLUDED.can_reply,
                is_enabled = EXCLUDED.is_enabled,
                can_edit_bio = EXCLUDED.can_edit_bio,
                can_edit_name = EXCLUDED.can_edit_name,
                connected_at = EXCLUDED.connected_at
            """,
            (owner_user_id, business_connection_id, can_reply, is_enabled, can_edit_bio, can_edit_name, time.time()),
        )


def get_connection(owner_user_id: int):
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM connections WHERE owner_user_id = %s", (owner_user_id,))
        row = cur.fetchone()
        return dict(row) if row else None


def get_connection_by_business_id(business_connection_id: str):
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        # is_blocked: ulanish egasi admin tomonidan bloklanganmi (bloklangan odamga
        # avtojavob berilmaydi). Shu bitta so'rovga qo'shilgan — qo'shimcha DB chaqiruvi yo'q.
        cur.execute(
            """
            SELECT c.*,
                   EXISTS (SELECT 1 FROM blocked_users b WHERE b.user_id = c.owner_user_id) AS is_blocked
            FROM connections c
            WHERE c.business_connection_id = %s
            """,
            (business_connection_id,),
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
            INSERT INTO settings (owner_user_id, offline, cooldown_hours, auto_reply_text, sleep_reply_text)
            VALUES (%s, FALSE, %s, %s, %s)
            ON CONFLICT (owner_user_id) DO NOTHING
            """,
            (owner_user_id, DEFAULT_COOLDOWN_HOURS, DEFAULT_AUTO_REPLY_TEXT, DEFAULT_SLEEP_MESSAGE),
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
    """ESKI, atomik EMAS (tekshir-keyin-yoz). Yangi kodda try_claim_reply() ishlating."""
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
    """ESKI (atomik EMAS). Yangi kodda try_claim_reply() ishlating."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO replied_cache (owner_user_id, chat_id, last_reply_at)
            VALUES (%s, %s, %s)
            ON CONFLICT (owner_user_id, chat_id) DO UPDATE SET last_reply_at = EXCLUDED.last_reply_at
            """,
            (owner_user_id, chat_id, time.time()),
        )


def try_claim_reply(owner_user_id: int, chat_id: int, cooldown_hours: float) -> float | None:
    """Javob berish huquqini ATOMIK ravishda "band qiladi" (check-then-act
    poyga holatisiz).

    Eski usul (already_replied_recently -> send -> mark_replied) uchta alohida
    qadam edi: ikkita xabar (yoki ikkita instance) deyarli bir vaqtda kelsa,
    ikkalasi ham "cooldown yo'q" deb ko'rib, ikki marta javob yuborishi
    mumkin edi. Bu yerda tekshirish va yozish BITTA SQL buyrug'ida bajariladi:
    bir vaqtda kelgan ikkinchi so'rov birinchisining qatorini kutadi, so'ng
    yangilangan qiymatni ko'rib, cooldown ichida ekanini aniqlaydi.

    Qaytaradi: huquq olingan bo'lsa — band qilingan vaqt (timestamp; xabar
    yuborilmasa release_reply_claim()ga uzatiladi), cooldown hali tugamagan
    bo'lsa — None (javob BERMASLIK kerak)."""
    now = time.time()
    threshold = now - cooldown_hours * 3600
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO replied_cache (owner_user_id, chat_id, last_reply_at)
            VALUES (%s, %s, %s)
            ON CONFLICT (owner_user_id, chat_id) DO UPDATE
                SET last_reply_at = EXCLUDED.last_reply_at
                WHERE replied_cache.last_reply_at IS NULL
                   OR replied_cache.last_reply_at <= %s
            RETURNING last_reply_at
            """,
            (owner_user_id, chat_id, now, threshold),
        )
        row = cur.fetchone()
    return row[0] if row else None


def release_reply_claim(owner_user_id: int, chat_id: int, claimed_at: float):
    """Xabar yuborilmay qolsa (masalan Telegram xatosi) band qilingan huquqni
    qaytaradi — shunda keyingi xabarga baribir javob beriladi. Faqat AYNAN
    shu claim hali o'zgarmagan bo'lsa o'chiradi (`last_reply_at = claimed_at`),
    shuning uchun boshqa so'rovning yangi claim'ini bekor qilib yubormaydi.
    (Claim faqat cooldown tugagan bo'lsa olinadi, shuning uchun qatorni
    o'chirish — oldingi holatga qaytarish bilan bir xil natija beradi.)"""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "DELETE FROM replied_cache WHERE owner_user_id = %s AND chat_id = %s AND last_reply_at = %s",
            (owner_user_id, chat_id, claimed_at),
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
def record_user(user_id: int, username=_UNSET, full_name=_UNSET):
    """Foydalanuvchini yozadi. `username`/`full_name` berilsa (None ham —
    "yo'q" ma'nosida), ular yangilanadi: /block @username shu orqali ID topadi.
    Berilmasa — faqat mavjudligi yoziladi (eski xatti-harakat)."""
    if username is _UNSET and full_name is _UNSET:
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO users (user_id, first_seen)
                VALUES (%s, %s)
                ON CONFLICT (user_id) DO NOTHING
                """,
                (user_id, time.time()),
            )
        return

    columns, values, updates = ["user_id", "first_seen"], [user_id, time.time()], []
    if username is not _UNSET:
        username = (username or "").lstrip("@") or None
        columns.append("username")
        values.append(username)
        updates.append("username = EXCLUDED.username")
    if full_name is not _UNSET:
        columns.append("full_name")
        values.append(full_name or None)
        updates.append("full_name = EXCLUDED.full_name")

    with get_conn() as conn, conn.cursor() as cur:
        if username is not _UNSET and username:
            # Username boshqa odamga o'tgan bo'lishi mumkin — eski egasidan olib
            # tashlaymiz, shunda @username bo'yicha qidiruv bir ma'noli bo'ladi.
            cur.execute(
                "UPDATE users SET username = NULL WHERE lower(username) = lower(%s) AND user_id <> %s",
                (username, user_id),
            )
        cur.execute(
            f"INSERT INTO users ({', '.join(columns)}) VALUES ({', '.join(['%s'] * len(columns))}) "
            f"ON CONFLICT (user_id) DO UPDATE SET {', '.join(updates)}",
            values,
        )


def get_user(user_id: int):
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT user_id, username, full_name FROM users WHERE user_id = %s", (user_id,))
        row = cur.fetchone()
        return dict(row) if row else None


def get_user_lang(user_id: int):
    """Tanlangan til kodi yoki None (tanlamagan / bazada yo'q)."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT lang FROM users WHERE user_id = %s", (user_id,))
        row = cur.fetchone()
        return row[0] if row else None


def get_user_plan_info(user_id: int):
    """(tarif, tugash vaqti yoki None). Muddati o'tgan bo'lsa (fon job hali ulgurmagan bo'lsa ham) — ('free', None)."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT plan, plan_expires_at FROM users WHERE user_id = %s", (user_id,))
        row = cur.fetchone()
    if not row or not row[0]:
        return "free", None
    plan, expires_at = row
    if expires_at is not None and expires_at <= time.time():
        return "free", None
    return plan, expires_at


def get_user_plan(user_id: int) -> str:
    """Foydalanuvchi tarifi ('free' | 'plus' | 'pro' | 'ultra'); yozuv yoki qiymat bo'lmasa yoki muddati o'tgan bo'lsa — 'free'."""
    return get_user_plan_info(user_id)[0]


def set_user_plan(user_id: int, plan: str, expires_at: float | None = None) -> None:
    """Tarifni yozadi (foydalanuvchi qatori bo'lmasa yaratadi). `expires_at=None` — muddatsiz."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO users (user_id, first_seen, plan, plan_expires_at) VALUES (%s, %s, %s, %s)
            ON CONFLICT (user_id) DO UPDATE SET plan = EXCLUDED.plan, plan_expires_at = EXCLUDED.plan_expires_at
            """,
            (user_id, time.time(), plan, None if plan == "free" else expires_at),
        )


def list_plan_subscribers():
    """/userplans uchun: (pullik tarifdagi faol obunachilar, bepul tarifdagilar soni).
    Obunachi: tarifi 'free' emas va muddati o'tmagan (muddati o'tgan, lekin fon job ulgurmagan — bepul hisoblanadi).
    Har bir qator: user_id, username, full_name, plan, plan_expires_at. Tartib: tarif, so'ng muddat (yaqin tugaydigani oldin)."""
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT user_id, username, full_name, plan, plan_expires_at
            FROM users
            WHERE plan IS NOT NULL AND plan <> 'free'
              AND (plan_expires_at IS NULL OR plan_expires_at > EXTRACT(EPOCH FROM now()))
            ORDER BY plan, plan_expires_at ASC NULLS LAST, user_id
            """
        )
        paid = [dict(r) for r in cur.fetchall()]
        cur.execute("SELECT COUNT(*) FROM users")
        total = cur.fetchone()["count"]
    return paid, total - len(paid)


def expire_plans(now: float | None = None):
    """Muddati tugagan tariflarni bepulga qaytaradi (atomik). [(user_id, eski_tarif)] qaytaradi."""
    now = time.time() if now is None else now
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            WITH old AS (
                SELECT user_id, plan FROM users
                WHERE plan IS NOT NULL AND plan <> 'free'
                  AND plan_expires_at IS NOT NULL AND plan_expires_at <= %s
                FOR UPDATE
            )
            UPDATE users u SET plan = 'free', plan_expires_at = NULL
            FROM old WHERE u.user_id = old.user_id
            RETURNING u.user_id, old.plan
            """,
            (now,),
        )
        return [(r[0], r[1]) for r in cur.fetchall()]


# --------------------------------------------------------------------------
# Smart Onboarding (yangi foydalanuvchini ulash va sozlashga yo'naltirish)
# --------------------------------------------------------------------------
ONBOARDING_STEPS = ("legacy", "welcome", "connect", "configure", "verify", "completed", "skipped")
ONBOARDING_ACTIVE_STEPS = ("connect", "configure", "verify")


def get_onboarding_step(user_id: int) -> str:
    """Foydalanuvchining onboarding holati. Qator yo'q yoki noma'lum qiymat bo'lsa — 'legacy'
    (ya'ni onboarding ko'rsatilmaydi)."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT onboarding_step FROM users WHERE user_id = %s", (user_id,))
        row = cur.fetchone()
    step = row[0] if row else None
    return step if step in ONBOARDING_STEPS else "legacy"


def set_onboarding_step(user_id: int, step: str, only_from=None) -> bool:
    """Holatni o'zgartiradi. `only_from` (ro'yxat) berilsa — faqat hozirgi holat shulardan
    biri bo'lsagina (masalan, 'legacy' foydalanuvchi tasodifan onboarding'ga tushib qolmasin).
    O'zgargan bo'lsa True. Boshlanish/tugash vaqti avtomatik yoziladi."""
    if step not in ONBOARDING_STEPS:
        raise ValueError(f"Noma'lum onboarding holati: {step!r}")
    now = time.time()
    sql = (
        "UPDATE users SET onboarding_step = %s, "
        "onboarding_started_at = CASE WHEN onboarding_started_at IS NULL AND %s <> 'welcome' "
        "THEN %s ELSE onboarding_started_at END, "
        "onboarding_completed_at = CASE WHEN %s = 'completed' THEN %s ELSE onboarding_completed_at END "
        "WHERE user_id = %s"
    )
    params = [step, step, now, step, now, user_id]
    if only_from is not None:
        sql += " AND onboarding_step = ANY(%s)"
        params.append(list(only_from))
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.rowcount > 0


def onboarding_stats() -> dict:
    """Admin uchun: onboarding'ni boshlaganlar, ulaganlar, Auto-Reply yoqqanlar, tugatganlar."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT
              COUNT(*) FILTER (WHERE u.onboarding_started_at IS NOT NULL),
              COUNT(*) FILTER (WHERE u.onboarding_started_at IS NOT NULL
                               AND EXISTS (SELECT 1 FROM connections c
                                           WHERE c.owner_user_id = u.user_id AND c.is_enabled)),
              COUNT(*) FILTER (WHERE u.onboarding_started_at IS NOT NULL
                               AND EXISTS (SELECT 1 FROM settings s
                                           WHERE s.owner_user_id = u.user_id AND s.offline)),
              COUNT(*) FILTER (WHERE u.onboarding_step = 'completed'),
              COUNT(*) FILTER (WHERE u.onboarding_step = 'skipped'),
              COUNT(*) FILTER (WHERE u.onboarding_step IN ('connect', 'configure', 'verify'))
            FROM users u
            """
        )
        r = cur.fetchone()
    return {
        "started": r[0], "connected": r[1], "auto_reply_on": r[2],
        "completed": r[3], "skipped": r[4], "in_progress": r[5],
    }


def set_user_lang(user_id: int, lang: str) -> None:
    """Tilni saqlaydi (foydalanuvchi qatori bo'lmasa yaratadi)."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO users (user_id, first_seen, lang) VALUES (%s, %s, %s)
            ON CONFLICT (user_id) DO UPDATE SET lang = EXCLUDED.lang
            """,
            (user_id, time.time(), lang),
        )


def get_user_id_by_username(username: str):
    """@username -> user_id (bazada saqlangan bo'lsa), aks holda None."""
    username = username.lstrip("@")
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT user_id FROM users WHERE lower(username) = lower(%s)", (username,))
        row = cur.fetchone()
        return row[0] if row else None


def get_users_page(offset: int, limit: int):
    """/users uchun: eng yangi qo'shilganlar oldinda. Har bir qator:
    user_id, username, full_name, first_seen, is_blocked, block_reason, info_checked_at.
    (user_id bo'yicha ikkilamchi saralash — sahifalar orasida tartib barqaror bo'lishi uchun.)"""
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT u.user_id, u.username, u.full_name, u.first_seen, u.info_checked_at,
                   (b.user_id IS NOT NULL) AS is_blocked, b.reason AS block_reason
            FROM users u
            LEFT JOIN blocked_users b ON b.user_id = u.user_id
            ORDER BY COALESCE(u.first_seen, 0) DESC, u.user_id DESC
            OFFSET %s LIMIT %s
            """,
            (offset, limit),
        )
        return [dict(r) for r in cur.fetchall()]


def get_users_needing_info(limit: int, retry_before_ts: float):
    """Ismi hali noma'lum (eski, hali qayta yozmagan) foydalanuvchilar. Telegramdan
    ma'lumot olishga urinib ko'rilgan bo'lsa (info_checked_at), `retry_before_ts`dan
    keyin qayta uriniladi — shunda ulanib bo'lmaydigan odamlar har restartda
    takror-takror so'ralmaydi."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT user_id FROM users
            WHERE full_name IS NULL
              AND (info_checked_at IS NULL OR info_checked_at < %s)
            ORDER BY user_id
            LIMIT %s
            """,
            (retry_before_ts, limit),
        )
        return [row[0] for row in cur.fetchall()]


def set_user_info(user_id: int, username, full_name):
    """Telegramdan olingan ism/username'ni saqlaydi va tekshirilgan deb belgilaydi.
    Faqat BERILGAN (None bo'lmagan) maydonlar yangilanadi: Telegram bo'sh qiymat
    qaytarsa, foydalanuvchi shu orada o'zi yozib saqlatgan ma'lumot o'chib ketmaydi."""
    fields = {}
    if username:
        fields["username"] = username
    if full_name:
        fields["full_name"] = full_name
    if fields:
        record_user(user_id, **fields)
    mark_user_info_checked(user_id)


def mark_user_info_checked(user_id: int):
    """Ma'lumot olishga urinildi (muvaffaqiyatli yoki yo'q) — keyingi urinish bir muddatdan keyin."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("UPDATE users SET info_checked_at = %s WHERE user_id = %s", (time.time(), user_id))


# Reklama: foydalanuvchi botni bloklagan/akkaunti o'chgan — qayta urinish foydasiz (har safar yana shunday bo'ladi)
NON_RETRYABLE_FAILURE = "blocked/deleted"

_BOT_LIKE_WHERE = """
    lower(username) LIKE '%%bot'
    AND NOT EXISTS (SELECT 1 FROM connections c WHERE c.owner_user_id = users.user_id)
"""


def list_bot_like_users(limit: int = 50):
    """Username'i 'bot' bilan tugaydigan (Telegram botlari shunday nomlanadi) va
    akkaunti ulanmagan yozuvlar. Eski xatodan bazaga tushib qolgan botlarni topish uchun."""
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            f"SELECT user_id, username, full_name FROM users WHERE {_BOT_LIKE_WHERE} "
            "ORDER BY user_id LIMIT %s",
            (limit,),
        )
        return [dict(r) for r in cur.fetchall()]


def delete_bot_like_users(user_ids=None) -> int:
    """list_bot_like_users() bilan bir xil shart bo'yicha o'chiradi. O'chirilganlar sonini qaytaradi.

    `user_ids` berilsa — FAQAT shu ID'lar (va ular hamon shartga mos bo'lsa) o'chiriladi: admin /bots
    ro'yxatida ko'rgan yozuvlardan boshqasiga tegilmaydi. Berilmasa — shartga mos hammasi (eski xatti-harakat)."""
    with get_conn() as conn, conn.cursor() as cur:
        if user_ids is None:
            cur.execute(f"DELETE FROM users WHERE {_BOT_LIKE_WHERE}")
        else:
            cur.execute(
                f"DELETE FROM users WHERE {_BOT_LIKE_WHERE} AND user_id = ANY(%s)",
                (list(user_ids),),
            )
        return cur.rowcount


def get_user_count(exclude_blocked: bool = False) -> int:
    with get_conn() as conn, conn.cursor() as cur:
        if exclude_blocked:
            cur.execute(
                "SELECT COUNT(*) FROM users u "
                "WHERE NOT EXISTS (SELECT 1 FROM blocked_users b WHERE b.user_id = u.user_id)"
            )
        else:
            cur.execute("SELECT COUNT(*) FROM users")
        return cur.fetchone()[0]


def get_user_ids_after(last_user_id: int, limit: int = 200):
    """Keyset pagination: `last_user_id`dan katta bo'lgan keyingi `limit` ta
    foydalanuvchi ID'sini qaytaradi. Bu butun jadvalni bir vaqtda xotiraga
    yuklamaslik uchun — 100,000+ foydalanuvchida ham xotira muammosi
    tug'dirmaydi, chunki har safar faqat kichik bo'lak o'qiladi."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            # Bloklangan foydalanuvchilar reklama olmaydi
            "SELECT user_id FROM users u WHERE user_id > %s "
            "AND NOT EXISTS (SELECT 1 FROM blocked_users b WHERE b.user_id = u.user_id) "
            "ORDER BY user_id LIMIT %s",
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


def get_failed_user_ids_after(source_job_id: int, last_user_id: int, limit: int = 200):
    """Retry job uchun: `source_job_id`da muvaffaqiyatsiz bo'lgan
    foydalanuvchilardan `last_user_id`dan kattalarini qaytaradi. Bu bazadan
    o'qiladi (RAM'dagi vaqtinchalik ro'yxat emas), shuning uchun server
    restart bo'lsa ham retry job to'g'ri (faqat shu cheklangan ro'yxatdan)
    davom etaveradi."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT user_id FROM broadcast_failures f
            WHERE job_id = %s AND user_id > %s
              AND error_text IS DISTINCT FROM %s
              AND NOT EXISTS (SELECT 1 FROM blocked_users b WHERE b.user_id = f.user_id)
            ORDER BY user_id
            LIMIT %s
            """,
            (source_job_id, last_user_id, NON_RETRYABLE_FAILURE, limit),
        )
        return [row[0] for row in cur.fetchall()]


# --------------------------------------------------------------------------
# Reklama (broadcast) job — fonda ishlaydi va qayta ishga tushirilsa davom
# ettirila oladi (resumable), muvaffaqiyatsiz bo'lganlar alohida saqlanadi.
# --------------------------------------------------------------------------
def create_broadcast_job(
    source_chat_id: int, source_message_id: int, total_count: int, retry_of_job_id: int | None = None
) -> int:
    now = time.time()
    new_id = None
    violated = False
    # try/except ATAYIN `with` blokining ICHIDA — shunda UniqueViolation
    # bo'lsa ham `with`dan hech qanday exception chiqmaydi va _PooledConnection
    # ulanishni (soppa-sog' bo'lsa ham) yopib tashlash o'rniga pool'ga
    # normal qaytaradi (bu xato juda tez-tez, kutilgan holat bo'lishi mumkin).
    with get_conn() as conn, conn.cursor() as cur:
        try:
            cur.execute(
                """
                INSERT INTO broadcast_jobs
                    (source_chat_id, source_message_id, status, last_user_id, total_count, retry_of_job_id, created_at, updated_at)
                VALUES (%s, %s, 'running', 0, %s, %s, %s, %s)
                RETURNING id
                """,
                (source_chat_id, source_message_id, total_count, retry_of_job_id, now, now),
            )
            new_id = cur.fetchone()[0]
        except psycopg2.errors.UniqueViolation:
            violated = True
    if violated:
        raise BroadcastAlreadyRunningError("Hozir allaqachon boshqa reklama 'running' holatida")
    return new_id


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
    """status='running'ga o'tkazishda, agar boshqa job allaqachon 'running'
    bo'lsa, partial unique index tufayli BroadcastAlreadyRunningError
    chiqadi (masalan /reklama_retry orqali 'failed' job'ni qayta tiklashda).
    'completed'/'failed'ga o'tkazishda bu konflikt hech qachon bo'lmaydi."""
    violated = False
    with get_conn() as conn, conn.cursor() as cur:
        try:
            cur.execute(
                "UPDATE broadcast_jobs SET status = %s, updated_at = %s WHERE id = %s",
                (status, time.time(), job_id),
            )
        except psycopg2.errors.UniqueViolation:
            violated = True
    if violated:
        raise BroadcastAlreadyRunningError("Hozir allaqachon boshqa reklama 'running' holatida")


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
    """Qayta urinishga arziydigan muvaffaqiyatsizlar (botni bloklagan/akkaunti o'chganlar kirmaydi)."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT user_id FROM broadcast_failures WHERE job_id = %s AND error_text IS DISTINCT FROM %s",
            (job_id, NON_RETRYABLE_FAILURE),
        )
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
                   s.bio_countdown_target, s.birthday_month, s.birthday_day, s.bio_updated_on,
                   u.lang,
                   CASE WHEN u.plan IS NULL OR (u.plan_expires_at IS NOT NULL AND u.plan_expires_at <= EXTRACT(EPOCH FROM now())) THEN 'free' ELSE u.plan END AS plan
            FROM connections c
            JOIN settings s ON s.owner_user_id = c.owner_user_id
            LEFT JOIN users u ON u.user_id = c.owner_user_id
            WHERE c.is_enabled = TRUE AND c.can_edit_bio = TRUE
              AND s.bio_countdown_target IS NOT NULL
              AND NOT EXISTS (SELECT 1 FROM blocked_users b WHERE b.user_id = c.owner_user_id)
            """
        )
        return [dict(r) for r in cur.fetchall()]


# --------------------------------------------------------------------------
# Smart FAQ (har bir egasining savol-javoblari alohida; hamma so'rov owner_user_id bilan cheklangan)
# --------------------------------------------------------------------------
_FAQ_COLS = "id, owner_user_id, question, keywords, answer, is_enabled"


def add_faq_entry(owner_user_id: int, question: str, keywords: list[str], answer: str, max_entries: int) -> int | None:
    """Yangi yozuv qo'shadi va id qaytaradi; limit to'lgan bo'lsa — None.

    Parallel so'rovlardan himoya: bir egasi uchun yozishlar tranzaksiya-darajali advisory lock bilan ketma-ket
    bajariladi (lock olingach INSERT yangi snapshot bilan sanaydi, shuning uchun boshqa so'rov qo'shgan yozuv
    ham hisobga olinadi). Oddiy `INSERT ... WHERE count < limit` READ COMMITTED'da ikki so'rovga ham ruxsat berardi."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("BEGIN")
        try:
            cur.execute("SELECT pg_advisory_xact_lock(hashtext('faq_entries'), (%s %% 2147483647)::int)", (owner_user_id,))
            cur.execute(
                """
                INSERT INTO faq_entries (owner_user_id, question, keywords, answer)
                SELECT %s, %s, %s, %s
                WHERE (SELECT COUNT(*) FROM faq_entries WHERE owner_user_id = %s) < %s
                RETURNING id
                """,
                (owner_user_id, question, keywords, answer, owner_user_id, max_entries),
            )
            row = cur.fetchone()
            cur.execute("COMMIT")
        except BaseException:
            try:
                cur.execute("ROLLBACK")
            except Exception:
                pass
            raise
        return row[0] if row else None


_FAQ_EDITABLE = {"question": "question", "keywords": "keywords", "answer": "answer"}


def update_faq_entry(owner_user_id: int, entry_id: int, **fields) -> bool:
    """Yozuvning savol/kalit so'z/javobini o'zgartiradi (id, egasi va yoqilgan holati o'zgarmaydi).
    Yozuv shu egasiga tegishli bo'lmasa yoki topilmasa — False."""
    invalid = set(fields) - set(_FAQ_EDITABLE)
    if invalid or not fields:
        raise ValueError(f"Ruxsat etilmagan FAQ maydoni: {invalid or 'bo`sh'}")
    assignments = ", ".join(f"{_FAQ_EDITABLE[k]} = %s" for k in fields)
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            f"UPDATE faq_entries SET {assignments} WHERE owner_user_id = %s AND id = %s",
            list(fields.values()) + [owner_user_id, entry_id],
        )
        return cur.rowcount > 0


_AUTOMATION_COLS = "id, owner_user_id, name, conditions, action, priority, is_enabled, sent_count, last_sent_at"


def add_automation_rule(owner_user_id: int, name, conditions, action, priority: int, max_rules: int, enabled: bool = False) -> int | None:
    """Yangi qoida qo'shadi (sukut bo'yicha O'CHIRILGAN holatda; panel foydalanuvchi tasdiqlagach enabled=True beradi) va id qaytaradi; limit to'lgan bo'lsa — None.
    Ma'lumot avval automation.validate_automation'dan o'tadi (noto'g'ri bo'lsa AutomationError — bazaga yozilmaydi).
    Parallel so'rovlardan himoya: egasi uchun yozishlar advisory lock bilan ketma-ket (add_faq_entry kabi)."""
    clean = automation.validate_automation(name, conditions, action, priority)
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("BEGIN")
        try:
            cur.execute("SELECT pg_advisory_xact_lock(hashtext('automation_rules'), (%s %% 2147483647)::int)", (owner_user_id,))
            cur.execute(
                """
                INSERT INTO automation_rules (owner_user_id, name, conditions, action, priority, is_enabled)
                SELECT %s, %s, %s, %s, %s, %s
                WHERE (SELECT COUNT(*) FROM automation_rules WHERE owner_user_id = %s) < %s
                RETURNING id
                """,
                (owner_user_id, clean["name"], psycopg2.extras.Json(clean["conditions"]),
                 psycopg2.extras.Json(clean["action"]), clean["priority"], bool(enabled), owner_user_id, max_rules),
            )
            row = cur.fetchone()
            cur.execute("COMMIT")
        except BaseException:
            try:
                cur.execute("ROLLBACK")
            except Exception:
                pass
            raise
    return row[0] if row else None


_AUTOMATION_EDIT_FIELDS = frozenset({"name", "keywords", "days", "time_range", "reply", "priority"})


def update_automation_rule(owner_user_id: int, rule_id: int, **changes) -> bool:
    """Mavjud qoidani tahrirlaydi — FAQAT berilgan maydonlar o'zgaradi (qolganlari bazadagi joriy qiymatida qoladi):
    name, keywords (str yoki ro'yxat; 2+ ta = YOKI), days (ro'yxat; None/[] = olib tashlash), time_range ((boshlanish, tugash)
    yoki None = olib tashlash), reply, priority.
    Hammasi BITTA tranzaksiyada: qator `FOR UPDATE` bilan qulflanadi (ikki tahrir bir-birining o'zgarishini bosib ketmaydi),
    yangi qiymatlar yig'ilgach automation.validate_automation'dan o'tadi (noto'g'ri bo'lsa AutomationError — hech narsa yozilmaydi).
    Boshqa egasining yoki yo'q qoida uchun — False. is_enabled, sent_count va id tegilmaydi."""
    invalid = set(changes) - _AUTOMATION_EDIT_FIELDS
    if invalid or not changes:
        raise ValueError(f"Ruxsat etilmagan automation maydoni: {invalid or 'bo`sh'}")
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("BEGIN")
        try:
            cur.execute(
                "SELECT name, conditions, action, priority FROM automation_rules WHERE owner_user_id = %s AND id = %s FOR UPDATE",
                (owner_user_id, rule_id),
            )
            row = cur.fetchone()
            if row is None:
                cur.execute("ROLLBACK")
                return False
            current = {"conditions": row["conditions"]}
            keywords = automation.split_keywords(current)
            _, days, time_range = automation.split_conditions(current)
            if "keywords" in changes:
                keywords = changes["keywords"]
            if "days" in changes:
                days = changes["days"] or None
            if "time_range" in changes:
                time_range = changes["time_range"]
            if isinstance(keywords, str):
                keywords = [keywords]
            if not isinstance(keywords, (list, tuple)) or not keywords:
                raise automation.AutomationError("keyword_required")
            action = dict(row["action"]) if isinstance(row["action"], dict) else {}
            if "reply" in changes:
                action = {"type": "send_reply", "text": changes["reply"]}
            clean = automation.validate_automation(
                changes.get("name", row["name"]),
                automation.build_conditions(list(keywords), days, time_range),
                action,
                changes.get("priority", row["priority"]),
            )
            cur.execute(
                "UPDATE automation_rules SET name = %s, conditions = %s, action = %s, priority = %s "
                "WHERE owner_user_id = %s AND id = %s",
                (clean["name"], psycopg2.extras.Json(clean["conditions"]), psycopg2.extras.Json(clean["action"]),
                 clean["priority"], owner_user_id, rule_id),
            )
            cur.execute("COMMIT")
        except BaseException:
            try:
                cur.execute("ROLLBACK")
            except Exception:
                pass
            raise
    return True


def record_automation_sent(owner_user_id: int, rule_id: int) -> bool:
    """Qoida javobi MUVAFFAQIYATLI yuborilgach sanagichni atomik oshiradi (boshqa egasiniki/o'chirilgan qoida — False)."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE automation_rules SET sent_count = sent_count + 1, last_sent_at = NOW() WHERE owner_user_id = %s AND id = %s",
            (owner_user_id, rule_id),
        )
        return cur.rowcount > 0


def list_automation_rules(owner_user_id: int) -> list[dict]:
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            f"SELECT {_AUTOMATION_COLS} FROM automation_rules WHERE owner_user_id = %s ORDER BY priority, id",
            (owner_user_id,),
        )
        return [dict(r) for r in cur.fetchall()]


def get_enabled_automation_rules(owner_user_id: int) -> list[dict]:
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            f"SELECT {_AUTOMATION_COLS} FROM automation_rules WHERE owner_user_id = %s AND is_enabled = TRUE ORDER BY priority, id",
            (owner_user_id,),
        )
        return [dict(r) for r in cur.fetchall()]


def count_automation_rules(owner_user_id: int) -> int:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM automation_rules WHERE owner_user_id = %s", (owner_user_id,))
        return cur.fetchone()[0]


def set_automation_rule_enabled(owner_user_id: int, rule_id: int, enabled: bool) -> bool:
    """Qoidani ANIQ holatga o'rnatadi (idempotent). Qoida topilmasa yoki boshqa egasiniki bo'lsa — False."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE automation_rules SET is_enabled = %s WHERE owner_user_id = %s AND id = %s",
            (bool(enabled), owner_user_id, rule_id),
        )
        return cur.rowcount > 0


def delete_automation_rule(owner_user_id: int, rule_id: int) -> bool:
    """Qoidani o'chiradi; uning yuborilgan javoblar soni egasining tarixiy jamiga ATOMIK qo'shiladi (bitta so'rov) —
    statistikadagi «jami» qoida o'chirilgach kamayib ketmaydi."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            WITH d AS (
                DELETE FROM automation_rules WHERE owner_user_id = %s AND id = %s RETURNING sent_count
            ), u AS (
                INSERT INTO automation_deleted_totals (owner_user_id, sent_count)
                SELECT %s, sent_count FROM d WHERE sent_count > 0
                ON CONFLICT (owner_user_id) DO UPDATE SET sent_count = automation_deleted_totals.sent_count + EXCLUDED.sent_count
            )
            SELECT COUNT(*) FROM d
            """,
            (owner_user_id, rule_id, owner_user_id),
        )
        return cur.fetchone()[0] > 0


def get_automation_deleted_sent(owner_user_id: int) -> int:
    """Egasining o'chirilgan qoidalari bo'yicha tarixiy yuborilgan javoblar soni."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT sent_count FROM automation_deleted_totals WHERE owner_user_id = %s", (owner_user_id,))
        row = cur.fetchone()
        return int(row[0]) if row else 0


def get_automation_counters_since():
    """Qoida sanagichlari (v1.2) hisoblana boshlagan vaqt: undan oldingi javoblar tiklanmaydi."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT value FROM automation_meta WHERE key = 'counters_since'")
        row = cur.fetchone()
        return row[0] if row else None


def list_faq_entries(owner_user_id: int) -> list[dict]:
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(f"SELECT {_FAQ_COLS} FROM faq_entries WHERE owner_user_id = %s ORDER BY id", (owner_user_id,))
        return [dict(r) for r in cur.fetchall()]


def get_enabled_faq_entries(owner_user_id: int) -> list[dict]:
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            f"SELECT {_FAQ_COLS} FROM faq_entries WHERE owner_user_id = %s AND is_enabled = TRUE ORDER BY id",
            (owner_user_id,),
        )
        return [dict(r) for r in cur.fetchall()]


def get_faq_entry(owner_user_id: int, entry_id: int) -> dict | None:
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            f"SELECT {_FAQ_COLS} FROM faq_entries WHERE owner_user_id = %s AND id = %s", (owner_user_id, entry_id)
        )
        row = cur.fetchone()
        return dict(row) if row else None


def count_faq_entries(owner_user_id: int) -> int:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM faq_entries WHERE owner_user_id = %s", (owner_user_id,))
        return cur.fetchone()[0]


def delete_faq_entry(owner_user_id: int, entry_id: int) -> bool:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM faq_entries WHERE owner_user_id = %s AND id = %s", (owner_user_id, entry_id))
        return cur.rowcount > 0


def set_faq_entry_enabled(owner_user_id: int, entry_id: int, enabled: bool) -> bool:
    """Yozuvni ANIQ holatga o'rnatadi (idempotent: eski tugma qayta bosilsa holat teskarilanmaydi). Yozuv topilmasa — False."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE faq_entries SET is_enabled = %s WHERE owner_user_id = %s AND id = %s",
            (bool(enabled), owner_user_id, entry_id),
        )
        return cur.rowcount > 0


def toggle_faq_entry(owner_user_id: int, entry_id: int) -> bool | None:
    """Yozuvni yoqadi/o'chiradi; yangi holatni qaytaradi (yozuv topilmasa — None)."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE faq_entries SET is_enabled = NOT is_enabled WHERE owner_user_id = %s AND id = %s RETURNING is_enabled",
            (owner_user_id, entry_id),
        )
        row = cur.fetchone()
        return row[0] if row else None


# --------------------------------------------------------------------------
# AI Knowledge Base (har bir egasining ma'lumotlari alohida; hamma so'rov owner_user_id bilan cheklangan)
# --------------------------------------------------------------------------
_KB_COLS = "id, owner_user_id, title, content, keywords, is_enabled"


def add_kb_entry(owner_user_id: int, title: str, content: str, keywords: list[str], max_entries: int) -> int | None:
    """Yangi yozuv qo'shadi va id qaytaradi; limit to'lgan bo'lsa — None. Parallel so'rovlardan himoya:
    bir egasi uchun yozishlar advisory lock bilan ketma-ket bajariladi (FAQ bilan bir xil usul)."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("BEGIN")
        try:
            cur.execute("SELECT pg_advisory_xact_lock(hashtext('knowledge_entries'), (%s %% 2147483647)::int)", (owner_user_id,))
            cur.execute(
                """
                INSERT INTO knowledge_entries (owner_user_id, title, content, keywords)
                SELECT %s, %s, %s, %s
                WHERE (SELECT COUNT(*) FROM knowledge_entries WHERE owner_user_id = %s) < %s
                RETURNING id
                """,
                (owner_user_id, title, content, keywords, owner_user_id, max_entries),
            )
            row = cur.fetchone()
            cur.execute("COMMIT")
        except BaseException:
            try:
                cur.execute("ROLLBACK")
            except Exception:
                pass
            raise
        return row[0] if row else None


_KB_EDITABLE = ("title", "content", "keywords")


def update_kb_entry(owner_user_id: int, entry_id: int, **fields) -> bool:
    """Sarlavha/ma'lumot/kalit so'zlarni o'zgartiradi. Yozuv shu egasiga tegishli bo'lmasa yoki topilmasa — False."""
    invalid = set(fields) - set(_KB_EDITABLE)
    if invalid or not fields:
        raise ValueError(f"Ruxsat etilmagan Knowledge Base maydoni: {invalid or 'bo`sh'}")
    assignments = ", ".join(f"{k} = %s" for k in fields)
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            f"UPDATE knowledge_entries SET {assignments} WHERE owner_user_id = %s AND id = %s",
            list(fields.values()) + [owner_user_id, entry_id],
        )
        return cur.rowcount > 0


def list_kb_entries(owner_user_id: int) -> list[dict]:
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(f"SELECT {_KB_COLS} FROM knowledge_entries WHERE owner_user_id = %s ORDER BY id", (owner_user_id,))
        return [dict(r) for r in cur.fetchall()]


def get_enabled_kb_entries(owner_user_id: int) -> list[dict]:
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            f"SELECT {_KB_COLS} FROM knowledge_entries WHERE owner_user_id = %s AND is_enabled = TRUE ORDER BY id",
            (owner_user_id,),
        )
        return [dict(r) for r in cur.fetchall()]


def get_kb_entry(owner_user_id: int, entry_id: int) -> dict | None:
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            f"SELECT {_KB_COLS} FROM knowledge_entries WHERE owner_user_id = %s AND id = %s", (owner_user_id, entry_id)
        )
        row = cur.fetchone()
        return dict(row) if row else None


def count_kb_entries(owner_user_id: int) -> int:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM knowledge_entries WHERE owner_user_id = %s", (owner_user_id,))
        return cur.fetchone()[0]


def delete_kb_entry(owner_user_id: int, entry_id: int) -> bool:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM knowledge_entries WHERE owner_user_id = %s AND id = %s", (owner_user_id, entry_id))
        return cur.rowcount > 0


def set_kb_entry_enabled(owner_user_id: int, entry_id: int, enabled: bool) -> bool:
    """Yozuvni ANIQ holatga o'rnatadi (idempotent). Yozuv topilmasa — False."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE knowledge_entries SET is_enabled = %s WHERE owner_user_id = %s AND id = %s",
            (bool(enabled), owner_user_id, entry_id),
        )
        return cur.rowcount > 0


def toggle_kb_entry(owner_user_id: int, entry_id: int) -> bool | None:
    """Yozuvni yoqadi/o'chiradi; yangi holatni qaytaradi (yozuv topilmasa — None)."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE knowledge_entries SET is_enabled = NOT is_enabled WHERE owner_user_id = %s AND id = %s RETURNING is_enabled",
            (owner_user_id, entry_id),
        )
        row = cur.fetchone()
        return row[0] if row else None


def get_bio_ad_candidates():
    """Ism soati yoqilgan YOKI BIO'ga reklama yozib qo'yilgan (olib tashlash kerak bo'lishi mumkin) egalar."""
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT c.owner_user_id, c.business_connection_id,
                   s.name_clock_enabled, s.clock_bio_ad,
                   s.bio_countdown_target, s.birthday_month, s.birthday_day,
                   u.lang,
                   CASE WHEN u.plan IS NULL OR (u.plan_expires_at IS NOT NULL AND u.plan_expires_at <= EXTRACT(EPOCH FROM now())) THEN 'free' ELSE u.plan END AS plan
            FROM connections c
            JOIN settings s ON s.owner_user_id = c.owner_user_id
            LEFT JOIN users u ON u.user_id = c.owner_user_id
            WHERE c.is_enabled = TRUE AND c.can_edit_bio = TRUE
              AND (s.name_clock_enabled = TRUE OR s.clock_bio_ad = TRUE)
              AND NOT EXISTS (SELECT 1 FROM blocked_users b WHERE b.user_id = c.owner_user_id)
            """
        )
        return [dict(r) for r in cur.fetchall()]


# --------------------------------------------------------------------------
# Bloklash (admin) va apellyatsiya (bloklangan foydalanuvchining izohi)
# --------------------------------------------------------------------------
def block_user(user_id: int, reason: str, blocked_by: int) -> bool:
    """True — yangi bloklandi; False — allaqachon bloklangan edi (hech narsa o'zgarmaydi)."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO blocked_users (user_id, reason, blocked_by, blocked_at)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (user_id) DO NOTHING
            """,
            (user_id, reason or "", blocked_by, time.time()),
        )
        return cur.rowcount > 0


def unblock_user(user_id: int) -> bool:
    """True — blokdan chiqarildi; False — u bloklanmagan edi."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM blocked_users WHERE user_id = %s", (user_id,))
        return cur.rowcount > 0


def get_block(user_id: int):
    """Bloklangan bo'lsa {'user_id','reason','blocked_by','blocked_at'}, aks holda None."""
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM blocked_users WHERE user_id = %s", (user_id,))
        row = cur.fetchone()
        return dict(row) if row else None


def list_blocked(limit: int = 30):
    """Eng oxirgi bloklanganlar oldinda; username/ism bo'lsa qo'shib beradi."""
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT b.user_id, b.reason, b.blocked_at, u.username, u.full_name
            FROM blocked_users b
            LEFT JOIN users u ON u.user_id = b.user_id
            ORDER BY b.blocked_at DESC
            LIMIT %s
            """,
            (limit,),
        )
        return [dict(r) for r in cur.fetchall()]


def count_blocked() -> int:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM blocked_users")
        return cur.fetchone()[0]


def add_appeal(user_id: int, message: str) -> int:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO block_appeals (user_id, message, created_at) VALUES (%s, %s, %s) RETURNING id",
            (user_id, message, time.time()),
        )
        return cur.fetchone()[0]


def count_recent_appeals(user_id: int, since_ts: float) -> int:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM block_appeals WHERE user_id = %s AND created_at >= %s",
            (user_id, since_ts),
        )
        return cur.fetchone()[0]


def add_feedback(user_id: int, message: str) -> int:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO feedback_messages (user_id, message, created_at) VALUES (%s, %s, %s) RETURNING id",
            (user_id, message, time.time()),
        )
        return cur.fetchone()[0]


def count_recent_feedback(user_id: int, since_ts: float) -> int:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM feedback_messages WHERE user_id = %s AND created_at >= %s",
            (user_id, since_ts),
        )
        return cur.fetchone()[0]


# --------------------------------------------------------------------------
# AI-Yordamchi: kunlik limit, suhbat tarixi, "egasi o'zi yozdi" pauzasi
# --------------------------------------------------------------------------
def add_ai_messages(owner_user_id: int, chat_id: int, messages: list, keep: int = 10):
    """messages: [(role, text), ...] — tartib bilan qo'shiladi. Shu chat uchun faqat
    oxirgi `keep` ta xabar saqlanadi (qolgani o'chadi)."""
    now = time.time()
    with get_conn() as conn, conn.cursor() as cur:
        for role, text in messages:
            cur.execute(
                "INSERT INTO ai_chat_history (owner_user_id, chat_id, role, text, created_at) "
                "VALUES (%s, %s, %s, %s, %s)",
                (owner_user_id, chat_id, role, text, now),
            )
        cur.execute(
            """
            DELETE FROM ai_chat_history
            WHERE owner_user_id = %s AND chat_id = %s
              AND id NOT IN (
                  SELECT id FROM ai_chat_history
                  WHERE owner_user_id = %s AND chat_id = %s
                  ORDER BY id DESC LIMIT %s
              )
            """,
            (owner_user_id, chat_id, owner_user_id, chat_id, keep),
        )


def try_consume_ai_quota(owner_user_id: int, day: str, limit: int) -> bool:
    """Bugungi AI javoblar limitidan bittasini ATOMIK band qiladi (bitta SQL).
    True — ruxsat berildi; False — limit tugagan."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO ai_usage (owner_user_id, day, count) VALUES (%s, %s, 1)
            ON CONFLICT (owner_user_id, day) DO UPDATE SET count = ai_usage.count + 1
            WHERE ai_usage.count < %s
            RETURNING count
            """,
            (owner_user_id, day, limit),
        )
        return cur.fetchone() is not None


def refund_ai_quota(owner_user_id: int, day: str):
    """Javob yuborilmagan bo'lsa, band qilingan limitni qaytaradi."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE ai_usage SET count = count - 1 WHERE owner_user_id = %s AND day = %s AND count > 0",
            (owner_user_id, day),
        )


def get_ai_usage(owner_user_id: int, day: str) -> int:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT count FROM ai_usage WHERE owner_user_id = %s AND day = %s", (owner_user_id, day))
        row = cur.fetchone()
        return row[0] if row else 0


# AI yozishmalar tarixi shuncha vaqtdan keyin unutiladi (ham javobda, ham bazadan tozalashda)
AI_HISTORY_MAX_AGE_SECONDS = 2 * 86400  # 2 kun


def get_ai_history(owner_user_id: int, chat_id: int, limit: int = 10, max_age_seconds: float = AI_HISTORY_MAX_AGE_SECONDS):
    """Oxirgi `limit` ta xabar, eskidan yangiga: [{'role','text'}]. Juda eskilari hisobga olinmaydi."""
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT role, text FROM (
                SELECT id, role, text FROM ai_chat_history
                WHERE owner_user_id = %s AND chat_id = %s AND created_at >= %s
                ORDER BY id DESC LIMIT %s
            ) t ORDER BY id
            """,
            (owner_user_id, chat_id, time.time() - max_age_seconds, limit),
        )
        return [dict(r) for r in cur.fetchall()]


def pause_ai_chat(owner_user_id: int, chat_id: int, seconds: float):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO ai_chat_pause (owner_user_id, chat_id, paused_until) VALUES (%s, %s, %s)
            ON CONFLICT (owner_user_id, chat_id) DO UPDATE SET paused_until = EXCLUDED.paused_until
            """,
            (owner_user_id, chat_id, time.time() + seconds),
        )


def is_ai_paused(owner_user_id: int, chat_id: int) -> bool:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM ai_chat_pause WHERE owner_user_id = %s AND chat_id = %s AND paused_until > %s",
            (owner_user_id, chat_id, time.time()),
        )
        return cur.fetchone() is not None


def delete_ai_data(owner_user_id: int):
    """Akkaunt uzilganda: shu egasining suhbat tarixi va pauzalari o'chiriladi."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM ai_chat_history WHERE owner_user_id = %s", (owner_user_id,))
        cur.execute("DELETE FROM ai_chat_pause WHERE owner_user_id = %s", (owner_user_id,))


def purge_old_ai_data(max_age_seconds: float = AI_HISTORY_MAX_AGE_SECONDS):
    cutoff = time.time() - max_age_seconds
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM ai_chat_history WHERE created_at < %s", (cutoff,))
        cur.execute("DELETE FROM ai_chat_pause WHERE paused_until < %s", (time.time(),))
        cur.execute("DELETE FROM ai_usage WHERE day < %s", (time.strftime("%Y-%m-%d", time.gmtime(cutoff)),))


# --------------------------------------------------------------------------
# Smart Auto-Reply Scheduler
# --------------------------------------------------------------------------
def list_schedule_rules(owner_user_id: int):
    """Egasining jadvallari (id bo'yicha tartiblangan — raqamlash va tarif limiti shu tartibda)."""
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM schedule_rules WHERE owner_user_id = %s ORDER BY id", (owner_user_id,))
        return [dict(r) for r in cur.fetchall()]


# Jadvallar keshi: har bir mijoz xabarida bazaga bormaslik uchun (bo'sh ro'yxat ham keshlanadi — ko'pchilikda jadval yo'q).
# Har qanday o'zgarishda (qo'shish/tahrirlash/o'chirish) shu egasining keshi darhol tozalanadi; TTL — boshqa instansiya
# o'zgartirgan holat uchun xavfsizlik chegarasi.
SCHEDULE_CACHE_TTL_SECONDS = 60
_SCHEDULE_CACHE_MAX = 5000
_schedule_cache: dict[int, tuple[float, list]] = {}
_schedule_cache_lock = threading.Lock()
# Avlod hisoblagichi: har bir invalidatsiyada oshadi. O'quvchi bazadan o'qishni boshlashdan oldin avlodni eslab qoladi va
# natijani keshga FAQAT shu vaqt ichida invalidatsiya bo'lmagan bo'lsa yozadi — shunda parallel yozuv bilan
# poyga (eski ma'lumot yangi tozalangan keshga qaytib yozilishi) bo'lmaydi.
_schedule_cache_gen = 0
_SCHEDULE_READ_RETRIES = 3


def invalidate_schedule_cache(owner_user_id: int):
    global _schedule_cache_gen
    with _schedule_cache_lock:
        _schedule_cache_gen += 1
        _schedule_cache.pop(owner_user_id, None)


def get_schedule_rules_cached(owner_user_id: int):
    """list_schedule_rules() ning qisqa muddatli keshlangan varianti (faqat o'qish uchun — ro'yxatni o'zgartirmang)."""
    now = time.monotonic()
    with _schedule_cache_lock:
        hit = _schedule_cache.get(owner_user_id)
        if hit and now - hit[0] < SCHEDULE_CACHE_TTL_SECONDS:
            return hit[1]
    # O'qish davomida jadval o'zgargan bo'lsa (avlod almashgan) — natija eskirgan: keshga yozilmaydi va
    # chaqiruvchiga ham qaytarilmaydi, bazadan qayta o'qiladi (cheklangan urinishlar bilan).
    for attempt in range(_SCHEDULE_READ_RETRIES):
        with _schedule_cache_lock:
            gen = _schedule_cache_gen
        rules = list_schedule_rules(owner_user_id)
        with _schedule_cache_lock:
            if gen == _schedule_cache_gen:
                if len(_schedule_cache) >= _SCHEDULE_CACHE_MAX:
                    _schedule_cache.clear()
                _schedule_cache[owner_user_id] = (time.monotonic(), rules)
                return rules
    return rules  # doimiy parallel yozuv: oxirgi o'qilgan (eng yangi) natija, keshsiz


def get_schedule_rule(owner_user_id: int, rule_id: int):
    """Faqat shu egasiniki; boshqasiniki 'topilmadi' (None)."""
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM schedule_rules WHERE id = %s AND owner_user_id = %s", (rule_id, owner_user_id))
        row = cur.fetchone()
        return dict(row) if row else None


def count_schedule_rules(owner_user_id: int) -> int:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM schedule_rules WHERE owner_user_id = %s", (owner_user_id,))
        return cur.fetchone()[0]


def _conflict_index(rules, days: int, start: int, end: int, skip_id=None):
    """Kesishgan jadvalning tartib raqami (1 dan) yoki None."""
    import logic  # kech import: db.py logic.py'ga modul yuklanishida bog'lanib qolmasligi uchun
    for n, r in enumerate(rules, 1):
        if r["id"] != skip_id and logic.schedules_overlap(days, start, end, r["days"], r["start_min"], r["end_min"]):
            return n
    return None


def _locked_schedule_tx(owner_user_id: int, work):
    """Egasining jadvallarini advisory lock ostida o'qish+yozish (parallel so'rovlardan himoya)."""
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("BEGIN")
        try:
            cur.execute("SELECT pg_advisory_xact_lock(hashtext('schedule_rules'), (%s %% 2147483647)::int)", (owner_user_id,))
            cur.execute("SELECT * FROM schedule_rules WHERE owner_user_id = %s ORDER BY id", (owner_user_id,))
            result = work(cur, [dict(r) for r in cur.fetchall()])
            cur.execute("COMMIT")
            invalidate_schedule_cache(owner_user_id)
            return result
        except BaseException:
            try:
                cur.execute("ROLLBACK")
            except Exception:
                pass
            raise


def add_schedule_rule(owner_user_id: int, days: int, start_min: int, end_min: int, text, max_rules: int):
    """('ok', id) | ('limit', None) | ('conflict', n) — n: kesishgan jadvalning tartib raqami."""
    def work(cur, rules):
        if len(rules) >= max_rules:
            return ("limit", None)
        n = _conflict_index(rules, days, start_min, end_min)
        if n is not None:
            return ("conflict", n)
        cur.execute(
            "INSERT INTO schedule_rules (owner_user_id, days, start_min, end_min, text) VALUES (%s, %s, %s, %s, %s) RETURNING id",
            (owner_user_id, days, start_min, end_min, text),
        )
        return ("ok", cur.fetchone()["id"])
    return _locked_schedule_tx(owner_user_id, work)


_SCHEDULE_EDITABLE = ("days", "start_min", "end_min", "text", "is_enabled")


def update_schedule_rule(owner_user_id: int, rule_id: int, **fields):
    """('ok', None) | ('gone', None) | ('conflict', n). Kunlar/vaqt o'zgarsa boshqa jadvallar bilan kesishmasligi tekshiriladi."""
    bad = set(fields) - set(_SCHEDULE_EDITABLE)
    if bad or not fields:
        raise ValueError(f"bad schedule fields: {bad or 'empty'}")

    def work(cur, rules):
        cur_rule = next((r for r in rules if r["id"] == rule_id), None)
        if cur_rule is None:
            return ("gone", None)
        merged = {**cur_rule, **fields}
        if {"days", "start_min", "end_min"} & set(fields):
            n = _conflict_index(rules, merged["days"], merged["start_min"], merged["end_min"], skip_id=rule_id)
            if n is not None:
                return ("conflict", n)
        sets = ", ".join(f"{k} = %s" for k in fields)
        cur.execute(f"UPDATE schedule_rules SET {sets} WHERE id = %s AND owner_user_id = %s", (*fields.values(), rule_id, owner_user_id))
        return ("ok", None)
    return _locked_schedule_tx(owner_user_id, work)


def delete_schedule_rule(owner_user_id: int, rule_id: int) -> bool:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM schedule_rules WHERE id = %s AND owner_user_id = %s", (rule_id, owner_user_id))
        deleted = cur.rowcount > 0
    invalidate_schedule_cache(owner_user_id)
    return deleted


# --------------------------------------------------------------------------
# Analytics (soatlik hisoblagichlar)
# --------------------------------------------------------------------------
ANALYTICS_KINDS = ("incoming", "faq", "ai", "static", "sleep", "automation", "skipped")
ANALYTICS_RETENTION_DAYS = 90


# Statistika yozuvlari bir vaqtda ko'pi bilan 3 ta ulanish oladi — asosiy oqim uchun pool'da joy qoladi
_analytics_write_slots = threading.BoundedSemaphore(3)


def record_analytics(owner_user_id: int, kind: str, ts: float | None = None, n: int = 1):
    """Bir hodisani soatlik hisoblagichga qo'shadi (UPSERT). Hech qanday matn/chat ID yozilmaydi."""
    if kind not in ANALYTICS_KINDS:
        raise ValueError(f"unknown analytics kind: {kind}")
    bucket = int((ts if ts is not None else time.time()) // 3600) * 3600
    with _analytics_write_slots, get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO analytics_hourly (owner_user_id, bucket, kind, count) VALUES (%s, %s, %s, %s)
            ON CONFLICT (owner_user_id, bucket, kind) DO UPDATE SET count = analytics_hourly.count + EXCLUDED.count
            """,
            (owner_user_id, bucket, kind, n),
        )


def get_analytics_rows(owner_user_id: int, since_ts: float):
    """[(bucket, kind, count), ...] — faqat shu egasining, since_ts'dan keyingilar."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT bucket, kind, count FROM analytics_hourly WHERE owner_user_id = %s AND bucket >= %s ORDER BY bucket",
            (owner_user_id, int(since_ts // 3600) * 3600),
        )
        return [(int(b), k, int(c)) for b, k, c in cur.fetchall()]


def purge_old_analytics(max_age_days: int = ANALYTICS_RETENTION_DAYS):
    cutoff = int(time.time() - max_age_days * 86400)
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM analytics_hourly WHERE bucket < %s", (cutoff,))
        return cur.rowcount


# --------------------------------------------------------------------------
# Ism soati
# --------------------------------------------------------------------------
def get_name_clock_targets():
    """Soati yoqilgan, ulanishi faol, ismni o'zgartirish ruxsati bor va bloklanmagan egalar."""
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT s.owner_user_id, c.business_connection_id, c.can_edit_bio, s.clock_bio_notified,
                   s.name_clock_tz, s.name_clock_first, s.name_clock_last, s.name_clock_applied, s.name_clock_style,
                   CASE WHEN u.plan IS NULL OR (u.plan_expires_at IS NOT NULL AND u.plan_expires_at <= EXTRACT(EPOCH FROM now())) THEN 'free' ELSE u.plan END AS plan
            FROM settings s
            JOIN connections c ON c.owner_user_id = s.owner_user_id
            LEFT JOIN users u ON u.user_id = s.owner_user_id
            WHERE s.name_clock_enabled = TRUE
              AND c.is_enabled = TRUE AND c.can_edit_name = TRUE
              AND s.name_clock_first IS NOT NULL
              AND NOT EXISTS (SELECT 1 FROM blocked_users b WHERE b.user_id = s.owner_user_id)
            """
        )
        return [dict(r) for r in cur.fetchall()]


def set_can_edit_bio(owner_user_id: int, value: bool) -> None:
    """Telegramdan o'qilgan joriy "Edit bio" ruxsatini ulanishga yozadi (boshqa huquqlarga tegmaydi)."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("UPDATE connections SET can_edit_bio = %s WHERE owner_user_id = %s", (bool(value), owner_user_id))


def set_bio_gate_flag(owner_user_id: int, value: bool) -> bool:
    """`clock_bio_notified` belgisini ATOMIK o'zgartiradi: haqiqatan o'zgargan bo'lsa True (xabar yuborish huquqi
    shu chaqiruvga tegadi), allaqachon shunday bo'lsa False — hodisa va 5 daqiqalik tekshiruv bir vaqtda ishlasa
    ham foydalanuvchiga xabar ikki marta bormaydi."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE settings SET clock_bio_notified = %s WHERE owner_user_id = %s AND clock_bio_notified IS DISTINCT FROM %s",
            (bool(value), owner_user_id, bool(value)),
        )
        return cur.rowcount > 0


def mark_name_clock_applied(owner_user_id: int, key: str):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("UPDATE settings SET name_clock_applied = %s WHERE owner_user_id = %s", (key, owner_user_id))


def mark_name_clock_applied_bulk(pairs):
    """[(owner_user_id, key), ...] — bir so'rovda (tick ichida har foydalanuvchi uchun alohida
    so'rov yuborib, hodisa siklini sekinlashtirmaslik uchun)."""
    pairs = list(pairs)
    if not pairs:
        return
    with get_conn() as conn, conn.cursor() as cur:
        psycopg2.extras.execute_values(
            cur,
            """
            UPDATE settings AS s SET name_clock_applied = v.key
            FROM (VALUES %s) AS v(owner_user_id, key)
            WHERE s.owner_user_id = v.owner_user_id::bigint
            """,
            pairs,
        )


def get_name_clock_base(owner_user_id: int):
    """Yengil o'qish (settings qatorini yaratmaydi): yoqilgan bo'lsa, asl ism; aks holda None."""
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            "SELECT name_clock_first, name_clock_last FROM settings "
            "WHERE owner_user_id = %s AND name_clock_enabled = TRUE AND name_clock_first IS NOT NULL",
            (owner_user_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None


# --------------------------------------------------------------------------
# Ulanish uzilsa — bitta qayta urinish (Supabase/tarmoq vaqtinchalik uzishi uchun)
# --------------------------------------------------------------------------
def retry_on_disconnect(fn):
    """Faqat ULANISH xatosida (OperationalError/InterfaceError) funksiyani bir marta qayta chaqiradi.
    `_PooledConnection` buzilgan ulanishni pool'dan chiqarib tashlagani uchun, ikkinchi urinish yangi ulanish oladi.
    Faqat takrorlash xavfsiz bo'lgan (o'qish yoki idempotent yozish) funksiyalarga qo'llanadi."""
    import functools

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except (psycopg2.OperationalError, psycopg2.InterfaceError):
            logger.warning("Baza ulanishi uzildi (%s) — qayta uriniladi", fn.__name__)
            return fn(*args, **kwargs)

    return wrapper


for _name in (
    "get_name_clock_targets", "mark_name_clock_applied_bulk", "get_name_clock_base", "mark_name_clock_applied",
    "get_settings", "get_connection", "get_connection_by_business_id", "get_user_lang", "get_user_plan_info", "list_plan_subscribers",
    "get_all_bio_targets", "get_user", "get_bio_ad_candidates", "get_onboarding_step", "set_onboarding_step", "onboarding_stats", "get_enabled_faq_entries", "list_faq_entries", "list_automation_rules", "get_enabled_automation_rules", "count_automation_rules", "get_automation_deleted_sent", "get_automation_counters_since", "get_faq_entry", "count_faq_entries",
    "get_analytics_rows", "list_schedule_rules", "get_schedule_rule", "count_schedule_rules", "get_enabled_kb_entries", "list_kb_entries", "get_kb_entry", "count_kb_entries",
):
    globals()[_name] = retry_on_disconnect(globals()[_name])
del _name
