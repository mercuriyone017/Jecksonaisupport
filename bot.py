"""
Jeckson AI Chatbot — AI Darslik sotuvchi bot.

Xususiyatlari:
1. /start bosilganda dumaloq video (video_note) + "To'lov uchun rekvizitlar" tugmasi
2. To'lov FAQAT avtomatik — Click va Payme Merchant API orqali (qo'lda to'lov,
   chek/skrinshot yuborish yo'q)
3. To'lov muvaffaqiyatli o'tgach — yopiq kanalga BIR MARTALIK havola avtomatik yuboriladi
4. Savol-javoblar uchun Claude bilan tabiiy suhbat (Jeckson personasi)
5. Ega (Asadbek) botga reply qilib mijozga to'g'ridan-to'g'ri javob yuborish
6. Har bir yangi mijoz va xabar egaga xabar sifatida keladi
"""

import os
import re
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

# /start bosilganda birinchi yuboriladigan DUMALOQ VIDEO (video_note) file_id.
# Sozlash: dumaloq videoni botga (OWNER sifatida) yuboring — bot avtomatik
# file_id'ni qaytaradi (pastda handle_owner_video_note funksiyasiga qarang).
# Olingan ID'ni Railway'ga INTRO_VIDEO_NOTE_FILE_ID env variable sifatida qo'shing.
INTRO_VIDEO_NOTE_FILE_ID = os.environ.get("INTRO_VIDEO_NOTE_FILE_ID", "").strip()

# Claude javobida bu marker bo'lsa, Click va Payme AVTOMATIK to'lov tugmalari (real
# checkout havolalari) qayta yuboriladi. To'lov muvaffaqiyatli o'tgach (Merchant API
# orqali), mijozga kanal linki avtomatik yuboriladi — hech qanday qo'lda tasdiqlash,
# chek yoki skrinshot kerak emas.
PAYMENT_BUTTONS_MARKER = "#TOLOV_TUGMALARI"

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
Mijoz botga /start bosganda unga avtomatik ravishda tanishtiruv videosi va
"To'lov uchun rekvizitlar" tugmasi allaqachon yuborilgan bo'ladi — bu qadamlarni
SEN emas, kod boshqaradi. Sening vazifang — mijoz savol-javob yozganda unga
tabiiy, ishonchli va qisqa javob berish, hamda kerak bo'lganda to'lov
tugmalarini qayta yuborish.

═══════════════════════════════════════
# MAHSULOT HAQIDA
═══════════════════════════════════════
- Mahsulot: AI Darslik (Eco product)
- Narxi: 39 000 som (taxminan 3 dollar)
- Format: yopiq Telegram kanal orqali darslar
- To'lov FAQAT avtomatik: Click yoki Payme tugmasi orqali. Qo'lda o'tkazma yo'q,
  chek yoki skrinshot yuborish shart emas.
- To'lov muvaffaqiyatli o'tgach (tizim tomonidan avtomatik tasdiqlanadi), mijozga
  yopiq kanalga BIR MARTALIK havola darhol va avtomatik yuboriladi.

═══════════════════════════════════════
# SUHBAT QOIDALARI
═══════════════════════════════════════

Mijoz savol bersa — qisqa, tabiiy va ishonchli javob ber (pastdagi "TIPIK SAVOLLAR"
bo'limiga qara). Ismini bilsang, jinsini ismidan taxmin qilib aka/opa qo'shib chaqir
(Erkak ismi → aka, Ayol ismi → opa, aniq bilmasang — faqat ism bilan).

Agar mijoz "rekvizit", "qayta yubor", "qanday to'layman", "link bermadi" kabi
to'lov havolasini qayta so'rasa — javobingning OXIRIGA alohida qatorda
#TOLOV_TUGMALARI deb qo'sh. Bu marker mijozga ko'rinmaydi — buni ko'rib bot
avtomatik ravishda Click va Payme uchun REAL checkout tugmalarini qayta yuboradi
(mijoz tugmani bosib to'laydi, to'lov o'tgach kanal linki avtomatik keladi).
Markerni FAQAT shu holatda qo'sh, oddiy savol-javoblarda qo'shma.

═══════════════════════════════════════
# QATIY QOIDALAR
═══════════════════════════════════════

BUNDAY QILMA:
- Uzun royxatlar (1, 2, 3, 4) tuzma
- Robot iboralari ishlatma (Xizmatingizda, Yordam berishga tayyorman)
- Bir vaqtda 3-4 ta savol berma
- Chegirma, bepul dars va uydirma vada berma
- Darslik ichida nima borligini uydirma
- Hech qachon qo'lda to'lov yoki chek/skrinshot yuborishni taklif qilma

BUNDAY QIL:
- Dostona, iliq, ishonchli ohang
- Qisqa jumlalar, aniq va tushunarli
- Mijoz ismini bilgach — har javobda ism bilan (aka/opa qoshib) chaqir
- Emoji orinli va kam ishlat (🙌 ✅ 💳 💰)
- Mijoz ikkilansa — muloyim javob berib, tolovga davat et

═══════════════════════════════════════
# TIPIK SAVOLLARGA JAVOB
═══════════════════════════════════════

"Darslik ichida nima bor?"
→ "Darslikda AI-ni amaliyotda qanday ishlatishni organasiz. Tolov qilingandan keyin kanalga qoshilib, barcha darslarni korishingiz mumkin. 🙌"

"Ishonasa boladimi?"
→ "Albatta, [ism aka/opa]. Payme yoki Click orqali rasmiy, xavfsiz va avtomatik tolov qabul qilamiz — hech qanday qo'lda tolov yo'q. ✅"

"Keyin tolayman"
→ "Yaxshi, [ism aka/opa]. Qulay vaqtingizda tugmalar orqali tolashingiz mumkin. 🙌"

"Chegirma bormi?"
→ "Narx eng qulay holida — 39 000 som, [ism aka/opa]. 🙌"

"Savolim bor" / "yordam kerak"
→ "Albatta, [ism aka/opa]! Savolingizni yozing, men shu yerdaman va yordam beraman 🙌"

═══════════════════════════════════════
# ESLATMA
═══════════════════════════════════════
Sen professional sotuv menejerisan. Dostona, ishonchli, aniq. Vazifang — mijozning savollariga javob berib, kerak bo'lsa to'lov tugmalarini qayta taqdim etish.
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

        conv = (paid_users / total_users * 100) if total_users else 0

        return {
            "total_users": total_users,
            "paid_users": paid_users,
            "today_users": today_users,
            "today_paid": today_paid,
            "week_users": week_users,
            "week_paid": week_paid,
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
# TO'LOV TUGMALARI (Click + Payme avtomatik checkout)
# =========================================================================

async def build_payment_keyboard(chat_id: int) -> InlineKeyboardMarkup | None:
    """
    Payme va Click uchun REAL checkout buyurtmalari yaratadi va ikkalasiga
    ham havola tugmasini qaytaradi. Ikkisi ham ishlamasa None qaytaradi.
    """
    buttons = []

    try:
        payme_order_id = payme_merchant.create_order(
            chat_id=chat_id, amount_sum=PRICE_PER_SALE
        )
        payme_url = payme_merchant.build_checkout_url(payme_order_id)
        buttons.append([InlineKeyboardButton("💳 Payme orqali to'lash", url=payme_url)])
    except Exception as e:
        logger.exception(f"Payme checkout yaratilmadi (chat_id={chat_id}): {e}")

    try:
        click_order_id = click_merchant.create_order(
            chat_id=chat_id, amount_sum=PRICE_PER_SALE
        )
        click_url = click_merchant.build_checkout_url(click_order_id)
        buttons.append([InlineKeyboardButton("💳 Click orqali to'lash", url=click_url)])
    except Exception as e:
        logger.exception(f"Click checkout yaratilmadi (chat_id={chat_id}): {e}")

    if not buttons:
        return None
    return InlineKeyboardMarkup(buttons)


PAYMENT_DETAILS_TEXT = (
    "💰 Narx: {price:,} so'm\n\n"
    "Pastdagi tugmalardan birini tanlab, Click yoki Payme orqali xavfsiz va "
    "avtomatik to'lang.\n\n"
    "✅ To'lov o'tgach yopiq kanalga BIR MARTALIK havola darhol avtomatik yuboriladi.\n"
    "❌ Qo'lda o'tkazma yo'q, chek yoki skrinshot yuborish shart emas.\n\n"
    "Savol bo'lsa bemalol yozing — javob beraman 🙌"
).format(price=PRICE_PER_SALE)


# =========================================================================
# HANDLERLAR
# =========================================================================

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mijoz /start bosganda: 1) dumaloq video, 2) 'To'lov uchun rekvizitlar' tugmasi."""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    conversations[user_id] = []
    db_upsert_user(update)
    db_clear_conversation(user_id)

    # 1) Dumaloq tanishtiruv videosi (agar sozlangan bolsa)
    if INTRO_VIDEO_NOTE_FILE_ID:
        try:
            await context.bot.send_video_note(
                chat_id=chat_id, video_note=INTRO_VIDEO_NOTE_FILE_ID
            )
        except Exception as e:
            logger.warning(f"Intro video_note yuborilmadi: {e}")
    else:
        logger.warning(
            "INTRO_VIDEO_NOTE_FILE_ID sozlanmagan — video yuborilmadi. "
            "Dumaloq videoni ega sifatida botga yuborib file_id oling."
        )

    # 2) Salomlashish + rekvizitlar tugmasi
    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("💳 To'lov uchun rekvizitlar", callback_data="show_payment")]]
    )
    await update.message.reply_text(
        "Assalomu alaykum! 🙌\n\n"
        "Men Jeckson — AI Darslik sotuv menejeriman.\n\n"
        "To'lov rekvizitlarini olish uchun pastdagi tugmani bosing. "
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
        f"  💵 Daromad: {s['revenue_total']:,} so'm"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def handle_show_payment_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Mijoz "💳 To'lov uchun rekvizitlar" tugmasini bosganda.
    Click va Payme uchun REAL avtomatik checkout tugmalarini yuboradi — qo'lda
    to'lov yoki chek/skrinshot talab qilinmaydi.
    """
    query = update.callback_query
    await query.answer()

    chat_id = update.effective_chat.id
    keyboard = await build_payment_keyboard(chat_id)

    if keyboard is None:
        text = (
            PAYMENT_DETAILS_TEXT
            + "\n\n⚠️ Hozircha to'lov havolasi yaratilmadi, birozdan so'ng "
            "qayta urinib ko'ring yoki shu yerga yozing."
        )
        await query.message.reply_text(text)
        return

    await query.message.reply_text(PAYMENT_DETAILS_TEXT, reply_markup=keyboard)
    logger.info(f"show_payment: rekvizitlar yuborildi, chat_id={chat_id}")


async def handle_owner_video_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Ega dumaloq video (video_note) yuborganda — file_id'ni qaytaradi.
    Buni INTRO_VIDEO_NOTE_FILE_ID environment variable sifatida qo'shing.
    """
    vn = update.message.video_note
    if not vn:
        return
    await update.message.reply_text(
        f"🎥 video_note file_id:\n\n`{vn.file_id}`\n\n"
        f"Uni Railway'ga INTRO_VIDEO_NOTE_FILE_ID nomi bilan qo'shing.",
        parse_mode="Markdown",
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

        # #TOLOV_TUGMALARI markerini topamiz — bo'lsa Click+Payme tugmalarini qayta yuboramiz
        resend_payment_buttons = PAYMENT_BUTTONS_MARKER in reply
        if resend_payment_buttons:
            reply = reply.replace(PAYMENT_BUTTONS_MARKER, "").strip()

        conversations[user_id].append({"role": "assistant", "content": reply})
        db_add_message(user_id, "assistant", reply)  # doimiy saqlash

        await update.message.reply_text(reply)

        # Click va Payme AVTOMATIK to'lov tugmalari - real checkout havolalari bilan
        if resend_payment_buttons:
            keyboard = await build_payment_keyboard(update.effective_chat.id)
            if keyboard:
                await update.message.reply_text(
                    PAYMENT_DETAILS_TEXT, reply_markup=keyboard
                )
                logger.info(
                    f"To'lov tugmalari qayta yuborildi: chat_id={update.effective_chat.id}"
                )

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
# CLICK - to'lov muvaffaqiyatli/bekor bo'lganda chaqiriladigan callbacklar
# =========================================================================

async def on_click_paid(application: Application, chat_id: int, order_id: int):
    """Click Complete (action=1) muvaffaqiyatli bolganda chaqiriladi (avtomatik)."""
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
        header="💳 CLICK orqali TO'LOV qabul qilindi (AVTOMATIK)",
        body=(
            f"👤 Chat ID: {chat_id}\n"
            f"Ism: {name or 'nomalum'}\n"
            f"Buyurtma: #{order_id}\n\n"
            f"Kanal linki mijozga avtomatik yuborildi, tasdiqlash shart emas."
        ),
        user_chat_id=chat_id,
    )
    logger.info(f"Click: to'lov muvaffaqiyatli, chat_id={chat_id}, order_id={order_id}")


async def on_click_cancelled(application: Application, chat_id: int, order_id: int, reason):
    """Click tomonidan tranzaksiya bekor qilinganda (error < 0)."""
    ctx = _FakeContext(application)
    try:
        await application.bot.send_message(
            chat_id=chat_id,
            text="❌ To'lovingiz bekor qilindi yoki qaytarildi. Savol bo'lsa yozing 🙏",
        )
    except Exception:
        logger.exception(f"Click: bekor qilish xabari yuborilmadi (chat_id={chat_id})")

    await notify_owner(
        ctx,
        header="❌ CLICK to'lovi BEKOR qilindi",
        body=f"👤 Chat ID: {chat_id}\nBuyurtma: #{order_id}\nSabab kodi: {reason}",
        user_chat_id=chat_id,
    )
    logger.info(f"Click: bekor qilindi, chat_id={chat_id}, order_id={order_id}, reason={reason}")


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
    db_init()                 # SQLite jadvallarni yaratish (asosiy bot)
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

    # Click callbacklarini ulaymiz (xuddi Payme kabi)
    click_merchant.set_callbacks(
        on_paid=functools.partial(on_click_paid, app),
        on_cancel=functools.partial(on_click_cancelled, app),
    )

    # Buyruqlar
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("reset", cmd_reset))
    app.add_handler(CommandHandler("stats", cmd_stats))

    # "To'lov uchun rekvizitlar" tugmasi
    app.add_handler(
        CallbackQueryHandler(handle_show_payment_button, pattern=r"^show_payment$")
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

    # Ega dumaloq video yuborsa — file_id qaytaramiz (INTRO_VIDEO_NOTE_FILE_ID sozlash uchun)
    app.add_handler(
        MessageHandler(filters.VIDEO_NOTE & filters.Chat(OWNER_CHAT_ID), handle_owner_video_note)
    )

    # Oddiy matn (Claude bilan suhbat — savol-javoblar uchun)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_chat))

    # ---- Payme va Click Merchant API webhooklari (aiohttp) ----
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

    logger.info(f"Bot ishga tushmoqda. OWNER_CHAT_ID={OWNER_CHAT_ID}, webhook port={port}")
    print("✅ Bot, Payme va Click webhooklari ishga tushdi. Ctrl+C to'xtatish uchun.")

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
