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
import logging
from datetime import timedelta
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
Sizni kim deb chaqirsam boladi?"

## 2-QADAM — Ismini bilib olgach, tolov rekvizitlarini ber
Mijoz ismini yozgach, jinsini ismidan taxmin qil:
- Erkak ismi bolsa → aka qosh (Aziz aka, Bekzod aka)
- Ayol ismi bolsa → opa qosh (Nilufar opa, Malika opa)
- Aniq bilolmasak — faqat ism bilan chaqir

Keyin bunday yoz:

"Juda yaxshi, [ism aka/opa]! 🙌

Tolov qilish uchun rekvizitlar:

💳 Payme yoki Click ilovasini oching
🔍 Qidiruvda: Mirage game club deb qidiring
💰 Summa: 39 000 som
📝 Izohga (yoki user nomiga): AI darslik deb yozishni unutmang!

Tolovni bajargach, chek rasmini shu yerga yuboring — tekshirib, darslar kanalining linkini beraman."

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

    state = user_state.get(user_id, {})

    # Agar mijoz allaqachon to'lagan bo'lsa — eslatma kerak emas
    if state.get("paid"):
        logger.info(f"followup skipped (paid): user={user_id}, type={reminder_type}")
        return

    # Ismini bilsak — chaqiramiz
    name = state.get("first_name", "")
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

    # 24 soatlik eslatma
    context.job_queue.run_once(
        followup_reminder,
        when=timedelta(hours=24),
        data={"user_id": user_id, "type": "24h"},
        name=f"followup_{user_id}",
    )
    # 48 soatlik eslatma
    context.job_queue.run_once(
        followup_reminder,
        when=timedelta(hours=48),
        data={"user_id": user_id, "type": "48h"},
        name=f"followup_{user_id}",
    )
    logger.info(f"followups scheduled for user={user_id}")


def cancel_followups(context: ContextTypes.DEFAULT_TYPE, user_id: int):
    """Mijoz to'lagach barcha follow-up eslatmalarni bekor qilish."""
    if context.job_queue is None:
        return
    for job in context.job_queue.get_jobs_by_name(f"followup_{user_id}"):
        job.schedule_removal()
    user_state[user_id]["paid"] = True
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
    """Mijoz /start bosganda."""
    user_id = update.effective_user.id
    conversations[user_id] = []

    await update.message.reply_text(
        "Assalomu alaykum! 🙌\n\n"
        "Darslikka qiziqish bildirganingizdan hursandmiz.\n\n"
        "Mening ismim — Jeckson, shu darslikning sotuv menejeriman.\n\n"
        "Sizni kim deb chaqirsam boladi?"
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
    conversations[update.effective_user.id] = []
    await update.message.reply_text("Suhbat tarixi tozalandi ✅")


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
            # To'lov tasdiqlandi — barcha follow-uplarni bekor qilamiz
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

    # 1) Xotiradagi mapping'dan qidiramiz
    user_chat_id = notif_to_user.get(replied.message_id) if replied else None
    logger.info(f"handle_owner_reply: from_memory={user_chat_id}")

    # 2) Bulmasa — matnda UID:xxx dan olamiz
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

    conversations[user_id].append({"role": "user", "content": user_text})
    conversations[user_id] = conversations[user_id][-20:]

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

        conversations[user_id].append({"role": "assistant", "content": reply})
        await update.message.reply_text(reply)

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
# MAIN
# =========================================================================

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    # Buyruqlar
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("reset", cmd_reset))

    # Inline tugmalar (Tasdiqlash / Rad etish)
    app.add_handler(
        CallbackQueryHandler(handle_confirm_button, pattern=r"^(confirm|reject):\d+$")
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

    logger.info(f"Bot ishga tushdi. OWNER_CHAT_ID={OWNER_CHAT_ID}")
    print("✅ Bot ishga tushdi. Ctrl+C to'xtatish uchun.")
    app.run_polling()


if __name__ == "__main__":
    main()
