import os
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

client = Anthropic(api_key=ANTHROPIC_API_KEY)
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)


async def notify_owner(context: ContextTypes.DEFAULT_TYPE, text: str):
    """Egaga (Asadbek akaga) xabar yuborish. Xatolik bo'lsa ham botni to'xtatmaydi."""
    try:
        await context.bot.send_message(
            chat_id=OWNER_CHAT_ID, text=text, parse_mode="Markdown"
        )
    except Exception as e:
        logging.error(f"Egaga xabar yuborishda xatolik: {e}")


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
        f"🆕 *Yangi mijoz botga kirdi*\n\n{user_info(update)}",
    )


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Suhbatni tozalash"""
    conversations[update.effective_user.id] = []
    await update.message.reply_text("Suhbat tarixi tozalandi ✅")


async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Har qanday matn xabariga javob"""
    user_id = update.effective_user.id
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
            f"🤖 *Bot javobi:*\n{reply}",
        )

    except Exception as e:
        logging.error(f"Xatolik: {e}")
        await update.message.reply_text(
            "Uzr, texnik nosozlik yuz berdi. Iltimos, biroz kutib, qaytadan urinib ko'ring 🙏"
        )


async def handle_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mijoz chek (rasm) yuborganda"""
    user_id = update.effective_user.id
    caption = update.message.caption or ""
    izoh = caption if caption else "yoq"

    # Suhbat tarixiga chek yuborilganini qo'shamiz (Claude bilishi uchun)
    conversations[user_id].append(
        {
            "role": "user",
            "content": f"[Mijoz tolov chekini rasm korinishida yubordi. Izoh: {izoh}]",
        }
    )

    # Mijozga tasdiq javob
    await update.message.reply_text(
        "Rahmat! ✅ Chekingiz qabul qilindi.\n\n"
        "Tekshirib, tez orada siz bilan aloqaga chiqamiz va darslar kanalining linkini yuboramiz. 🙌"
    )

    # Egaga chekni forward qilish (Asadbekka)
    try:
        await context.bot.forward_message(
            chat_id=OWNER_CHAT_ID,
            from_chat_id=update.effective_chat.id,
            message_id=update.message.message_id,
        )
        await notify_owner(
            context,
            f"💰 *YANGI CHEK KELDI!*\n\n{user_info(update)}\n\n📝 Izoh: {izoh}",
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
