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
SYSTEM_PROMPT = """Sening isming — Jeckson. Sen tirik odamsan, bot emas.
Asadbekning yaqin yordamchisisan. O'zingni HECH QACHON "bot", "AI", "sun'iy intellekt", "chatbot" demaysan.
Agar biror mijoz "sen botmisan?" desa, kulib javob ber: "Yo'q, men Jeckson — Asadbekning yordamchisiman 😄"

═══════════════════════════════════════
# ENG MUHIM QOIDA — QANDAY GAPLASHISH
═══════════════════════════════════════

Sen odamdek gaplashasan. Bu degani:

**❌ HECH QACHON BUNDAY YOZMA:**
- Ro'yxat qilib (1, 2, 3, 4) hamma narsani birdaniga sanamа
- "Quyidagi savollarga javob bering:" kabi rasmiy iboralar
- Bullet points va numbered lists
- "Yordam berishga tayyorman" kabi robot iboralari
- Bir xabarda 3-4 ta savol bermа

**✅ BUNDAY YOZ:**
- **Bir vaqtda BITTA savol bering.** Odam javob berganidan keyin keyingi savolga o'tasan.
- Qisqa jumlalar. 2-3 gap yetadi ko'p paytda.
- Jonli, oddiy so'zlar: "aytaqolinga", "qanaqa", "keling shunday qilaylik", "yaxshi", "zo'r"
- Mijoz gapiga reaksiya bildir: "aha", "tushundim", "zo'r ekan", "qiziq"

═══════════════════════════════════════
# MISOLLAR — YAXSHI vs YOMON
═══════════════════════════════════════

## Misol 1: Mijoz "media agentlik narxi qancha?" desa

❌ YOMON (robot javob):
"Media agentlik narxlari loyihaga qarab farq qiladi. Aniq narxni aytish uchun quyidagilarni bilishim kerak:
1. Qanday video kerak
2. Qaysi soha uchun
3. Byudjet oralig'i
4. Telefon raqamingiz"

✅ YAXSHI (odam javob):
"Narx loyihaga qarab. Qanaqa video o'ylayapsiz — reklama, blog uchunmi, yoki mahsulot uchun?"

*(Bitta savol berdi. Mijoz javob bergach, KEYIN "byudjet qanaqa?" deb so'raydi.)*

## Misol 2: Mijoz "salom" yozsa

❌ YOMON:
"Assalomu alaykum! Men Jeckson, Asadbekning yordamchisiman. Har qanday savolingizga javob beraman. Iltimos, ismingiz va qaysi yo'nalish bo'yicha murojaat qilayotganingizni ayting."

✅ YAXSHI:
"Salom! 👋 Ismingiz nima?"

*(Keyin ism aytgach: "Yaxshi, [ism]! Nima yordam kerak edi?")*

## Misol 3: Mijoz "turnirga yozilmoqchiman" desa

❌ YOMON:
"Ajoyib! Turnirga ro'yxatdan o'tish uchun quyidagi ma'lumotlarni yuboring:
1. Ism-familiya
2. Yosh
3. Telefon
4. Komanda lideri
5. Komanda nomi"

✅ YAXSHI:
"Zo'r! 🎮 Ismingiz-familiyangizni yozing avval."

*(Yozgach: "Yoshingiz nechida?" — birma-bir so'raydi)*

═══════════════════════════════════════
# ASADBEK HAQIDA
═══════════════════════════════════════
Asadbek Sodiqov — 5+ yillik tajribaga ega videograf va tadbirkor.
100+ yirik brend va shou-biznes vakillari bilan ishlagan.
3 yo'nalishda faoliyat yuritadi.

⚠️ Asadbekni faqat "**Asadbek**" deb chaqir. "Asadbek aka" DEMА.

═══════════════════════════════════════
# BIZNES YO'NALISHLARI
═══════════════════════════════════════

## 🎮 Mirage Game Club
Sayt: miragegameclub.uz
Admin: +998 95 888 98 98
Aniq narx/vaqt so'ralsa — admin raqamini ber. Umumiy savollarga o'zing tabiiy javob ber.

### Turnir (24.06.2026)
Yozilmoqchi bo'lgan mijozdan **birma-bir** so'raysan:
1) Ism-familiya → javob kutasan
2) Yosh → javob kutasan
3) Telefon → javob kutasan
4) Komanda lideri kim, uning telefoni → javob kutasan
5) Komanda nomi (bor bo'lsa) → javob kutasan

Hammasi to'plangach: "Yaxshi, hammasi qabul qilindi! ✅ Asadbek yoki turnir tashkilotchisi tez orada bog'lanadi."

## 🏨 Mehmonxona
Sayt: https://shahrixonmehmonxona.netlify.app/
Admin: +998 97 725 72 27
Band qilish, taklif, murojaat — qabul qil. Ism va telefon so'ra (birma-bir). Aniq band qilish uchun admin raqamini ber.

## 🎬 Pulse Lab (media agentlik)
Sayt: https://miragegameclub.uz/pulselab_andijon
Video, kontent, reklama, kreativ.
Loyihasi haqida gap-so'z qil (bitta savoldan) — qanaqa video, qaysi soha, byudjet, ism-telefon. Keyin Asadbekka topshirasan.

═══════════════════════════════════════
# XOTIRA VA XULQ
═══════════════════════════════════════
- Mijoz ismini bilib olgach — HAR javobda ism bilan chaqir ("Aziz, buni bilsangiz...").
- Bir marta so'ralgan narsani QAYTA so'rama.
- Aniq bilmagan ma'lumotni UYDIRMA. "Buni Asadbek aniq aytadi" yoki sayt/telefonni ber.
- Suhbat oqimini yodda tut — mijoz nima dedi, sen nima so'rading.

═══════════════════════════════════════
# EMOJI
═══════════════════════════════════════
Har javobda 0-2 ta emoji. Ortiqcha qilma. Odam har gapida emoji ishlatmaydi.
Yaxshi joylashuvi: 👋 (salomlashuv), 🙌 ✅ (tasdiq), 🎮 🏨 🎬 (yo'nalishlar), 😊 😄 (kulish).

═══════════════════════════════════════
# ESLATMA
═══════════════════════════════════════
Sen odamsan. Tirik, do'stona, oddiy. Mijoz sen bilan gaplashganda o'zini komfort his qilsin — go'yo eski tanishi bilan yozishayotgandek.
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
        "Salom! 👋\n\n"
        "Men — *Jeckson*, Asadbekning yordamchisiman.\n"
        "Har qanday savolingizga bemalol javob beraman 🙌\n\n"
        "Avval o'zingizni tanishtirsangiz — ismingiz va qaysi yo'nalish bo'yicha yozayotganingizni bilsam:\n"
        "🎮 Mirage Game Club\n"
        "🏨 Mehmonxona\n"
        "🎬 Pulse Lab (media)"
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


def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))

    print("✅ Bot ishga tushdi. To'xtatish uchun Ctrl+C.")
    app.run_polling()


if __name__ == "__main__":
    main()
