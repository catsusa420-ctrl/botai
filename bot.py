import os
import logging
import httpx
from urllib.parse import quote

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

# ─── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ─── States ────────────────────────────────────────────────────────────────────
WAITING_FOR_PROMPT = 1

# ─── Pollinations helper ────────────────────────────────────────────────────────
def build_image_url(prompt: str, width: int = 1024, height: int = 1024) -> str:
    """Return a Pollinations.ai URL for the given prompt."""
    encoded = quote(prompt)
    return (
        f"https://image.pollinations.ai/prompt/{encoded}"
        f"?width={width}&height={height}&nologo=true&enhance=true"
    )

# ─── Handlers ──────────────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "👋 مرحباً! أنا بوت توليد الصور.\n\n"
        "أرسل /image لتوليد صورة من وصف نصي.\n"
        "أرسل /help لعرض المساعدة."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "📖 *المساعدة*\n\n"
        "/image — ابدأ توليد صورة جديدة\n"
        "/cancel — إلغاء العملية الحالية\n\n"
        "بعد إرسال /image سيُطلب منك كتابة وصف للصورة بالإنجليزية أو العربية.",
        parse_mode="Markdown",
    )


async def image_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry point — ask the user for a prompt."""
    await update.message.reply_text(
        "🎨 أرسل لي وصفاً للصورة التي تريد توليدها:\n"
        "_(مثال: a futuristic city at sunset, digital art)_",
        parse_mode="Markdown",
    )
    return WAITING_FOR_PROMPT


async def generate_image(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive the prompt, generate the image and send it back."""
    prompt = update.message.text.strip()

    if not prompt:
        await update.message.reply_text("⚠️ الوصف فارغ، حاول مرة أخرى.")
        return WAITING_FOR_PROMPT

    thinking_msg = await update.message.reply_text("⏳ جارٍ توليد الصورة، انتظر لحظة…")

    image_url = build_image_url(prompt)
    logger.info("Fetching image for prompt: %s", prompt)

    try:
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
            response = await client.get(image_url)
            response.raise_for_status()
            image_bytes = response.content

        await update.message.reply_photo(
            photo=image_bytes,
            caption=f"🖼 *{prompt}*",
            parse_mode="Markdown",
        )
    except httpx.TimeoutException:
        await update.message.reply_text("⏱ انتهت مهلة الطلب، جرّب مرة أخرى.")
    except httpx.HTTPStatusError as e:
        logger.error("HTTP error: %s", e)
        await update.message.reply_text(f"❌ خطأ من الخادم: {e.response.status_code}")
    except Exception as e:
        logger.exception("Unexpected error")
        await update.message.reply_text(f"❌ حدث خطأ غير متوقع: {e}")
    finally:
        await thinking_msg.delete()

    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("❌ تم الإلغاء.")
    return ConversationHandler.END


async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "🤔 أمر غير معروف. أرسل /help للمساعدة."
    )

# ─── Main ───────────────────────────────────────────────────────────────────────
def main() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN environment variable is not set!")

    app = ApplicationBuilder().token(token).build()

    # Conversation: /image → prompt → generate
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("image", image_command)],
        states={
            WAITING_FOR_PROMPT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, generate_image)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(conv_handler)
    app.add_handler(MessageHandler(filters.COMMAND, unknown))

    logger.info("Bot is running…")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
