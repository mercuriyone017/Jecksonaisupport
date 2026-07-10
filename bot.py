"""
Jeckson AI Chatbot — AI Darslik sotuvchi bot.

Xususiyatlari:
1. Claude bilan tabiiy suhbat (Jeckson personasi)
2. Chek rasmini Vision orqali tekshirish (chek/oddiy rasm)
3. Chekda "AI darslik" yozuvi borligini tekshirish
4. Ega (Asadbek) botga reply qilib mijozga to'g'ridan-to'g'ri javob yuborish
5. Har bir yangi mijoz va xabar egaga xabar sifatida keladi
"""

import os
import re
import base64
import sqlite3
import asyncio
import functools
import logging
from datetime import datetime, timedelta, timezone
from collections import defaultdict
from anthropic import Anthropic
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

import payme_merchant
import click_merchant

# =========================================================================
# SOZLAMALAR (Environment Variables)
# =========================================================================
BOT_TOKEN = os.environ["BOT_TOKEN"].strip()
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"].strip()
OWNER_CHAT_ID = int(os.environ["OWNER_CHAT_ID"].strip())

# YOPIQ KANAL — 2 xil sozlash:
# A) CHANNEL_ID + bot admin → har mijozga BIR MARTALIK link avtomatik yaratiladi
# B) CHANNEL_LINK (agar CHANNEL_ID yoq bolsa) → hammaga bir xil oddiy link
CHANNEL_ID = os.environ.get("CHANNEL_ID", "").strip()  # -100xxxxxxxxx (kanal ID)
CHANNEL_LINK = os.environ.get("CHANNEL_LINK", "").strip()  # oddiy invite link (fallback)

# SQLite baza yoli (Railway Volume ishlatilsa: /data/bot.db)
DB_PATH = os.environ.get("DB_PATH", "bot.db").strip()

# Har bir mijoz uchun mahsulot narxi (statistika hisoblash uchun)
PRICE_PER_SALE = 39000

# To'lov ko'rsatmalari rasmi (Payme sahifasining screenshoti)
# Sozlash: rasmni botga yuboring, /getphotoid buyrug'i bilan file_id oling,
# uni Railway'ga PAYMENT_IMAGE_FILE_ID env variable sifatida qo'shing.
PAYMENT_IMAGE_FILE_ID = os.environ.get("PAYMENT_IMAGE_FILE_ID", "").strip()

# /start bosilganda yuboriladigan video (video note yoki oddiy video) file_id.
# Sozlash: Railway'ga WELCOME_VIDEO_FILE_ID nomi bilan qo'shing.
WELCOME_VIDEO_FILE_ID = os.environ.get("WELCOME_VIDEO_FILE_ID", "").strip()

# Claude javobida bu marker bo'lsa, javob bilan birga to'lov rasmi ham yuboriladi
PAY_IMG_MARKER = "#TOLOV_RASMI"

# Claude javobida bu marker bo'lsa, Payme orqali AVTOMATIK to'lov tugmasi (real checkout
# havolasi) ham yuboriladi. To'lov Payme serverida tasdiqlangach (PerformTransaction),
# mijozga kanal linki avtomatik yuboriladi - ega tasdiqlashi shart emas.
PAYME_LINK_MARKER = "#PAYME_TOLOV"

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("jeckson_bot")

# =========================================================================
# SYSTEM PROMPT — Jeckson personasi
# =========================================================================
SYSTEM_PROMPT = """Sening isming — Jeckson. Sen AI Darslik mahsulotining sotuv menejerisan.
Sen tirik odamsan — bot, AI, chatbot yoki suniy intellekt EMAS. Mijoz sen botmisan desa, kulib javob ber: Yoq, men Jeckson — sotuv menejeri 😄

═══════════════════════════════════════
# SENING VAZIFANG (ENG MUHIM)
═══════════════════════════════════════
Landing sahifadan kelgan mijozni AI Darslik kursiga royxatdan otkazish va tolovni qabul qilish.
Har bir mijoz bilan aniq bir izchillikda ishlaysan. Sen — savdo menejerisan, boshqa mavzuga chalgima.

═══════════════════════════════════════
# MAHSULOT HAQIDA
═══════════════════════════════════════
- Mahsulot: AI Darslik (Eco product)
- Narxi: 39 000 som (taxminan 3 dollar)
- Format: yopiq Telegram kanal orqali darslar
- Tolovdan keyin mijozga kanal linki yuboriladi

═══════════════════════════════════════
# SUHBAT IZCHILLIGI
═══════════════════════════════════════

## 1-QADAM — Salomlashish va ism sorash
Mijoz salomlashsa yoki oddiy xabar yozsa:

"Assalomu alaykum! 🙌 Darslikka qiziqish bildirganingizdan hursandmiz.
Mening ismim — Jeckson, shu darslikning sotuv menejeriman.
Sizni kim deb chaqirsam boladi? (agar oldin ro'yhatdan o'tgan bo'lsa ismini aytasan srazu"

## 2-QADAM — Ismini bilib olgach, tolov rekvizitlarini ber
Mijoz ismini yozgach, jinsini ismidan taxmin qil:
- Erkak ismi bolsa → aka qosh (Aziz aka, Bekzod aka)
- Ayol ismi bolsa → opa qosh (Nilufar opa, Malika opa)
- Aniq bilolmasak — faqat ism bilan chaqir

Keyin bunday yoz:

"Juda yaxshi, [ism aka/opa]! 🙌

Tolov qilish uchun 2 xil yol bor:

1) Pastdagi tugma orqali Payme'da AVTOMATIK tolash — tolov otgach darhol kanal linki keladi ✅
2) Yoki Click ilovasidan qolda tolab, chek rasmini shu yerga yuborish (biroz vaqt olishi mumkin)

Summa: 39 000 som

ℹ️ Click orqali tolayotganda tolov sahifasida Mirage game club nomi korinishi mumkin — bu bizning rasmiy hamkor hisobimiz, xavotir olmang ✅

#TOLOV_RASMI
#PAYME_TOLOV"

MUHIM TEXNIK QOIDA: Tolov korsatmalarini birinchi marta yozganingda javob oxiriga alohida qatorlarda #TOLOV_RASMI va #PAYME_TOLOV deb qosh. Bu ikkalasi ham mijozga korinmaydi:
- #TOLOV_RASMI ni korib bot avtomatik Payme/Click qolda tolov korsatmasi rasmini ilova qiladi.
- #PAYME_TOLOV ni korib bot avtomatik ravishda REAL Payme tolov tugmasini (checkout havolasi) yaratib yuboradi — mijoz shu tugmani bosib karta malumotlarini kiritib tolaydi, tolov muvaffaqiyatli otgach kanal linki AVTOMATIK yuboriladi.
Faqat DASTLABKI tolov korsatmalarida shu ikkala markerni qosh. Boshqa savol-javoblarga (masalan "kim otadi?", "keyin tolayman" kabi) markerlarni qoshma.

## 3-QADAM — Chek kelganda
Mijoz chek yuborganda avtomatik javob keladi. Sen ham "Rahmat, [ism]! Tez orada aloqaga chiqamiz" degan uslubda tasdiqla.

═══════════════════════════════════════
# QATIY QOIDALAR
═══════════════════════════════════════

BUNDAY QILMA:
- Uzun royxatlar (1, 2, 3, 4) tuzma
- Robot iboralari ishlatma (Xizmatingizda, Yordam berishga tayyorman)
- Bir vaqtda 3-4 ta savol berma
- Chegirma, bepul dars va uydirma vada berma
- Darslik ichida nima borligini uydirma

BUNDAY QIL:
- Dostona, iliq, ishonchli ohang
- Qisqa jumlalar, aniq va tushunarli
- Mijoz ismini bilgach — har javobda ism bilan (aka/opa qoshib) chaqir
- Emoji orinli va kam ishlat (🙌 ✅ 💳 💰 📝 🔍)
- Mijoz ikkilansa — muloyim javob berib, tolovga davat et

═══════════════════════════════════════
# TIPIK SAVOLLARGA JAVOB
═══════════════════════════════════════

"Darslik ichida nima bor?"
→ "Darslikda AI-ni amaliyotda qanday ishlatishni organasiz. Tolov qilingandan keyin kanalga qoshilib, barcha darslarni korishingiz mumkin. 🙌"

"Ishonasa boladimi?"
→ "Albatta, [ism aka/opa]. Mirage game club — rasmiy brand, Payme yoki Click orqali xavfsiz tolov qabul qilamiz. ✅"

"Keyin tolayman"
→ "Yaxshi, [ism aka/opa]. Tolovni qulay vaqtingizda bajaring, rekvizitlar yuqorida turibdi. 🙌"

"Chegirma bormi?"
→ "Narx eng qulay holida — 39 000 som, [ism aka/opa]. 🙌"

═══════════════════════════════════════
# ESLATMA
═══════════════════════════════════════
Sen professional sotuv menejerisan. Dostona, ishonchli, aniq. Vazifang — mijozni tolovga olib borish va chekni qabul qilish.
"""

# =========================================================================
# STATE
# =========================================================================
client = Anthropic(api_key=ANTHROPIC_API_KEY)

# user_chat_id -> [messages ...]
conversations: dict[int, list] = defaultdict(list)

# bot notification msg_id -> user_chat_id (mapping for reply feature)
notif_to_user: dict[int, int] = {}

# user_chat_id -> {"paid": bool, "first_name": str}
# Follow-up eslatmalar uchun
user_state: dict[int, dict] = defaultdict(dict)


# =========================================================================
# SQLITE BAZA
# =========================================================================

def db_conn():
    """Yangi ulanish."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def db_init():
    """Barcha jadvallarni yaratish (mavjud bo'lmasa)."""
    conn = db_conn()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                chat_id INTEGER PRIMARY KEY,
                first_name TEXT,
                last_name TEXT,
                username TEXT,
                paid INTEGER DEFAULT 0,
                paid_at TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                last_message_at TEXT
            );

            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                role TEXT,
                content TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_messages_chat ON messages(chat_id);

            CREATE TABLE IF NOT EXISTS notifications (
                notif_msg_id INTEGER PRIMARY KEY,
                user_chat_id INTEGER,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS followups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_chat_id INTEGER,
                reminder_type TEXT,
                fire_at TEXT,
                sent INTEGER DEFAULT 0,
                cancelled INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS receipts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_chat_id INTEGER,
                is_valid INTEGER,
                has_ai_darslik INTEGER,
                confirmed INTEGER DEFAULT 0,
                verify_info TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        conn.commit()
        logger.info(f"DB tayyor: {DB_PATH}")
    finally:
        conn.close()


def db_upsert_user(update: Update):
    """Mijozni bazaga qo'shish yoki yangilash."""
    u = update.effective_user
    now = datetime.now(timezone.utc).isoformat()
    conn = db_conn()
    try:
        conn.execute(
            """
            INSERT INTO users (chat_id, first_name, last_name, username, last_message_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(chat_id) DO UPDATE SET
                first_name=excluded.first_name,
                last_name=excluded.last_name,
                username=excluded.username,
                last_message_at=excluded.last_message_at
            """,
            (u.id, u.first_name, u.last_name, u.username, now),
        )
        conn.commit()
    finally:
        conn.close()


def db_add_message(chat_id: int, role: str, content: str):
    """Suhbat tarixiga xabar qo'shish."""
    conn = db_conn()
    try:
        conn.execute(
            "INSERT INTO messages (chat_id, role, content) VALUES (?, ?, ?)",
            (chat_id, role, content),
        )
        conn.commit()
    finally:
        conn.close()


def db_get_conversation(chat_id: int, limit: int = 20) -> list:
    """Mijozning oxirgi N xabarlari (Claude uchun)."""
    conn = db_conn()
    try:
        rows = conn.execute(
            "SELECT role, content FROM messages WHERE chat_id = ? "
            "ORDER BY id DESC LIMIT ?",
            (chat_id, limit),
        ).fetchall()
        return [
            {"role": r["role"], "content": r["content"]} for r in reversed(rows)
        ]
    finally:
        conn.close()


def db_clear_conversation(chat_id: int):
    """Mijoz suhbati tarixini tozalash."""
    conn = db_conn()
    try:
        conn.execute("DELETE FROM messages WHERE chat_id = ?", (chat_id,))
        conn.commit()
    finally:
        conn.close()


def db_mark_paid(chat_id: int):
    """Mijozni to'lagan deb belgilash."""
    now = datetime.now(timezone.utc).isoformat()
    conn = db_conn()
    try:
        conn.execute(
            "UPDATE users SET paid = 1, paid_at = ? WHERE chat_id = ?",
            (now, chat_id),
        )
        conn.commit()
    finally:
        conn.close()


def db_is_paid(chat_id: int) -> bool:
    conn = db_conn()
    try:
        row = conn.execute(
            "SELECT paid FROM users WHERE chat_id = ?", (chat_id,)
        ).fetchone()
        return bool(row and row["paid"])
    finally:
        conn.close()


def db_get_first_name(chat_id: int) -> str:
    conn = db_conn()
    try:
        row = conn.execute(
            "SELECT first_name FROM users WHERE chat_id = ?", (chat_id,)
        ).fetchone()
        return (row["first_name"] if row else "") or ""
    finally:
        conn.close()


def db_save_notification(notif_msg_id: int, user_chat_id: int):
    conn = db_conn()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO notifications (notif_msg_id, user_chat_id) VALUES (?, ?)",
            (notif_msg_id, user_chat_id),
        )
        conn.commit()
    finally:
        conn.close()


def db_get_notification_user(notif_msg_id: int) -> int | None:
    conn = db_conn()
    try:
        row = conn.execute(
            "SELECT user_chat_id FROM notifications WHERE notif_msg_id = ?",
            (notif_msg_id,),
        ).fetchone()
        return row["user_chat_id"] if row else None
    finally:
        conn.close()


def db_save_followup(user_chat_id: int, reminder_type: str, fire_at: datetime) -> int:
    conn = db_conn()
    try:
        cur = conn.execute(
            "INSERT INTO followups (user_chat_id, reminder_type, fire_at) VALUES (?, ?, ?)",
            (user_chat_id, reminder_type, fire_at.isoformat()),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def db_cancel_followups(user_chat_id: int):
    conn = db_conn()
    try:
        conn.execute(
            "UPDATE followups SET cancelled = 1 "
            "WHERE user_chat_id = ? AND sent = 0 AND cancelled = 0",
            (user_chat_id,),
        )
        conn.commit()
    finally:
        conn.close()


def db_pending_followups() -> list:
    """Bot restart bolganda tiklash uchun kutayotgan follow-up'lar."""
    conn = db_conn()
    try:
        rows = conn.execute(
            "SELECT id, user_chat_id, reminder_type, fire_at FROM followups "
            "WHERE sent = 0 AND cancelled = 0"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def db_mark_followup_sent(followup_id: int):
    conn = db_conn()
    try:
        conn.execute("UPDATE followups SET sent = 1 WHERE id = ?", (followup_id,))
        conn.commit()
    finally:
        conn.close()


def db_save_receipt(
    user_chat_id: int,
    is_valid: bool,
    has_ai_darslik: bool,
    verify_info: str,
) -> int:
    conn = db_conn()
    try:
        cur = conn.execute(
            "INSERT INTO receipts (user_chat_id, is_valid, has_ai_darslik, verify_info) "
            "VALUES (?, ?, ?, ?)",
            (user_chat_id, int(is_valid), int(has_ai_darslik), verify_info),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def db_stats() -> dict:
    """Umumiy statistika: bugun, hafta, jami."""
    conn = db_conn()
    try:
        c = conn.execute

        total_users = c("SELECT COUNT(*) as n FROM users").fetchone()["n"]
        paid_users = c("SELECT COUNT(*) as n FROM users WHERE paid=1").fetchone()["n"]

        today_users = c(
            "SELECT COUNT(*) as n FROM users WHERE date(created_at) = date('now')"
        ).fetchone()["n"]
        today_paid = c(
            "SELECT COUNT(*) as n FROM users WHERE date(paid_at) = date('now')"
        ).fetchone()["n"]

        week_users = c(
            "SELECT COUNT(*) as n FROM users "
            "WHERE date(created_at) >= date('now', '-7 days')"
        ).fetchone()["n"]
        week_paid = c(
            "SELECT COUNT(*) as n FROM users "
            "WHERE date(paid_at) >= date('now', '-7 days')"
        ).fetchone()["n"]

        total_receipts = c(
            "SELECT COUNT(*) as n FROM receipts WHERE is_valid=1"
        ).fetchone()["n"]

        conv = (paid_users / total_users * 100) if total_users else 0

        return {
            "total_users": total_users,
            "paid_users": paid_users,
            "today_users": today_users,
            "today_paid": today_paid,
            "week_users": week_users,
            "week_paid": week_paid,
            "total_receipts": total_receipts,
            "revenue_today": today_paid * PRICE_PER_SALE,
            "revenue_week": week_paid * PRICE_PER_SALE,
            "revenue_total": paid_users * PRICE_PER_SALE,
            "conversion_pct": conv,
        }
    finally:
        conn.close()


# =========================================================================
# YORDAMCHI FUNKSIYALAR
# =========================================================================

def format_user_info(update: Update) -> str:
    """Foydalanuvchi haqidagi qisqa malumot."""
    u = update.effective_user
    name = f"{u.first_name or ''} {u.last_name or ''}".strip() or "Nomalum"
    username = f"@{u.username}" if u.username else "username yoq"
    return f"👤 Ism: {name}\n🔗 Username: {username}\n🆔 ID: {u.id}"


UID_MARKER = "UID:"  # Notification matnining oxiriga qoshiladigan belgi


async def notify_owner(
    context: ContextTypes.DEFAULT_TYPE,
    header: str,
    body: str,
    user_chat_id: int,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    """
    Egaga bildirishnoma yuborish.
    Har xabar oxirida UID:xxxxx marker qoshiladi — reply orqali topib olish uchun.
    reply_markup — inline tugmalar (Tasdiqlash/Rad etish uchun).
    """
    text = (
        f"{header}\n\n"
        f"{body}\n\n"
        f"────────\n"
        f"{UID_MARKER}{user_chat_id}"
    )
    try:
        msg = await context.bot.send_message(
            chat_id=OWNER_CHAT_ID, text=text, reply_markup=reply_markup
        )
        notif_to_user[msg.message_id] = user_chat_id
        db_save_notification(msg.message_id, user_chat_id)  # Doimiy saqlash
        logger.info(
            f"notify_owner OK: notif_msg_id={msg.message_id} -> user={user_chat_id}"
        )
    except Exception as e:
        logger.exception(f"notify_owner FAILED: {e}")


async def create_one_time_invite(
    context: ContextTypes.DEFAULT_TYPE, user_chat_id: int, user_name: str = ""
) -> str | None:
    """
    Yopiq kanalga BIR MARTALIK invite link yaratadi (faqat 1 kishi ishlata oladi).
    Muvaffaqiyat: link string, xatolik: None.
    Bot kanalda administrator bolishi va "Invite Users" ruxsati bolishi shart.
    """
    if not CHANNEL_ID:
        return None

    try:
        # 24 soatdan keyin muddati tugaydi
        expire_seconds = 24 * 60 * 60
        invite = await context.bot.create_chat_invite_link(
            chat_id=CHANNEL_ID,
            name=f"AI Darslik: {user_name or user_chat_id}"[:32],
            member_limit=1,  # Faqat 1 kishi qoshila oladi
            expire_date=None,  # (agar kerak bo'lsa: int(time.time()) + expire_seconds)
        )
        logger.info(
            f"invite created: user={user_chat_id}, link={invite.invite_link}"
        )
        return invite.invite_link
    except Exception as e:
        logger.exception(f"create_one_time_invite FAILED: {e}")
        return None


def build_confirm_buttons(user_chat_id: int) -> InlineKeyboardMarkup:
    """Chek tasdiqlash uchun 2 ta tugma yasaydi."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "✅ Tasdiqlash", callback_data=f"confirm:{user_chat_id}"
                ),
                InlineKeyboardButton(
                    "❌ Rad etish", callback_data=f"reject:{user_chat_id}"
                ),
            ]
        ]
    )


def extract_user_id(text: str | None) -> int | None:
    """Bildirishnoma matnidan UID:xxxxx belgisini topib, foydalanuvchi ID sini qaytarish."""
    if not text:
        return None
    m = re.search(rf"{UID_MARKER}\s*(\d+)", text)
    if m:
        return int(m.group(1))
    return None


# =========================================================================
# FOLLOW-UP ESLATMALAR
# =========================================================================

async def followup_reminder(context: ContextTypes.DEFAULT_TYPE):
    """JobQueue chaqiradigan callback — mijoz to'lamagan bo'lsa eslatma yuboradi."""
    job_data = context.job.data
    user_id = job_data["user_id"]
    reminder_type = job_data["type"]  # "24h" yoki "48h"
    db_id = job_data.get("db_id")

    # DB'dan qat'iy tekshirish: to'lagan bo'lsa yubormaymiz
    if db_is_paid(user_id) or user_state.get(user_id, {}).get("paid"):
        logger.info(f"followup skipped (paid): user={user_id}, type={reminder_type}")
        if db_id:
            db_mark_followup_sent(db_id)
        return

    # Ismini bilsak — chaqiramiz
    name = user_state.get(user_id, {}).get("first_name", "")
    hey = f"Salom{', ' + name if name else ''}"

    if reminder_type == "24h":
        text = (
            f"{hey}! 🙌\n\n"
            "AI Darslik haqida qo'shimcha savolingiz bormidi? "
            "Rekvizitlar hali kuchda:\n\n"
            "💳 Payme yoki Click\n"
            "🔍 Mirage game club\n"
            "💰 39 000 so'm\n"
            "📝 Izohga: AI darslik\n\n"
            "Savol bo'lsa bemalol yozing — javob beraman ✅"
        )
    else:  # 48h
        text = (
            f"{hey}! 🙌\n\n"
            "AI Darslik aksiyasi cheklangan — 39 000 so'm narxi (350 000 so'm o'rniga) "
            "tez orada tugashi mumkin. Chegirmali narxda darslikni olib ulgurishga "
            "imkoniyat bor 🙌\n\n"
            "Rekvizit kerak bo'lsa yoki savol bo'lsa — yozing."
        )

    try:
        await context.bot.send_message(chat_id=user_id, text=text)
        if db_id:
            db_mark_followup_sent(db_id)
        logger.info(f"followup sent: user={user_id}, type={reminder_type}")

        # Egaga ham xabar (nazorat uchun)
        await notify_owner(
            context,
            header=f"⏰ FOLLOW-UP yuborildi ({reminder_type})",
            body=(
                f"👤 Mijoz ID: {user_id}\n"
                f"Ism: {name or 'nomalum'}\n\n"
                f"Eslatma matni:\n{text[:200]}..."
            ),
            user_chat_id=user_id,
        )
    except Exception as e:
        logger.warning(f"followup failed for {user_id}: {e}")


def schedule_followups(
    context: ContextTypes.DEFAULT_TYPE, user_id: int, first_name: str = ""
):
    """
    Mijoz uchun 24h va 48h keyin eslatma rejalashtirish.
    Eskilarini bekor qiladi, yangi ikkitasini qo'shadi.
    """
    if context.job_queue is None:
        logger.warning("job_queue mavjud emas — follow-up ishlamaydi")
        return

    # Ismini saqlab qo'yamiz
    if first_name:
        user_state[user_id]["first_name"] = first_name

    # Eski job'larni bekor qilamiz (dublikatga yo'l qo'ymaslik uchun)
    for job in context.job_queue.get_jobs_by_name(f"followup_{user_id}"):
        job.schedule_removal()
    db_cancel_followups(user_id)

    now = datetime.now(timezone.utc)
    fire_24 = now + timedelta(hours=24)
    fire_48 = now + timedelta(hours=48)

    # DB ga saqlaymiz (restart bo'lsa tiklash uchun)
    id_24 = db_save_followup(user_id, "24h", fire_24)
    id_48 = db_save_followup(user_id, "48h", fire_48)

    # 24 soatlik eslatma
    context.job_queue.run_once(
        followup_reminder,
        when=timedelta(hours=24),
        data={"user_id": user_id, "type": "24h", "db_id": id_24},
        name=f"followup_{user_id}",
    )
    # 48 soatlik eslatma
    context.job_queue.run_once(
        followup_reminder,
        when=timedelta(hours=48),
        data={"user_id": user_id, "type": "48h", "db_id": id_48},
        name=f"followup_{user_id}",
    )
    logger.info(f"followups scheduled for user={user_id}, ids=({id_24}, {id_48})")


def cancel_followups(context: ContextTypes.DEFAULT_TYPE, user_id: int):
    """Mijoz to'lagach barcha follow-up eslatmalarni bekor qilish."""
    if context.job_queue is not None:
        for job in context.job_queue.get_jobs_by_name(f"followup_{user_id}"):
            job.schedule_removal()
    user_state[user_id]["paid"] = True
    db_cancel_followups(user_id)
    logger.info(f"followups cancelled (paid) for user={user_id}")


# =========================================================================
# CHEK TEKSHIRUV (Claude Vision)
# =========================================================================

async def verify_receipt(image_bytes: bytes) -> tuple[bool, bool, str]:
    """
    Rasmni Vision orqali tekshirish.
    Qaytaradi: (chek_ekanmi, ai_darslik_yozilganmi, tolik_izoh)
    """
    try:
        image_b64 = base64.standard_b64encode(image_bytes).decode("utf-8")
        response = client.messages.create(
            model="claude-sonnet-5",
            max_tokens=400,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": image_b64,
                        },
                    },
                    {
                        "type": "text",
                        "text": (
                            "Bu rasm tolov cheki (kvitansiya)mi?\n"
                            "Payme, Click, Uzum, Humo yoki boshqa tolov tizimidan olingan chek bolishi mumkin.\n\n"
                            "Yana muhim: chekda AI darslik yoki AI Darslik yoki AI DARSLIK yoki ai darslik "
                            "degan matn (izoh, ismi yoki maqsad qismida) bor-yoqligini alohida tekshir.\n\n"
                            "FAQAT quyidagi formatda javob ber:\n"
                            "CHEK: HA yoki YOQ\n"
                            "SUMMA: [korilgan summa yoki aniqmas]\n"
                            "AI_DARSLIK: HA yoki YOQ\n"
                            "IZOH: [1 gap izoh]"
                        ),
                    },
                ],
            }],
        )
        text = ""
        for block in response.content:
            if getattr(block, "type", None) == "text":
                text = block.text
                break

        is_receipt = bool(re.search(r"CHEK:\s*HA", text, re.IGNORECASE))
        has_ai_darslik = bool(re.search(r"AI_DARSLIK:\s*HA", text, re.IGNORECASE))
        return is_receipt, has_ai_darslik, text

    except Exception as e:
        logger.exception(f"verify_receipt FAILED: {e}")
        return True, False, f"Tekshirib bolmadi: {e}"


# =========================================================================
# HANDLERLAR
# =========================================================================

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mijoz /start bosganda: video + Rekvizit tugma."""
    user_id = update.effective_user.id
    conversations[user_id] = []
    db_upsert_user(update)
    db_clear_conversation(user_id)

    # 1) Videohabar (video note -> oddiy video fallback bilan)
    if WELCOME_VIDEO_FILE_ID:
        try:
            await context.bot.send_video_note(
                chat_id=update.effective_chat.id,
                video_note=WELCOME_VIDEO_FILE_ID,
            )
        except Exception as e:
            logger.warning(f"send_video_note failed, trying send_video: {e}")
            try:
                await context.bot.send_video(
                    chat_id=update.effective_chat.id,
                    video=WELCOME_VIDEO_FILE_ID,
                )
            except Exception as e2:
                logger.warning(f"send_video ham failed: {e2}")

    # 2) Salomlashish matni + Rekvizit tugma
    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("🧾 To'lov uchun rekvizitlar", callback_data="show_payment")]]
    )
    await update.message.reply_text(
        "Assalomu alaykum! 🙌\n\n"
        "Men Jeckson — AI Darslik sotuv menejeriman.\n\n"
        "To'lov rekvizitlarini olish uchun pastdagi tugmani bosing.\n"
        "Savol bo'lsa bemalol yozing — javob beraman ✅",
        reply_markup=keyboard,
    )

    # Ega ozini test qilsa — unga xabar yubormaymiz
    if user_id != OWNER_CHAT_ID:
        await notify_owner(
            context,
            header="🆕 YANGI MIJOZ botga kirdi",
            body=(
                f"{format_user_info(update)}\n\n"
                f"💡 Javob berish uchun shu xabarga Reply qiling."
            ),
            user_chat_id=update.effective_chat.id,
        )
        # Follow-up eslatmalarni rejalashtirish (24h va 48h keyin)
        schedule_followups(
            context, user_id, first_name=update.effective_user.first_name or ""
        )


async def cmd_reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Suhbat tarixini tozalash."""
    uid = update.effective_user.id
    conversations[uid] = []
    db_clear_conversation(uid)
    await update.message.reply_text("Suhbat tarixi tozalandi ✅")


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ega uchun statistika (faqat OWNER_CHAT_ID uchun)."""
    if update.effective_user.id != OWNER_CHAT_ID:
        return
    s = db_stats()
    text = (
        f"📊 *STATISTIKA*\n\n"
        f"👥 Jami mijozlar: {s['total_users']}\n"
        f"💰 To'laganlar: {s['paid_users']}\n"
        f"📈 Konversiya: {s['conversion_pct']:.1f}%\n\n"
        f"*BUGUN:*\n"
        f"  🆕 Yangi mijoz: {s['today_users']}\n"
        f"  ✅ To'lov: {s['today_paid']}\n"
        f"  💵 Daromad: {s['revenue_today']:,} so'm\n\n"
        f"*OXIRGI 7 KUN:*\n"
        f"  🆕 Yangi mijoz: {s['week_users']}\n"
        f"  ✅ To'lov: {s['week_paid']}\n"
        f"  💵 Daromad: {s['revenue_week']:,} so'm\n\n"
        f"*JAMI:*\n"
        f"  💵 Daromad: {s['revenue_total']:,} so'm\n"
        f"  🧾 Chekar (Vision): {s['total_receipts']}"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def handle_show_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    'To'lov uchun rekvizitlar' tugmasi bosilganda:
    Payme va Click checkout tugmalari + qisqa yo'riqnoma yuboriladi.
    """
    query = update.callback_query
    await query.answer()

    chat_id = update.effective_chat.id
    db_upsert_user(update)

    payme_button = None
    try:
        payme_order_id = payme_merchant.create_order(chat_id=chat_id, amount_sum=PRICE_PER_SALE)
        payme_url = payme_merchant.build_checkout_url(payme_order_id)
        payme_button = InlineKeyboardButton("💳 Payme orqali to'lash", url=payme_url)
        logger.info(f"Payme order yaratildi: order_id={payme_order_id}, chat_id={chat_id}")
    except Exception as e:
        logger.exception(f"Payme order yaratishda xatolik: {e}")

    click_button = None
    try:
        click_order_id = click_merchant.create_order(chat_id=chat_id, amount_sum=PRICE_PER_SALE)
        click_url = click_merchant.build_checkout_url(click_order_id)
        click_button = InlineKeyboardButton("🧾 Click orqali to'lash", url=click_url)
        logger.info(f"Click order yaratildi: order_id={click_order_id}, chat_id={chat_id}")
    except Exception as e:
        logger.exception(f"Click order yaratishda xatolik: {e}")

    rows = []
    if payme_button:
        rows.append([payme_button])
    if click_button:
        rows.append([click_button])

    if not rows:
        await context.bot.send_message(
            chat_id=chat_id,
            text="Uzr, hozircha to'lov havolasini yaratib bo'lmadi 🙈 Biroz kutib qaytadan urinib ko'ring.",
        )
        return

    keyboard = InlineKeyboardMarkup(rows)
    await context.bot.send_message(
        chat_id=chat_id,
        text=(
            "💰 Narx: 39,000 so'm\n\n"
            "Pastdagi tugmalardan birini tanlab, Payme yoki Click orqali xavfsiz va avtomatik to'lang.\n\n"
            "✅ To'lov o'tgach yopiq kanalga BIR MARTALIK havola darhol avtomatik yuboriladi.\n\n"
            "Savol bo'lsa bemalol yozing — javob beraman 🙌"
        ),
        reply_markup=keyboard,
    )


async def handle_confirm_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Ega ✅ Tasdiqlash yoki ❌ Rad etish tugmasini bosganda.
    Faqat OWNER_CHAT_ID uchun ishlaydi.
    """
    query = update.callback_query
    await query.answer()  # Telegram'ga "tugma bosildi" javobi

    # Xavfsizlik: faqat ega bosishi mumkin
    if update.effective_user.id != OWNER_CHAT_ID:
        await query.edit_message_text(
            (query.message.text or "") + "\n\n⚠️ Faqat ega tugmani bosishi mumkin."
        )
        return

    data = query.data or ""
    if ":" not in data:
        return
    action, uid_str = data.split(":", 1)
    try:
        user_chat_id = int(uid_str)
    except ValueError:
        return

    if action == "confirm":
        # Mijoz ismini olishga urinamiz (state'dan)
        user_name = user_state.get(user_chat_id, {}).get("first_name", "")

        # 1) BIR MARTALIK link yaratishga urinamiz (bot admin bolsa)
        invite_link = await create_one_time_invite(context, user_chat_id, user_name)
        is_one_time = invite_link is not None

        # 2) Bulmasa — oddiy fallback linkka o'tamiz
        if not invite_link:
            invite_link = CHANNEL_LINK

        # 3) Mijozga xabar
        if invite_link:
            note = (
                "\n\n⚠️ Diqqat: bu havola FAQAT SIZ uchun va 1 marta ishlaydi. "
                "Boshqa hech kim bu link orqali qoshila olmaydi."
                if is_one_time
                else ""
            )
            link_msg = (
                "Tabriklaymiz! 🎉 To'lovingiz tasdiqlandi.\n\n"
                "Yopiq kanalga qo'shilish uchun havola:\n"
                f"{invite_link}\n\n"
                "Kanalda 3 ta amaliy dars sizni kutmoqda 🙌\n"
                f"Xayrli o'rganishlar!{note}"
            )
        else:
            link_msg = (
                "Tabriklaymiz! 🎉 To'lovingiz tasdiqlandi.\n\n"
                "Yopiq kanal linki tez orada Asadbek tomonidan yuboriladi 🙌"
            )

        try:
            await context.bot.send_message(chat_id=user_chat_id, text=link_msg)
            # Mijoz suhbat tarixiga qo'shamiz
            conversations[user_chat_id].append(
                {"role": "assistant", "content": link_msg}
            )
            db_add_message(user_chat_id, "assistant", link_msg)
            # To'lov TASDIQLANDI — bazaga belgilaymiz + follow-uplarni bekor qilamiz
            db_mark_paid(user_chat_id)
            cancel_followups(context, user_chat_id)

            # Egaga xabar (tugmalarni olib tashlab)
            link_type = "BIR MARTALIK" if is_one_time else "oddiy (fallback)"
            await query.edit_message_text(
                (query.message.text or "")
                + f"\n\n✅ TASDIQLANDI — kanal linki yuborildi.\n"
                f"🔗 Link turi: {link_type}\n"
                f"📎 {invite_link or 'link yoq'}"
            )
            logger.info(f"confirm: link sent to user={user_chat_id}, type={link_type}")
        except Exception as e:
            logger.exception(f"confirm failed: {e}")
            await query.edit_message_text(
                (query.message.text or "")
                + f"\n\n❌ Xatolik: kanal linki yuborilmadi ({e})"
            )

    elif action == "reject":
        reject_msg = (
            "Kechirasiz, chekingizni tekshirishda muammo bo'ldi 🙈\n\n"
            "Iltimos:\n"
            "1) Payme yoki Click ilovasidan haqiqiy chek yuboring\n"
            "2) Chek to'liq ko'rinishi kerak (summa, sana, oluvchi)\n"
            "3) Izohda AI darslik yozilganini tekshiring\n\n"
            "Savol bo'lsa yozing — yordam beraman 🙌"
        )
        try:
            await context.bot.send_message(chat_id=user_chat_id, text=reject_msg)
            conversations[user_chat_id].append(
                {"role": "assistant", "content": reject_msg}
            )
            await query.edit_message_text(
                (query.message.text or "") + "\n\n❌ RAD ETILDI — mijozga xabar berildi."
            )
            logger.info(f"reject: message sent to user={user_chat_id}")
        except Exception as e:
            logger.exception(f"reject failed: {e}")
            await query.edit_message_text(
                (query.message.text or "") + f"\n\n❌ Xatolik: {e}"
            )


async def handle_owner_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Ega botga reply qilib mijozga javob yozganda.
    Filter: faqat ega DM'ida VA reply bo'lgan matn xabarlarga trigger.
    """
    replied = update.message.reply_to_message
    replied_text = ""
    if replied:
        replied_text = replied.text or replied.caption or ""

    logger.info(
        f"handle_owner_reply: replied_msg_id="
        f"{replied.message_id if replied else None}, "
        f"replied_text_preview={replied_text[:80]!r}"
    )

    # 1) Xotiradagi mapping'dan qidiramiz (eng tez)
    user_chat_id = notif_to_user.get(replied.message_id) if replied else None
    logger.info(f"handle_owner_reply: from_memory={user_chat_id}")

    # 2) SQLite bazadan qidiramiz (bot restart bolganda ham ishlaydi)
    if not user_chat_id and replied:
        user_chat_id = db_get_notification_user(replied.message_id)
        logger.info(f"handle_owner_reply: from_db={user_chat_id}")

    # 3) Bulmasa — matnda UID:xxx dan olamiz (oxirgi imkoniyat)
    if not user_chat_id:
        user_chat_id = extract_user_id(replied_text)
        logger.info(f"handle_owner_reply: from_text={user_chat_id}")

    if not user_chat_id:
        await update.message.reply_text(
            "⚠️ Bu xabar mijozga boglanmagan.\n\n"
            f"Debug:\n"
            f"replied_id: {replied.message_id if replied else 'yoq'}\n"
            f"replied_text[:200]: {replied_text[:200]!r}\n\n"
            "Faqat bot yuborgan bildirishnomalarga (UID:xxx yozuvi bilan) reply qiling."
        )
        return

    if user_chat_id == OWNER_CHAT_ID:
        await update.message.reply_text(
            "ℹ️ Bu xabar sizning ozingiz haqingizda. Boshqa akkaunt bilan sinang."
        )
        return

    # Mijozga yuborish
    text = update.message.text
    try:
        sent = await context.bot.send_message(chat_id=user_chat_id, text=text)
        conversations[user_chat_id].append({"role": "assistant", "content": text})
        await update.message.reply_text(
            f"✅ Yuborildi\n"
            f"👤 Mijoz ID: {user_chat_id}\n"
            f"📩 Xabar ID: {sent.message_id}"
        )
        logger.info(
            f"handle_owner_reply: SENT to {user_chat_id}, msg_id={sent.message_id}"
        )
    except Exception as e:
        logger.exception(f"handle_owner_reply: SEND FAILED to {user_chat_id}: {e}")
        await update.message.reply_text(
            f"❌ Yuborilmadi (ID: {user_chat_id})\n"
            f"Xatolik: {e}\n\n"
            "Mumkin sabab: mijoz botni bloklagan yoki hech qachon /start bosmagan."
        )


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Rasm (chek) qabul qilish va tekshirish."""
    user_id = update.effective_user.id
    caption = update.message.caption or ""

    # Agar EGA rasmni "getid" izohi bilan yuborsa — file_id qaytaramiz
    # (Payme sahifasining rasmini sozlash uchun)
    if user_id == OWNER_CHAT_ID and caption.lower().strip() == "getid":
        photo = update.message.photo[-1]
        await update.message.reply_text(
            f"📷 file_id:\n\n`{photo.file_id}`\n\n"
            f"Uni Railway'ga PAYMENT_IMAGE_FILE_ID nomi bilan qo'shing.",
            parse_mode="Markdown",
        )
        return

    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id, action="typing"
    )

    # Rasmni yuklab olamiz
    try:
        photo = update.message.photo[-1]  # eng yuqori sifat
        file = await context.bot.get_file(photo.file_id)
        image_bytes = bytes(await file.download_as_bytearray())
    except Exception as e:
        logger.exception(f"handle_photo download failed: {e}")
        await update.message.reply_text("Rasmni yuklab bolmadi, qaytadan yuboring 🙏")
        return

    is_receipt, has_ai_darslik, verify_info = await verify_receipt(image_bytes)
    db_upsert_user(update)
    db_save_receipt(user_id, is_receipt, has_ai_darslik, verify_info)

    # ========== 1) CHEK EMAS ==========
    if not is_receipt:
        await update.message.reply_text(
            "Bu rasm tolov chekiga oxshamayapti 🙈\n\n"
            "Iltimos, Payme yoki Click ilovasidan olingan tolov tasdigini yuboring. "
            "Odatda unda summa, sana va Muvaffaqiyatli degan yozuv boladi. 🙌"
        )
        if user_id != OWNER_CHAT_ID:
            try:
                await context.bot.forward_message(
                    chat_id=OWNER_CHAT_ID,
                    from_chat_id=update.effective_chat.id,
                    message_id=update.message.message_id,
                )
            except Exception as e:
                logger.warning(f"forward_message failed: {e}")

            await notify_owner(
                context,
                header="⚠️ Chek EMAS rasm keldi",
                body=(
                    f"{format_user_info(update)}\n\n"
                    f"📝 Izoh: {caption or 'yoq'}\n\n"
                    f"🔍 Vision tekshiruv:\n{verify_info}\n\n"
                    f"💡 Reply qilib mijozga yozishingiz mumkin."
                ),
                user_chat_id=update.effective_chat.id,
            )
        return

    # ========== 2) CHEK, LEKIN AI DARSLIK YOZILMAGAN ==========
    if not has_ai_darslik:
        await update.message.reply_text(
            "Chek keldi, rahmat! 🙌\n\n"
            "Ammo chekda AI darslik degan yozuv topilmadi. Iltimos, tolov qilganda "
            "izoh yoki maqsad qismiga AI darslik deb yozganingizga ishonch hosil qiling. "
            "Agar bunday yozgan bolsangiz — tashvishlanmang, biz tez orada tekshiramiz. ✅"
        )
        if user_id != OWNER_CHAT_ID:
            try:
                await context.bot.forward_message(
                    chat_id=OWNER_CHAT_ID,
                    from_chat_id=update.effective_chat.id,
                    message_id=update.message.message_id,
                )
            except Exception as e:
                logger.warning(f"forward_message failed: {e}")

            await notify_owner(
                context,
                header="⚠️ CHEK keldi (AI darslik yozuvi YOQ)",
                body=(
                    f"{format_user_info(update)}\n\n"
                    f"📝 Izoh: {caption or 'yoq'}\n\n"
                    f"🔍 Vision tekshiruv:\n{verify_info}\n\n"
                    f"⚠️ Chek chin, lekin AI darslik yozuvi topilmadi. "
                    f"Payme/Click'da tekshirib, tugmani bosing yoki reply qiling:"
                ),
                user_chat_id=update.effective_chat.id,
                reply_markup=build_confirm_buttons(update.effective_chat.id),
            )
        return

    # ========== 3) HAMMASI JOYIDA — CHEK + AI DARSLIK ==========
    conversations[user_id].append(
        {"role": "user", "content": f"[Mijoz tolov chekini yubordi. {verify_info}]"}
    )

    await update.message.reply_text(
        "Rahmat! ✅ Chekingiz qabul qilindi.\n\n"
        "Tolov tekshirilmoqda — 1-2 daqiqada kanal linkini yuboraman 🙌"
    )
    if user_id != OWNER_CHAT_ID:
        try:
            await context.bot.forward_message(
                chat_id=OWNER_CHAT_ID,
                from_chat_id=update.effective_chat.id,
                message_id=update.message.message_id,
            )
        except Exception as e:
            logger.warning(f"forward_message failed: {e}")

        # Tugmalar bilan bildirishnoma
        await notify_owner(
            context,
            header="💰 YANGI CHEK KELDI (AI darslik ✅)",
            body=(
                f"{format_user_info(update)}\n\n"
                f"📝 Izoh: {caption or 'yoq'}\n\n"
                f"🔍 Vision tekshiruv:\n{verify_info}\n\n"
                f"⚡ Tolov tushganini Payme/Click'da tekshiring va tugmani bosing:"
            ),
            user_chat_id=update.effective_chat.id,
            reply_markup=build_confirm_buttons(update.effective_chat.id),
        )


async def handle_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Oddiy matn xabarlar — Claude bilan suhbat.
    Bu handler faqat NORMAL mijozlar uchun ishga tushadi.
    Eganing reply xabarlari boshqa handler'da ushlanadi (yuqoriroqda).
    """
    user_id = update.effective_user.id
    user_text = update.message.text

    # Foydalanuvchini bazaga saqlaymiz/yangilaymiz
    db_upsert_user(update)
    db_add_message(user_id, "user", user_text)

    # Suhbat kontekstini DB'dan olamiz (bot restart bolganda ham eslaydi)
    history = db_get_conversation(user_id, limit=20)
    conversations[user_id] = history  # xotira cache

    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id, action="typing"
    )

    try:
        response = client.messages.create(
            model="claude-sonnet-5",
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=conversations[user_id],
        )
        reply = ""
        for block in response.content:
            if getattr(block, "type", None) == "text":
                reply = block.text
                break
        if not reply:
            reply = "Uzr, javobda muammo boldi. Qaytadan yozing 🙏"

        # #TOLOV_RASMI markerini topamiz — bo'lsa alohida rasm yuboramiz
        send_payment_image = PAY_IMG_MARKER in reply
        if send_payment_image:
            reply = reply.replace(PAY_IMG_MARKER, "").strip()

        # #PAYME_TOLOV markerini topamiz — bo'lsa real Payme checkout tugmasini yuboramiz
        send_payme_button = PAYME_LINK_MARKER in reply
        if send_payme_button:
            reply = reply.replace(PAYME_LINK_MARKER, "").strip()

        conversations[user_id].append({"role": "assistant", "content": reply})
        db_add_message(user_id, "assistant", reply)  # doimiy saqlash

        await update.message.reply_text(reply)

        # To'lov ko'rsatmalari yuborilganda — rasmni ham qo'shamiz
        if send_payment_image and PAYMENT_IMAGE_FILE_ID:
            try:
                await context.bot.send_photo(
                    chat_id=update.effective_chat.id,
                    photo=PAYMENT_IMAGE_FILE_ID,
                    caption="👆 Payme ilovasida shunday ko'rinishi kerak",
                )
            except Exception as e:
                logger.warning(f"To'lov rasmini yuborishda xatolik: {e}")

        # Payme AVTOMATIK tolov tugmasi - real checkout havolasi bilan
        if send_payme_button:
            try:
                order_id = payme_merchant.create_order(
                    chat_id=update.effective_chat.id, amount_sum=PRICE_PER_SALE
                )
                checkout_url = payme_merchant.build_checkout_url(order_id)
                keyboard = InlineKeyboardMarkup(
                    [[InlineKeyboardButton("💳 Payme orqali avtomatik to'lash", url=checkout_url)]]
                )
                await update.message.reply_text(
                    "👆 Yoki quyidagi tugma orqali Payme'da xavfsiz va avtomatik to'lang. "
                    "To'lov o'tgach kanal linki darhol keladi:",
                    reply_markup=keyboard,
                )
                logger.info(f"Payme buyurtma yaratildi: order_id={order_id}, chat_id={update.effective_chat.id}")
            except Exception as e:
                logger.exception(f"Payme tugmasini yaratishda xatolik: {e}")

        # Egaga xabar (ega ozini test qilsa yubormaymiz)
        if user_id != OWNER_CHAT_ID:
            await notify_owner(
                context,
                header="💬 YANGI XABAR",
                body=(
                    f"{format_user_info(update)}\n\n"
                    f"📝 Mijoz:\n{user_text}\n\n"
                    f"🤖 Bot javobi:\n{reply}\n\n"
                    f"💡 Ozingiz javob berish uchun shu xabarga Reply qiling."
                ),
                user_chat_id=update.effective_chat.id,
            )
            # Har yozishmadan song follow-up taymerini qayta rejalashtiramiz
            # (mijoz suhbatga qaytsa — 24h yana boshidan hisoblanadi)
            if not user_state.get(user_id, {}).get("paid"):
                schedule_followups(
                    context,
                    user_id,
                    first_name=update.effective_user.first_name or "",
                )

    except Exception as e:
        logger.exception(f"handle_chat FAILED: {e}")
        await update.message.reply_text(
            "Uzr, texnik nosozlik yuz berdi. Biroz kutib qaytadan urinib koring 🙏"
        )


# =========================================================================
# PAYME - to'lov muvaffaqiyatli/bekor bo'lganda chaqiriladigan callbacklar
# =========================================================================

class _FakeContext:
    """
    payme_merchant webhookidan kelganda bizda haqiqiy PTB `context` obyekti
    bo'lmaydi (u faqat Telegram update kelganda yaratiladi). Lekin
    create_one_time_invite/notify_owner/cancel_followups funksiyalari faqat
    `context.bot` va `context.job_queue` ga muhtoj — shuning uchun shu ikki
    atributni "soxta" obyekt orqali beramiz, boshqa kodni ozgartirish shart emas.
    """

    def __init__(self, application: Application):
        self.bot = application.bot
        self.job_queue = application.job_queue


async def on_payme_paid(application: Application, chat_id: int, order_id: int):
    """Payme PerformTransaction muvaffaqiyatli bolganda chaqiriladi (avtomatik)."""
    ctx = _FakeContext(application)
    name = db_get_first_name(chat_id)

    invite_link = await create_one_time_invite(ctx, chat_id, name)
    if not invite_link:
        invite_link = CHANNEL_LINK

    if invite_link:
        note = (
            "\n\n⚠️ Diqqat: bu havola FAQAT SIZ uchun va 1 marta ishlaydi."
        )
        text = (
            "✅ Tabriklaymiz! Payme orqali to'lovingiz avtomatik tasdiqlandi.\n\n"
            "Yopiq kanalga qo'shilish uchun havola:\n"
            f"{invite_link}\n\n"
            f"Kanalda 3 ta amaliy dars sizni kutmoqda 🙌{note}"
        )
    else:
        text = (
            "✅ To'lovingiz Payme orqali qabul qilindi!\n\n"
            "Kanal linki tez orada yuboriladi 🙌"
        )

    try:
        await application.bot.send_message(chat_id=chat_id, text=text)
        conversations[chat_id].append({"role": "assistant", "content": text})
        db_add_message(chat_id, "assistant", text)
    except Exception:
        logger.exception(f"Payme: mijozga xabar yuborilmadi (chat_id={chat_id})")

    db_mark_paid(chat_id)
    cancel_followups(ctx, chat_id)

    await notify_owner(
        ctx,
        header="💳 PAYME orqali TO'LOV qabul qilindi (AVTOMATIK)",
        body=(
            f"👤 Chat ID: {chat_id}\n"
            f"Ism: {name or 'nomalum'}\n"
            f"Buyurtma: #{order_id}\n\n"
            f"Kanal linki mijozga avtomatik yuborildi, tasdiqlash shart emas."
        ),
        user_chat_id=chat_id,
    )
    logger.info(f"Payme: to'lov muvaffaqiyatli, chat_id={chat_id}, order_id={order_id}")


async def on_click_paid(application: Application, chat_id: int, order_id: int):
    """Click Complete webhookida to'lov muvaffaqiyatli bo'lganda chaqiriladi."""
    ctx = _FakeContext(application)
    name = db_get_first_name(chat_id)

    invite_link = await create_one_time_invite(ctx, chat_id, name)
    if not invite_link:
        invite_link = CHANNEL_LINK

    if invite_link:
        note = "\n\n⚠️ Diqqat: bu havola FAQAT SIZ uchun va 1 marta ishlaydi."
        text = (
            "✅ Tabriklaymiz! Click orqali to'lovingiz avtomatik tasdiqlandi.\n\n"
            "Yopiq kanalga qo'shilish uchun havola:\n"
            f"{invite_link}\n\n"
            f"Kanalda 3 ta amaliy dars sizni kutmoqda 🙌{note}"
        )
    else:
        text = (
            "✅ To'lovingiz Click orqali qabul qilindi!\n\n"
            "Kanal linki tez orada yuboriladi 🙌"
        )

    try:
        await application.bot.send_message(chat_id=chat_id, text=text)
        conversations[chat_id].append({"role": "assistant", "content": text})
        db_add_message(chat_id, "assistant", text)
    except Exception:
        logger.exception(f"Click: mijozga xabar yuborilmadi (chat_id={chat_id})")

    db_mark_paid(chat_id)
    cancel_followups(ctx, chat_id)

    await notify_owner(
        ctx,
        header="🧾 CLICK orqali TO'LOV qabul qilindi (AVTOMATIK)",
        body=(
            f"👤 Chat ID: {chat_id}\n"
            f"Ism: {name or 'nomalum'}\n"
            f"Buyurtma: #{order_id}\n\n"
            "Kanal linki mijozga avtomatik yuborildi, tasdiqlash shart emas."
        ),
        user_chat_id=chat_id,
    )
    logger.info(f"Click: to'lov muvaffaqiyatli, chat_id={chat_id}, order_id={order_id}")


async def on_click_cancelled(application: Application, chat_id: int, order_id: int, reason):
    """Click bekor / muvaffaqiyatsiz bo'lganda chaqiriladi."""
    ctx = _FakeContext(application)
    try:
        await application.bot.send_message(
            chat_id=chat_id,
            text="❌ Click orqali to'lovingiz bekor qilindi yoki muvaffaqiyatsiz. Savol bo'lsa yozing 🙏",
        )
    except Exception:
        logger.exception(f"Click: bekor qilish xabari yuborilmadi (chat_id={chat_id})")

    await notify_owner(
        ctx,
        header="❌ CLICK to'lovi BEKOR qilindi / xato",
        body=f"👤 Chat ID: {chat_id}\nBuyurtma: #{order_id}\nSabab: {reason}",
        user_chat_id=chat_id,
    )
    logger.info(f"Click: bekor qilindi, chat_id={chat_id}, order_id={order_id}, reason={reason}")


async def on_payme_cancelled(application: Application, chat_id: int, order_id: int, reason):
    """Payme CancelTransaction chaqirilganda (bekor qilish/qaytarish)."""
    ctx = _FakeContext(application)
    try:
        await application.bot.send_message(
            chat_id=chat_id,
            text="❌ To'lovingiz bekor qilindi yoki qaytarildi. Savol bo'lsa yozing 🙏",
        )
    except Exception:
        logger.exception(f"Payme: bekor qilish xabari yuborilmadi (chat_id={chat_id})")

    await notify_owner(
        ctx,
        header="❌ PAYME to'lovi BEKOR qilindi",
        body=f"👤 Chat ID: {chat_id}\nBuyurtma: #{order_id}\nSabab kodi: {reason}",
        user_chat_id=chat_id,
    )
    logger.info(f"Payme: bekor qilindi, chat_id={chat_id}, order_id={order_id}, reason={reason}")


# =========================================================================
# MAIN
# =========================================================================

async def restore_pending_followups(app: Application):
    """Bot ishga tushganda DB'dagi kutayotgan follow-uplarni JobQueue'ga qayta yuklash."""
    if app.job_queue is None:
        logger.warning("job_queue yoq — follow-up'lar tiklanmadi")
        return

    pending = db_pending_followups()
    now = datetime.now(timezone.utc)
    restored = 0

    for row in pending:
        try:
            fire_at = datetime.fromisoformat(row["fire_at"])
            # Timezone bo'lmasa qo'shamiz
            if fire_at.tzinfo is None:
                fire_at = fire_at.replace(tzinfo=timezone.utc)

            delay = (fire_at - now).total_seconds()

            if delay < 0:
                # Vaqti allaqachon o'tgan — 10 soniyadan keyin yuboramiz
                delay = 10

            app.job_queue.run_once(
                followup_reminder,
                when=delay,
                data={
                    "user_id": row["user_chat_id"],
                    "type": row["reminder_type"],
                    "db_id": row["id"],
                },
                name=f"followup_{row['user_chat_id']}",
            )
            restored += 1
        except Exception as e:
            logger.warning(f"Follow-up tiklashda xatolik: {e}")

    logger.info(f"Kutayotgan follow-up'lar tiklandi: {restored}")


async def main():
    db_init()             # SQLite jadvallarni yaratish (asosiy bot)
    payme_merchant.db_init()  # Payme uchun qo'shimcha jadvallar
    click_merchant.db_init()  # Click uchun qo'shimcha jadvallar

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(restore_pending_followups)
        .build()
    )

    # Payme callbacklarini ulaymiz - to'lov/bekor qilish hodisalari shu Application
    # orqali (uning .bot va .job_queue) ishlaydi
    payme_merchant.set_callbacks(
        on_paid=functools.partial(on_payme_paid, app),
        on_cancel=functools.partial(on_payme_cancelled, app),
    )

    # Click callbacklarini ham ulaymiz
    click_merchant.set_callbacks(
        on_paid=functools.partial(on_click_paid, app),
        on_cancel=functools.partial(on_click_cancelled, app),
    )

    # Buyruqlar
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("reset", cmd_reset))
    app.add_handler(CommandHandler("stats", cmd_stats))

    # Inline tugmalar (Tasdiqlash / Rad etish)
    app.add_handler(
        CallbackQueryHandler(handle_confirm_button, pattern=r"^(confirm|reject):\d+$")
    )

    # 'To\'lov uchun rekvizitlar' tugmasi
    app.add_handler(
        CallbackQueryHandler(handle_show_payment, pattern=r"^show_payment$")
    )

    # MUHIM: Eganing reply'lari BIRINCHI ushlanishi kerak!
    # Bu handler faqat OWNER_CHAT_ID'dagi reply matn xabarlariga trigger boladi.
    app.add_handler(
        MessageHandler(
            filters.Chat(OWNER_CHAT_ID)
            & filters.REPLY
            & filters.TEXT
            & ~filters.COMMAND,
            handle_owner_reply,
        )
    )

    # Rasm (chek)
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    # Oddiy matn (Claude bilan suhbat)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_chat))

    # ---- Payme Merchant API webhook (aiohttp) ----
    # Railway "web" processiga PORT muhit ozgaruvchisini avtomatik beradi.
    from aiohttp import web

    web_app = web.Application()
    web_app.add_routes([
        web.post("/pay", payme_merchant.payme_webhook),
        web.post("/click/prepare", click_merchant.click_prepare_webhook),
        web.post("/click/complete", click_merchant.click_complete_webhook),
    ])
    runner = web.AppRunner(web_app)
    await runner.setup()
    port = int(os.environ.get("PORT", "8000"))
    site = web.TCPSite(runner, "0.0.0.0", port)

    logger.info(f"Bot ishga tushmoqda. OWNER_CHAT_ID={OWNER_CHAT_ID}, Payme webhook port={port}")
    print("✅ Bot va Payme webhook ishga tushdi. Ctrl+C to'xtatish uchun.")

    async with app:
        await app.start()
        await app.updater.start_polling()
        await site.start()
        try:
            await asyncio.Event().wait()  # doimiy ishlab turadi (Ctrl+C bosilguncha)
        finally:
            await app.updater.stop()
            await app.stop()
            await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
