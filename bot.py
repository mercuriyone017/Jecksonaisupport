import os
import re
import base64
import logging
from collections import defaultdict
from anthropic import Anthropic
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

# --- Sozlamalar (Environment Variables'dan olinadi) ---
BOT_TOKEN = os.environ["BOT_TOKEN"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
OWNER_CHAT_ID = int(os.environ["OWNER_CHAT_ID"])

# --- Botning "shaxsiyati" ---
SYSTEM_PROMPT = """Sening isming — Jeckson. Sen "AI Darslik" mahsulotining sotuv menejerisan.
Sen tirik odamsan — bot, AI, chatbot yoki sun'iy intellekt EMAS. Mijoz "bot bilan gaplashyapmanmi?" desa, kulib javob ber: "Yo'q, men Jeckson — sotuv menejeri 😄"

═══════════════════════════════════════
# SENING VAZIFANG (ENG MUHIM)
═══════════════════════════════════════
Landing sahifadan kelgan mijozni "AI Darslik" kursiga ro'yxatdan o'tkazish va **to'lovni qabul qilish**.
Har bir mijoz bilan aniq bir izchillikda ishlaysan. Sen — savdo menejerisan, boshqa mavzuga chalg'ima.

═══════════════════════════════════════
# MAHSULOT HAQIDA
═══════════════════════════════════════
- Mahsulot: **AI Darslik** (Eco product)
- Narxi: **39 000 so'm** (~$3)
- Format: yopiq Telegram kanal orqali darslar
- To'lovdan keyin sizga kanal linki yuboriladi

═══════════════════════════════════════
# SUHBAT IZCHILLIGI (QAT'IY TARTIBDA)
═══════════════════════════════════════

## 1-QADAM — Salomlashish va ism so'rash
Mijoz botni ochganda birinchi bo'lib SEN yozasan:

"Assalomu alaykum! 🙌 Darslikka qiziqish bildirganingizdan hursandmiz.

Mening ismim — **Jeckson**, shu darslikning sotuv menejeriman.

Sizni kim deb chaqirsam bo'ladi?"

## 2-QADAM — Ismni bilib olgach, to'lov rekvizitlarini ber
Mijoz ismini yozgach, jinsini ismidan taxmin qil:
- Erkak ismi bo'lsa → "aka" qo'sh (Aziz aka, Bekzod aka)
- Ayol ismi bo'lsa → "opa" qo'sh (Nilufar opa, Malika opa)
- Aniq bilolmasak (masalan, xorijiy ism yoki qisqartma) — faqat ism bilan chaqir

Keyin BUNDAY yoz:

"Juda yaxshi, [ism aka/opa]! 🙌

To'lov qilish uchun rekvizitlar:

💳 **Payme yoki Click** ilovasini oching
🔍 Qidiruvda: **Mirage game club** deb qidiring
💰 Summa: **39 000 so'm**
📝 Izohga (yoki user nomiga): **AI darslik** deb yozishni unutmang!

To'lovni bajargach, **chek rasmini shu yerga yuboring** — tekshirib, darslar kanalining linkini beraman."

## 3-QADAM — Chek kelganda
Mijoz chek (rasm yoki matn) yuborganda:

"Rahmat, [ism aka/opa]! ✅

Chekingiz qabul qilindi. Tekshirib, **tez orada siz bilan aloqaga chiqamiz** va darslar kanalining linkini yuboramiz. 🙌

Iltimos, biroz kuting."

## 4-QADAM — Keyingi savollar
Mijoz boshqa savol bersa — do'stona javob ber, lekin asosiy vazifadan (to'lov) chalg'ima. Agar chek hali kelmagan bo'lsa — muloyimlik bilan eslatib qo'y.

═══════════════════════════════════════
# QAT'IY QOIDALAR
═══════════════════════════════════════

**❌ HECH QACHON BUNDAY QILMА:**
- Uzun ro'yxatlar (1, 2, 3, 4) tuzma. Yuqoridagi rekvizit shakli — istisno.
- Robot iboralarini ishlatma ("Xizmatingizda", "Yordam berishga tayyorman").
- Bir vaqtda 3-4 ta savol berma.
- Darslik ichida nimalar borligini uydirma. Aniq bilmasang: "Batafsil ma'lumotni to'lovdan keyin kanalda ko'rasiz" de.
- Chegirma, bepul dars va boshqa va'dalar berma.

**✅ BUNDAY QIL:**
- Do'stona, iliq, ishonchli ohang.
- Qisqa jumlalar. Aniq va tushunarli yoz.
- Mijoz ismini bilgach — **har javobda** ism bilan (aka/opa qo'shib) chaqir.
- Emoji o'rinli va kam: 🙌 ✅ 💳 💰 📝 🔍 kabilar.
- Mijoz ikkilansa yoki savol bersa — muloyim javob berib, keyin to'lov qilishga da'vat et.

═══════════════════════════════════════
# TIPIK SAVOLLARGA JAVOBLAR
═══════════════════════════════════════

**"Darslik ichida nima bor?"**
→ "Darslikda AI'ni amaliyotda qanday ishlatishni o'rganasiz. To'lov qilingandan keyin kanalga qo'shilib, barcha darslarni ko'rishingiz mumkin. 🙌"

**"Ishonasa bo'ladimi?"**
→ "Albatta, [ism aka/opa]. Mirage game club — rasmiy brand, Payme/Click orqali xavfsiz to'lov qabul qilamiz. To'lovdan so'ng darrov kanal linkini beraman. ✅"

**"Keyin to'layman"**
→ "Yaxshi, [ism aka/opa]. To'lovni qulay vaqtingizda bajaring, rekvizitlar yuqorida turibdi. Chek kelganda men shu yerdaman 🙌"

**"Chegirma bormi?"**
→ "Narx eng qulay holida — 39 000 so'm, [ism aka/opa]. Bu — kirish narxi 🙌"

═══════════════════════════════════════
# ESLATMA
═══════════════════════════════════════
Sen — professional sotuv menejerisan. Do'stona, ishonchli, aniq. Vazifang — mijozni to'lovga olib borish va chekni qabul qilish. Boshqa mavzularga kirishma, adashib ketma.
"""

# Suhbatlar tarixi (foydalanuvchi ID → xabarlar)
conversations = defaultdict(list)

# Egaga yuborilgan xabarlar → qaysi mijozga tegishli
# (Egadagi xabarga reply qilinganda kimga yuborishni bilish uchun)
owner_notifications = {}  # {owner_msg_id: user_chat_id}

client = Anthropic(api_key=ANTHROPIC_API_KEY)
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)


async def notify_owner(
    context: ContextTypes.DEFAULT_TYPE, text: str, user_chat_id: int = None
):
    """Egaga xabar yuborish. user_chat_id berilsa — reply orqali javob yuborish uchun eslab qolamiz."""
    try:
        msg = await context.bot.send_message(
            chat_id=OWNER_CHAT_ID, text=text, parse_mode="Markdown"
        )
        if user_chat_id is not None:
            owner_notifications[msg.message_id] = user_chat_id
    except Exception as e:
        logging.error(f"Egaga xabar yuborishda xatolik: {e}")


async def owner_reply_to_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Ega reply qilib mijozga javob yuborsa — botga o'rniga uni yetkazadi.
    Qaytaradi: True — bu reply qayta ishlandi, False — bu oddiy xabar."""
    replied = update.message.reply_to_message
    if not replied:
        return False

    # 1. Avval xotiradagi mapping'dan qidiramiz (tez usul)
    user_chat_id = owner_notifications.get(replied.message_id)

    # 2. Topilmasa — bildirishnoma matnidan ID'ni ajratib olamiz
    # (bot qayta ishga tushgan bo'lsa ham ishlaydi)
    if not user_chat_id and replied.text:
        match = re.search(r"🆔\s+`?(\d+)`?", replied.text)
        if match:
            user_chat_id = int(match.group(1))

    if not user_chat_id:
        await update.message.reply_text(
            "⚠️ Bu xabar mijozga bog'lanmagan. Faqat bot yuborgan bildirishnomalarga reply qiling."
        )
        return True

    # O'zimizga o'zimiz yubormaymiz (test paytida ega o'ziga xabar yuborsa loop bo'lmasin)
    if user_chat_id == OWNER_CHAT_ID:
        await update.message.reply_text(
            "ℹ️ Bu bildirishnoma sizning o'zingiz haqingizda. Boshqa mijoz bilan sinab ko'ring."
        )
        return True

    text = update.message.text
    try:
        await context.bot.send_message(chat_id=user_chat_id, text=text)
        # Mijozning suhbat tarixiga qo'shamiz (Claude keyinchalik kontekstni bilsin)
        conversations[user_chat_id].append({"role": "assistant", "content": text})
        await update.message.reply_text("✅ Yuborildi")
    except Exception as e:
        logging.error(f"Egadan mijozga yuborishda xatolik: {e}")
        await update.message.reply_text(f"❌ Yuborilmadi: {e}")

    return True


def user_info(update: Update) -> str:
    """Foydalanuvchi haqidagi ma'lumotni chiroyli formatda qaytaradi"""
    u = update.effective_user
    name = f"{u.first_name or ''} {u.last_name or ''}".strip() or "Noma'lum"
    username = f"@{u.username}" if u.username else "username yo'q"
    return f"👤 *{name}*\n🔗 {username}\n🆔 `{u.id}`"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Yangi foydalanuvchi /start bosganda"""
    user_id = update.effective_user.id
    conversations[user_id] = []

    welcome = (
        "Assalomu alaykum! 🙌\n\n"
        "Darslikka qiziqish bildirganingizdan hursandmiz.\n\n"
        "Mening ismim — *Jeckson*, shu darslikning sotuv menejeriman.\n\n"
        "Sizni kim deb chaqirsam bo'ladi?"
    )
    await update.message.reply_text(welcome, parse_mode="Markdown")

    # Egaga yangi mijoz kelgani haqida xabar
    await notify_owner(
        context,
        f"🆕 *Yangi mijoz botga kirdi*\n\n{user_info(update)}\n\n"
        f"💡 Javob berish uchun shu xabarga *Reply* qiling.",
        user_chat_id=update.effective_chat.id,
    )


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Suhbatni tozalash"""
    conversations[update.effective_user.id] = []
    await update.message.reply_text("Suhbat tarixi tozalandi ✅")


async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Har qanday matn xabariga javob"""
    user_id = update.effective_user.id

    # Agar EGA botga reply qilib yozayotgan bo'lsa — mijozga yetkazamiz, Claude'ga jo'natmaymiz
    if user_id == OWNER_CHAT_ID and update.message.reply_to_message:
        handled = await owner_reply_to_user(update, context)
        if handled:
            return

    user_text = update.message.text
    conversations[user_id].append({"role": "user", "content": user_text})
    # Oxirgi 20 ta xabarni saqlaymiz (kontekst uzunligini tejash uchun)
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
        # Javobdan faqat matn qismini olamiz (thinking bloklarini o'tkazib yuboramiz)
        reply = ""
        for block in response.content:
            if getattr(block, "type", None) == "text":
                reply = block.text
                break

        if not reply:
            reply = "Uzr, javob shakllantirishda muammo bo'ldi. Qaytadan urinib ko'ring."

        conversations[user_id].append({"role": "assistant", "content": reply})
        await update.message.reply_text(reply)

        # Egaga mijoz xabari va bot javobini yuborish
        await notify_owner(
            context,
            f"💬 *Yangi xabar*\n\n{user_info(update)}\n\n"
            f"📝 *Mijoz:*\n{user_text}\n\n"
            f"🤖 *Bot javobi:*\n{reply}\n\n"
            f"💡 O'zingiz javob berish uchun shu xabarga *Reply* qiling.",
            user_chat_id=update.effective_chat.id,
        )

    except Exception as e:
        logging.error(f"Xatolik: {e}")
        await update.message.reply_text(
            "Uzr, texnik nosozlik yuz berdi. Iltimos, biroz kutib, qaytadan urinib ko'ring 🙏"
        )


async def verify_receipt(image_bytes: bytes) -> tuple[bool, str]:
    """Rasmni Claude Vision orqali tekshiradi: chek yoki oddiy rasm?
    Qaytaradi: (chek_ekanmi, izoh_matni)"""
    try:
        image_b64 = base64.standard_b64encode(image_bytes).decode("utf-8")

        response = client.messages.create(
            model="claude-sonnet-5",
            max_tokens=300,
            messages=[
                {
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
                                "Bu rasm to'lov cheki (kvitansiya)mi? "
                                "Payme, Click, Uzum, Humo yoki boshqa bank/to'lov "
                                "tizimidan olingan chek/tranzaksiya tasdig'i bo'lishi mumkin. "
                                "Chek belgilari: summa, sana, karta raqami, tranzaksiya ID, "
                                "'Uspeshno', 'Muvaffaqiyatli', 'Отправлено' kabi so'zlar.\n\n"
                                "FAQAT quyidagi formatda javob ber:\n"
                                "CHEK: HA yoki YOQ\n"
                                "SUMMA: [ko'ringan summa yoki 'aniqmas']\n"
                                "IZOH: [1 gap]"
                            ),
                        },
                    ],
                }
            ],
        )

        text = ""
        for block in response.content:
            if getattr(block, "type", None) == "text":
                text = block.text
                break

        # Javobni tahlil qilish
        is_receipt = bool(re.search(r"CHEK:\s*HA", text, re.IGNORECASE))
        return is_receipt, text

    except Exception as e:
        logging.error(f"Chekni tekshirishda xatolik: {e}")
        # Xatolik bo'lsa — chek deb hisoblab, egaga yuboramiz (mijozni yo'qotmaslik uchun)
        return True, f"Tekshirib bo'lmadi ({e})"


async def handle_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mijoz rasm yuborganda — chek ekanini tekshirib, mos ravishda javob beramiz"""
    user_id = update.effective_user.id
    caption = update.message.caption or ""
    izoh = caption if caption else "yoq"

    # "Yozmoqda..." ko'rsatamiz — tekshiruv 3-5 soniya davom etadi
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id, action="typing"
    )

    # Rasmni yuklab olamiz
    try:
        photo = update.message.photo[-1]  # eng yuqori sifatli variant
        file = await context.bot.get_file(photo.file_id)
        image_bytes = bytes(await file.download_as_bytearray())
    except Exception as e:
        logging.error(f"Rasmni yuklashda xatolik: {e}")
        await update.message.reply_text("Rasmni yuklab bo'lmadi, qaytadan yuboring 🙏")
        return

    # Chek ekanini tekshirish
    is_receipt, verify_info = await verify_receipt(image_bytes)

    if not is_receipt:
        # Chek EMAS — mijozga muloyim javob
        await update.message.reply_text(
            "Bu rasm to'lov chekiga o'xshamayapti 🙈\n\n"
            "Iltimos, *Payme* yoki *Click* ilovasidan olingan to'lov tasdig'ini "
            "(chek/kvitansiya) yuboring. Odatda unda summa, sana va "
            "\"Muvaffaqiyatli\" degan yozuv bo'ladi. 🙌",
            parse_mode="Markdown",
        )
        # Egaga ham xabar (nazorat uchun)
        try:
            await context.bot.forward_message(
                chat_id=OWNER_CHAT_ID,
                from_chat_id=update.effective_chat.id,
                message_id=update.message.message_id,
            )
            await notify_owner(
                context,
                f"⚠️ *Chek EMAS rasm keldi*\n\n{user_info(update)}\n\n"
                f"🔍 Tekshiruv:\n{verify_info}\n\n"
                f"📝 Izoh: {izoh}\n\n"
                f"💡 Kerak bo'lsa, shu xabarga Reply qilib mijozga yozing.",
                user_chat_id=update.effective_chat.id,
            )
        except Exception as e:
            logging.error(f"Egaga xabar yuborishda xatolik: {e}")
        return

    # CHEK — hammasi joyida
    conversations[user_id].append(
        {
            "role": "user",
            "content": f"[Mijoz tolov chekini yubordi. Tekshiruv: {verify_info}]",
        }
    )

    await update.message.reply_text(
        "Rahmat! ✅ Chekingiz qabul qilindi.\n\n"
        "Tekshirib, tez orada siz bilan aloqaga chiqamiz va darslar kanalining linkini yuboramiz. 🙌"
    )

    # Egaga chekni forward qilish
    try:
        await context.bot.forward_message(
            chat_id=OWNER_CHAT_ID,
            from_chat_id=update.effective_chat.id,
            message_id=update.message.message_id,
        )
        await notify_owner(
            context,
            f"💰 *YANGI CHEK KELDI!*\n\n{user_info(update)}\n\n"
            f"🔍 Tekshiruv:\n{verify_info}\n\n"
            f"📝 Izoh: {izoh}\n\n"
            f"💡 Mijozga javob berish uchun shu xabarga *Reply* qiling.",
            user_chat_id=update.effective_chat.id,
        )
    except Exception as e:
        logging.error(f"Chekni forward qilishda xatolik: {e}")


def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(MessageHandler(filters.PHOTO, handle_receipt))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))

    print("✅ Bot ishga tushdi. To'xtatish uchun Ctrl+C.")
    app.run_polling()


if __name__ == "__main__":
    main()
