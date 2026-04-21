from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import qrcode
from qrcode.image.styles.moduledrawers import RoundedModuleDrawer
from qrcode.image.styles.colormasks import RadialGradiantColorMask
from PIL import Image
from io import BytesIO

TOKEN = "8793867925:AAFMTvDczkOuy3iTe1BN6XuX9SpQutcqegA"  # ← ваш токен

# Создание QR-кода (с логотипом или без)
def generate_qr(text: str, logo_bytes: bytes = None) -> BytesIO:
    qr = qrcode.QRCode(version=1,
                       error_correction=qrcode.constants.ERROR_CORRECT_H,
                       box_size=10, border=4)
    qr.add_data(text)
    qr.make(fit=True)

    # Красивый стиль: закруглённые углы + градиент
    img = qr.make_image(
        fill_color="black",
        back_color="white",
        module_drawer=RoundedModuleDrawer(),
        color_mask=RadialGradiantColorMask()
    ).convert('RGBA')

    # Если прислали фото — ставим его в центр
    if logo_bytes:
        logo = Image.open(BytesIO(logo_bytes)).convert("RGBA")
        logo_size = img.size[0] // 5
        logo = logo.resize((logo_size, logo_size), Image.LANCZOS)
        pos = ((img.size[0] - logo.size[0]) // 2, (img.size[1] - logo.size[1]) // 2)
        img.paste(logo, pos, logo)

    bio = BytesIO()
    img.save(bio, "PNG")
    bio.seek(0)
    return bio

# /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я бот-генератор QR-кодов с логотипом\n\n"
        "Просто пришли:\n"
        "• текст или ссылку → обычный красивый QR\n"
        "• фото + подпись (ссылка) → QR с твоим логотипом в центре\n\n"
        "Команды:\n"
        "/help — помощь\n"
        "/qr ссылка — быстро создать QR"
    )

# /help
async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Как пользоваться:\n\n"
        "1. Пришли обычный текст или ссылку → получишь красивый QR-код\n"
        "2. Пришли любое фото и в подписи напиши ссылку → "
        "получишь QR-код с твоим логотипом в центре\n"
        "3. Команда /qr https://google.com — мгновенный QR"
    )

# Обычный текст
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    qr_img = generate_qr(text)
    await update.message.reply_photo(qr_img,
        caption=f"Готово!\n\n`{text[:70]}{'...' if len(text)>70 else ''}`",
        parse_mode="Markdown")

# Фото пришло (логотип)
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo = update.message.photo[-1]
    caption = update.message.caption.strip() if update.message.caption else "https://t.me/ваш_канал"

    file = await photo.get_file()
    photo_bytes = await file.download_as_bytearray()

    qr_img = generate_qr(caption, photo_bytes)
    await update.message.reply_photo(qr_img, caption="QR-код с логотипом готов!")

# /qr команда
async def qr_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        text = " ".join(context.args)
        qr_img = generate_qr(text)
        await update.message.reply_photo(qr_img, caption=text[:100])
    else:
        await update.message.reply_text("Пример: /qr https://youtube.com")

def main():
    print("Бот запускается... (с логотипом в центре QR)")
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("qr", qr_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    # Убираем лишние ошибки в консоли
    import logging
    logging.getLogger("httpx").setLevel(logging.WARNING)

    app.run_polling(drop_pending_updates=True, poll_interval=2.0)

if __name__ == "__main__":
    main()
