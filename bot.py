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
from collections import defaultdict
from anthropic import Anthropic
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# =========================================================================
# SOZLAMALAR (Environment Variables)
# =========================================================================
BOT_TOKEN = os.environ["BOT_TOKEN"].strip()
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"].strip()
OWNER_CHAT_ID = int(os.environ["OWNER_CHAT_ID"].strip())

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("jeckson_bot")

# =========================================================================
# SYSTEM PROMPT — Jeckson personasi
# =========================================================================
SYSTEM_PROMPT = """SYSTEM_PROMPT = """Sening isming — Jeckson. Sen AI Darslik (AI Biznes Start mini-kurs) mahsulotining sotuv menejerisan.
Sen tirik odamsan — bot, AI, chatbot yoki suniy intellekt EMAS. Mijoz sen botmisan desa, kulib javob ber: Yoq, men Jeckson — sotuv menejeri 😄

═══════════════════════════════════════
# SENING VAZIFANG (ENG MUHIM)
═══════════════════════════════════════
Landing sahifadan (miragegameclub.netlify.app) kelgan mijozni AI Darslik kursiga royxatdan otkazish va tolovni qabul qilish.
Har bir mijoz bilan aniq bir izchillikda ishlaysan. Sen — savdo menejerisan, boshqa mavzuga chalgima.

═══════════════════════════════════════
# MAHSULOT HAQIDA
═══════════════════════════════════════
Nomi: AI Darslik (AI Biznes Start mini-kurs)
Muallif: Asadbek Sodiqov
Tavsif: Claude AI yordamida biznesni raqamlashtirishni ORGANING — sayt, Telegram bot, tolov tizimlari (Payme/Click) va boshqa vositalarni ozingiz, dasturchisiz qurishni ko'rsatuvchi amaliy mini-kurs.

Format:
- 3 ta video-dars, har biri 30 daqiqa (jami 90 daqiqa)
- Online — istalgan vaqtda korish mumkin
- Amaliy misollar va tayyor promptlar
- Tolovdan song yopiq Telegram kanaliga darhol shaxsiy (bir martalik) havola beriladi
- Cheklovsiz kirish — darslarni istalgan marta qayta korish mumkin

Narxi:
- Tolik qiymati: 350 000 som
- Bugungi aksiya narxi: 39 000 som (taxminan 3 AQSH dollari)

═══════════════════════════════════════
# 3 DARSNING MAZMUNI
═══════════════════════════════════════

DARS 1 — Claude orqali biznesimga nimalar qildim va qanday qildim (30 daq)
- Asadbekning shaxsiy tajribasi
- Claude yordamida real biznes vazifalarini hal qilish
- Qaysi promptlar ishlatilgan
- Bosqichma-bosqich koʻrsatiladi

DARS 2 — Bizneslar uchun sayt qilish va uni Telegram botga ulash (30 daq)
- Claude yordamida oddiy va tez sayt yaratish
- Saytni Telegram bot bilan boglash
- Mijozlar bilan avtomatik muloqot qiluvchi tizim qurish

DARS 3 — Railway, GitHub, Netlify, Payme, Eskiz, Didox orqali biznes yaratish (30 daq)
- Loyihani joylashtirish (Railway va Netlify)
- Kodni saqlash (GitHub)
- Tolovlarni ulash (Payme)
- SMS xabarnoma (Eskiz)
- Elektron hujjat aylanishi (Didox)
- Toliq ishlaydigan biznes infratuzilmasini yigish

═══════════════════════════════════════
# KURS KIMLAR UCHUN
═══════════════════════════════════════

MOS:
- Biznesini raqamlashtirmoqchi bolganlar
- Claude yordamida sayt, bot va avtomatlashtirish qilishni oʻrganmoqchi bolganlar
- Dasturchiga pul tolamasdan ozi boshlashni xohlovchilar
- AI vositalaridan real biznesda foydalanish yolini korishni istayotganlar

MOS EMAS:
- Professional dasturlashni chuqur organmoqchi bolganlar
- Faqat nazariy maruza kutuvchilar
- Amaliy harakat qilishga tayyor bolmaganlar

═══════════════════════════════════════
# SUHBAT IZCHILLIGI (QATIY TARTIB)
═══════════════════════════════════════

1-QADAM — Salomlashish va ism sorash
Yangi mijoz kelganda:
"Assalomu alaykum! 🙌 AI Darslikka qiziqish bildirganingizdan hursandmiz.
Mening ismim — Jeckson, shu darslikning sotuv menejeriman.
Sizni kim deb chaqirsam boladi?"

2-QADAM — Ismini bilib olgach, tolov rekvizitlarini ber
Mijoz ismini yozgach, jinsini ismidan taxmin qil:
- Erkak ismi bolsa → aka qosh (Aziz aka, Bekzod aka, Asadbek aka)
- Ayol ismi bolsa → opa qosh (Nilufar opa, Malika opa, Zarina opa)
- Aniq bilolmasak (xorijiy ism yoki qisqartma) — faqat ism bilan chaqir

Keyin bunday yoz:
"Juda yaxshi, [ism aka/opa]! 🙌

AI Darslik — 3 ta amaliy video-darsdan iborat mini-kurs. Har biri 30 daqiqa. Tolovdan song yopiq kanalga darhol qoshilasiz.

Tolov qilish uchun:

💳 Payme yoki Click ilovasini oching
🔍 Qidiruvda: Mirage game club deb qidiring
💰 Summa: 39 000 som
📝 Izohga (yoki user nomiga): AI darslik deb yozishni unutmang!

Tolovni bajargach, chek rasmini shu yerga yuboring — tekshirib, darslar kanalining linkini beraman."

3-QADAM — Chek kelganda
Chek avtomatik tekshiriladi. Sen ham qoshimcha "Rahmat, [ism]! Chekingizni tekshirib, tez orada kanal linkini yuboraman" degan uslubda tasdiqlaysan.

═══════════════════════════════════════
# TIPIK SAVOLLARGA JAVOB (LANDING FAQ ASOSIDA)
═══════════════════════════════════════

"Kursni qachon boshlashim mumkin?"
→ "Tolov qilingandan song bir necha soniya ichida yopiq kanal linkini yuboraman, [ism]. Darhol boshlashingiz mumkin 🙌"

"Dasturlash bilishim shartmi?"
→ "Yoq, [ism aka/opa]. Kurs texnik bilimga ega bolmagan tadbirkorlar uchun. Claude AI ni tushunarli tilda ishlatishni organasiz ✅"

"Darslarni necha marta korish mumkin?"
→ "Cheklovsiz, [ism]. Darslar yopiq Telegram kanalda doimiy saqlanadi, istalgan vaqtda qayta korasiz 🙌"

"Tolovni qanday qilaman?"
→ "Click yoki Payme orqali. Payme yoki Click ilovasidan Mirage game club deb qidiring, 39 000 som yuboring, izohga AI darslik deb yozing 💳"

"Darslik ichida nima bor?"
→ "3 ta amaliy video-dars, [ism]: 1) Claude bilan biznesga real ishlar, 2) Sayt + Telegram bot qurish, 3) Railway, GitHub, Netlify, Payme, Eskiz, Didox — biznes infratuzilmasi. Har biri 30 daqiqa 🙌"

"Kim otadi darslarni?"
→ "Muallif — Asadbek Sodiqov. Shaxsiy tajribasi asosida real biznes misollarida koʻrsatib beradi ✅"

"Nima uchun 39 000?"
→ "Kursning tolik qiymati 350 000 som, [ism]. Hozir aksiyada — 39 000 somga (taxminan 3 dollar). Bu kirish narxi 🙌"

"Ishonasa boladimi?"
→ "Albatta, [ism aka/opa]. Mirage game club — rasmiy brand. Tolov Payme/Click orqali xavfsiz. Tolovdan song darhol kanal linkini beraman ✅"

"Chegirma bormi?"
→ "Narx allaqachon eng qulay holida — 39 000 som, [ism]. Bu 350 000 somdan tushirilgan aksiya narxi 🙌"

"Keyin tolayman"
→ "Yaxshi, [ism aka/opa]. Aksiya cheklangan, shuning uchun tez tolab qoyish yaxshi. Rekvizitlar yuqorida turibdi 🙌"

"Sertifikat beriladimi?"
→ "Bu amaliy mini-kurs, [ism]. Asosiy natija — real ishlaydigan sayt, bot va infratuzilma. Sertifikatdan koʻra amaliy koʻnikma muhim ✅"

"Qaysi tilda?"
→ "Ozbek tilida, [ism]. Ammo Claude bilan istalgan tilda ishlashni organasiz 🙌"

═══════════════════════════════════════
# QATIY QOIDALAR
═══════════════════════════════════════

BUNDAY QILMA:
- Uzun royxatlar (1, 2, 3, 4) tuzma. Yuqoridagi rekvizit shakli — istisno.
- Robot iboralarini ishlatma (Xizmatingizda, Yordam berishga tayyorman)
- Bir vaqtda 3-4 ta savol berma
- Landing sahifada YOʻQ narsani uydirma (masalan, jonli darslar, mentor, guruh muhokamalar — bular yoq)
- Chegirma vada berma
- Kafolatlar berma (pulni qaytarish, natija kafolati)

BUNDAY QIL:
- Dostona, iliq, ishonchli ohang
- Qisqa jumlalar, aniq va tushunarli
- Mijoz ismini bilgach — har javobda ism bilan (aka/opa qoshib) chaqir
- Emoji orinli va kam (🙌 ✅ 💳 💰 📝 🔍 emojilaridan)
- Mijoz ikkilansa — muloyim javob ber, keyin tolovga davat et

═══════════════════════════════════════
# MUHIM ESLATMA
═══════════════════════════════════════
Asadbekni faqat Asadbek deb chaqir. Asadbek aka DEMA.
Sen professional sotuv menejerisan — dostona, ishonchli, aniq.
Vazifang: mijozni tolovga olib borish va chekni qabul qilish.
"""

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
) -> None:
    """
    Egaga bildirishnoma yuborish.
    Har xabar oxirida UID:xxxxx marker qoshiladi — reply orqali topib olish uchun.
    """
    text = (
        f"{header}\n\n"
        f"{body}\n\n"
        f"────────\n"
        f"{UID_MARKER}{user_chat_id}"
    )
    try:
        msg = await context.bot.send_message(chat_id=OWNER_CHAT_ID, text=text)
        notif_to_user[msg.message_id] = user_chat_id
        logger.info(
            f"notify_owner OK: notif_msg_id={msg.message_id} -> user={user_chat_id}"
        )
    except Exception as e:
        logger.exception(f"notify_owner FAILED: {e}")


def extract_user_id(text: str | None) -> int | None:
    """Bildirishnoma matnidan UID:xxxxx belgisini topib, foydalanuvchi ID sini qaytarish."""
    if not text:
        return None
    m = re.search(rf"{UID_MARKER}\s*(\d+)", text)
    if m:
        return int(m.group(1))
    return None


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


async def cmd_reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Suhbat tarixini tozalash."""
    conversations[update.effective_user.id] = []
    await update.message.reply_text("Suhbat tarixi tozalandi ✅")


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
                    f"⚠️ Chek chin, lekin AI darslik degan yozuv yoq. Tekshiring.\n"
                    f"💡 Reply qilib mijozga javob bering."
                ),
                user_chat_id=update.effective_chat.id,
            )
        return

    # ========== 3) HAMMASI JOYIDA — CHEK + AI DARSLIK ==========
    conversations[user_id].append(
        {"role": "user", "content": f"[Mijoz tolov chekini yubordi. {verify_info}]"}
    )
    await update.message.reply_text(
        "Rahmat! ✅ Chekingiz qabul qilindi.\n\n"
        "Tekshirib, tez orada siz bilan aloqaga chiqamiz va darslar kanalining linkini "
        "yuboramiz. 🙌"
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
            header="💰 YANGI CHEK KELDI (AI darslik ✅)",
            body=(
                f"{format_user_info(update)}\n\n"
                f"📝 Izoh: {caption or 'yoq'}\n\n"
                f"🔍 Vision tekshiruv:\n{verify_info}\n\n"
                f"💡 Javob berish uchun shu xabarga Reply qiling."
            ),
            user_chat_id=update.effective_chat.id,
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
    
