from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes, ConversationHandler
)
import qrcode
from qrcode.image.styles.moduledrawers import (
    RoundedModuleDrawer, GappedSquareModuleDrawer,
    CircleModuleDrawer, SquareModuleDrawer, VerticalBarsDrawer, HorizontalBarsDrawer
)
from qrcode.image.styledpil import StyledPilImage
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
from io import BytesIO
import logging
import math

logging.getLogger("httpx").setLevel(logging.WARNING)

TOKEN = "8793867925:AAFMTvDczkOuy3iTe1BN6XuX9SpQutcqegA"  # ← sizning tokeningiz

# --- States ---
WAITING_TEXT, WAITING_STYLE, WAITING_COLOR, WAITING_FRAME, WAITING_LOGO = range(5)

# --- User sessiyalarini saqlash ---
user_sessions = {}

# ══════════════════════════════════════════════
#  RANGLAR
# ══════════════════════════════════════════════
COLOR_THEMES = {
    "🔴 Qizil":        {"fg": (180, 0, 0),       "bg": (255, 245, 245)},
    "🔵 Ko'k":         {"fg": (0, 60, 180),       "bg": (240, 245, 255)},
    "🟢 Yashil":       {"fg": (0, 140, 60),       "bg": (240, 255, 245)},
    "🟣 Binafsha":     {"fg": (100, 0, 180),      "bg": (248, 240, 255)},
    "🟠 To'q sariq":   {"fg": (200, 80, 0),       "bg": (255, 248, 235)},
    "⚫ Klassik":      {"fg": (20, 20, 20),       "bg": (255, 255, 255)},
    "🌈 Neon yashil":  {"fg": (0, 220, 100),      "bg": (10, 15, 10)},
    "💜 Neon binafsha":{"fg": (180, 0, 255),      "bg": (10, 5, 20)},
    "🩵 Cyan neon":    {"fg": (0, 220, 255),      "bg": (5, 10, 20)},
    "🌹 Pushti":       {"fg": (220, 30, 120),     "bg": (255, 240, 248)},
    "🤎 Qahva":        {"fg": (100, 55, 20),      "bg": (255, 248, 235)},
    "🩶 Kulrang":      {"fg": (80, 90, 100),      "bg": (240, 242, 245)},
}

# ══════════════════════════════════════════════
#  STILLAR
# ══════════════════════════════════════════════
STYLE_DRAWERS = {
    "⭕ Doira":         CircleModuleDrawer(),
    "🔲 Kvadrat":       SquareModuleDrawer(),
    "🔳 Bo'shliqli":    GappedSquareModuleDrawer(),
    "💊 Yumaloq":       RoundedModuleDrawer(),
    "📊 Vertikal":      VerticalBarsDrawer(),
    "📉 Gorizontal":    HorizontalBarsDrawer(),
}

# ══════════════════════════════════════════════
#  RAMKALAR
# ══════════════════════════════════════════════
FRAMES = {
    "❌ Ramsiz":     None,
    "📷 Skanerlang": "scan",
    "⭐ Yulduzli":   "star",
    "💎 Premium":    "premium",
    "🌊 To'lqin":    "wave",
    "🔥 Olov":       "fire",
    "🎯 Target":     "target",
}

# ══════════════════════════════════════════════
#  QR YARATISH FUNKSIYASI
# ══════════════════════════════════════════════
def generate_creative_qr(
    text: str,
    color_name: str = "⚫ Klassik",
    style_name: str = "💊 Yumaloq",
    frame_name: str = "❌ Ramsiz",
    logo_bytes: bytes = None
) -> BytesIO:
    theme = COLOR_THEMES.get(color_name, COLOR_THEMES["⚫ Klassik"])
    drawer = STYLE_DRAWERS.get(style_name, RoundedModuleDrawer())
    fg = theme["fg"]
    bg = theme["bg"]

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=12,
        border=4
    )
    qr.add_data(text)
    qr.make(fit=True)

    img = qr.make_image(
        image_factory=StyledPilImage,
        module_drawer=drawer,
        fill_color=fg,
        back_color=bg,
    ).convert("RGBA")

    # --- Logo qo'shish ---
    if logo_bytes:
        logo = Image.open(BytesIO(logo_bytes)).convert("RGBA")
        logo_size = img.size[0] // 5
        logo = logo.resize((logo_size, logo_size), Image.LANCZOS)

        # Logo uchun oq doira fon
        circle_size = logo_size + 20
        circle_bg = Image.new("RGBA", (circle_size, circle_size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(circle_bg)
        draw.ellipse([0, 0, circle_size, circle_size], fill=(255, 255, 255, 255))

        pos_circle = (
            (img.size[0] - circle_size) // 2,
            (img.size[1] - circle_size) // 2
        )
        img.paste(circle_bg, pos_circle, circle_bg)

        pos_logo = (
            (img.size[0] - logo_size) // 2,
            (img.size[1] - logo_size) // 2
        )
        img.paste(logo, pos_logo, logo)

    # --- Ramka qo'shish ---
    frame_key = FRAMES.get(frame_name)
    if frame_key:
        img = add_frame(img, frame_key, fg, bg, text)

    bio = BytesIO()
    img.save(bio, "PNG")
    bio.seek(0)
    return bio


def add_frame(img: Image.Image, frame_type: str, fg, bg, label_text: str) -> Image.Image:
    """QR atrofiga chiroyli ramka qo'shadi"""
    qr_w, qr_h = img.size
    padding = 40
    label_h = 60

    # Yangi canvas
    canvas_w = qr_w + padding * 2
    canvas_h = qr_h + padding * 2 + label_h
    canvas = Image.new("RGBA", (canvas_w, canvas_h), (255, 255, 255, 255))
    draw = ImageDraw.Draw(canvas)

    if frame_type == "scan":
        # Ko'k-oq gradient ramka
        draw.rectangle([0, 0, canvas_w, canvas_h], fill=(30, 60, 180))
        draw.rectangle([8, 8, canvas_w-8, canvas_h-8], fill=(255, 255, 255))
        # Burchak markerlar
        corner_size = 30
        lw = 6
        for x, y in [(15,15),(canvas_w-15-corner_size, 15),
                     (15, canvas_h-15-corner_size)]:
            draw.rectangle([x, y, x+corner_size, y+lw], fill=(30, 60, 180))
            draw.rectangle([x, y, x+lw, y+corner_size], fill=(30, 60, 180))
        x, y = canvas_w-15-corner_size, canvas_h-15-corner_size
        draw.rectangle([x, y, x+corner_size, y+lw], fill=(30, 60, 180))
        draw.rectangle([x+corner_size-lw, y, x+corner_size, y+corner_size], fill=(30, 60, 180))
        label = "📷  SKANERLANG"
        label_color = (30, 60, 180)

    elif frame_type == "star":
        draw.rectangle([0, 0, canvas_w, canvas_h], fill=(255, 200, 0))
        draw.rectangle([6, 6, canvas_w-6, canvas_h-6], fill=(255, 255, 255))
        # Yulduzchalar
        for i, (sx, sy) in enumerate([(15,15),(canvas_w-35,15),(15,canvas_h-35),(canvas_w-35,canvas_h-35)]):
            draw_star(draw, sx+10, sy+10, 12, (255, 160, 0))
        label = "⭐  QR KOD"
        label_color = (180, 100, 0)

    elif frame_type == "premium":
        draw.rectangle([0, 0, canvas_w, canvas_h], fill=(20, 20, 20))
        # Oltin chegara
        border = 5
        draw.rectangle([border, border, canvas_w-border, canvas_h-border],
                       outline=(212, 175, 55), width=3)
        draw.rectangle([border+8, border+8, canvas_w-border-8, canvas_h-border-8],
                       fill=(255, 255, 255))
        label = "💎  PREMIUM"
        label_color = (150, 110, 20)

    elif frame_type == "wave":
        draw.rectangle([0, 0, canvas_w, canvas_h], fill=(0, 150, 200))
        # To'lqin effekti — gorizontal chiziqlar
        for i in range(0, canvas_h, 6):
            alpha = int(30 + 20 * math.sin(i * 0.2))
            draw.line([(0, i), (canvas_w, i)], fill=(255, 255, 255, alpha), width=2)
        draw.rectangle([10, 10, canvas_w-10, canvas_h-10], fill=(255, 255, 255))
        label = "🌊  QR KOD"
        label_color = (0, 100, 160)

    elif frame_type == "fire":
        draw.rectangle([0, 0, canvas_w, canvas_h], fill=(220, 50, 0))
        draw.rectangle([6, 6, canvas_w-6, canvas_h-6], fill=(255, 255, 255))
        # Olov chiziqlar
        for i in range(0, canvas_w, 20):
            h = 10 + (i % 3) * 5
            draw.polygon([(i, 0), (i+10, 0), (i+5, -h)], fill=(255, 150, 0))
        label = "🔥  SKANERLANG"
        label_color = (180, 30, 0)

    elif frame_type == "target":
        draw.ellipse([0, 0, canvas_w, canvas_w], fill=(220, 0, 50))
        draw.rectangle([0, 0, canvas_w, canvas_h], fill=(255, 255, 255))
        draw.rectangle([0, 0, canvas_w, canvas_h], outline=(220, 0, 50), width=8)
        draw.rectangle([8, 8, canvas_w-8, canvas_h-8], outline=(220, 0, 50), width=3)
        label = "🎯  QR KOD"
        label_color = (180, 0, 30)

    else:
        label = "QR KOD"
        label_color = (50, 50, 50)

    # QR ni joylashtirish
    canvas.paste(img, (padding, padding), img)

    # Label yozish
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 22)
    except:
        font = ImageFont.load_default()

    # Qisqartirish
    short_label = label_text[:25] + ("..." if len(label_text) > 25 else "")
    label_y = qr_h + padding + 10

    draw2 = ImageDraw.Draw(canvas)
    # Mavzu nomi
    draw2.text((canvas_w // 2, label_y), label, fill=label_color, font=font, anchor="mm")
    # URL/matn
    try:
        small_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 14)
    except:
        small_font = font
    draw2.text((canvas_w // 2, label_y + 28), short_label, fill=(120, 120, 120),
               font=small_font, anchor="mm")

    return canvas


def draw_star(draw, cx, cy, r, color):
    """5 burchakli yulduz chizadi"""
    points = []
    for i in range(10):
        angle = math.radians(i * 36 - 90)
        radius = r if i % 2 == 0 else r * 0.4
        points.append((cx + radius * math.cos(angle), cy + radius * math.sin(angle)))
    draw.polygon(points, fill=color)


# ══════════════════════════════════════════════
#  KLAVIATURA YORDAMCHILARI
# ══════════════════════════════════════════════
def style_keyboard():
    styles = list(STYLE_DRAWERS.keys())
    keyboard = []
    row = []
    for i, s in enumerate(styles):
        row.append(InlineKeyboardButton(s, callback_data=f"style:{s}"))
        if (i + 1) % 2 == 0:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    return InlineKeyboardMarkup(keyboard)

def color_keyboard():
    colors = list(COLOR_THEMES.keys())
    keyboard = []
    row = []
    for i, c in enumerate(colors):
        row.append(InlineKeyboardButton(c, callback_data=f"color:{c}"))
        if (i + 1) % 2 == 0:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    return InlineKeyboardMarkup(keyboard)

def frame_keyboard():
    frames = list(FRAMES.keys())
    keyboard = []
    row = []
    for i, f in enumerate(frames):
        row.append(InlineKeyboardButton(f, callback_data=f"frame:{f}"))
        if (i + 1) % 2 == 0:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    return InlineKeyboardMarkup(keyboard)

def logo_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Logo qo'shish (rasm yuboring)", callback_data="logo:yes")],
        [InlineKeyboardButton("⏭ Logo kerak emas", callback_data="logo:no")],
    ])

def generate_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✨ QR YARATISH", callback_data="generate")],
        [InlineKeyboardButton("🔄 Qayta boshlash", callback_data="restart")],
    ])


# ══════════════════════════════════════════════
#  HANDLERS
# ══════════════════════════════════════════════
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user_sessions[uid] = {}
    await update.message.reply_text(
        "👋 *Kreativ QR-kod Generator*\n\n"
        "Men sizga rang-barang, chiroyli, ramkali QR-kodlar yaratib beraman!\n\n"
        "📌 Boshlash uchun — ссылка yoki matn yuboring\n"
        "📎 Yoki shunchaki: /qr <matn>",
        parse_mode="Markdown"
    )
    return WAITING_TEXT

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user_sessions[uid] = {"text": update.message.text.strip()}
    await update.message.reply_text(
        "🎨 *Modul stili tanlang:*",
        reply_markup=style_keyboard(),
        parse_mode="Markdown"
    )
    return WAITING_STYLE

async def style_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    style = query.data.split(":", 1)[1]
    user_sessions[uid]["style"] = style
    await query.edit_message_text(
        f"✅ Stil: *{style}*\n\n🌈 *Rang tanlang:*",
        reply_markup=color_keyboard(),
        parse_mode="Markdown"
    )
    return WAITING_COLOR

async def color_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    color = query.data.split(":", 1)[1]
    user_sessions[uid]["color"] = color
    await query.edit_message_text(
        f"✅ Rang: *{color}*\n\n🖼 *Ramka tanlang:*",
        reply_markup=frame_keyboard(),
        parse_mode="Markdown"
    )
    return WAITING_FRAME

async def frame_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    frame = query.data.split(":", 1)[1]
    user_sessions[uid]["frame"] = frame
    await query.edit_message_text(
        f"✅ Ramka: *{frame}*\n\n🖼 *Logo qo'shmoqchimisiz?*",
        reply_markup=logo_keyboard(),
        parse_mode="Markdown"
    )
    return WAITING_LOGO

async def logo_decision(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    decision = query.data.split(":", 1)[1]

    if decision == "yes":
        await query.edit_message_text(
            "📸 Logo rasmingizni yuboring (PNG/JPG):",
            parse_mode="Markdown"
        )
        return WAITING_LOGO
    else:
        user_sessions[uid]["logo"] = None
        await query.edit_message_text(
            _session_summary(uid) + "\n\n✨ *QR yaratamizmi?*",
            reply_markup=generate_keyboard(),
            parse_mode="Markdown"
        )
        return WAITING_LOGO

async def handle_logo_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    photo = update.message.photo[-1]
    file = await photo.get_file()
    photo_bytes = bytes(await file.download_as_bytearray())
    user_sessions[uid]["logo"] = photo_bytes

    await update.message.reply_text(
        "✅ Logo qabul qilindi!\n\n" + _session_summary(uid) + "\n\n✨ *QR yaratamizmi?*",
        reply_markup=generate_keyboard(),
        parse_mode="Markdown"
    )
    return WAITING_LOGO

async def do_generate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    sess = user_sessions.get(uid, {})

    await query.edit_message_text("⏳ QR-kod yaratilmoqda...")

    qr_img = generate_creative_qr(
        text=sess.get("text", "https://t.me"),
        color_name=sess.get("color", "⚫ Klassik"),
        style_name=sess.get("style", "💊 Yumaloq"),
        frame_name=sess.get("frame", "❌ Ramsiz"),
        logo_bytes=sess.get("logo"),
    )

    caption = (
        f"✅ *QR-kod tayyor!*\n\n"
        f"🎨 Stil: {sess.get('style','?')}\n"
        f"🌈 Rang: {sess.get('color','?')}\n"
        f"🖼 Ramka: {sess.get('frame','?')}\n"
        f"📎 Matn: `{sess.get('text','')[:50]}`"
    )

    await query.message.reply_photo(qr_img, caption=caption, parse_mode="Markdown")
    await query.message.reply_text(
        "🔄 Yangi QR uchun matn yuboring yoki /start bosing."
    )
    return WAITING_TEXT

async def restart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    user_sessions[uid] = {}
    await query.edit_message_text("🔄 Qayta boshlandi! Matn yoki link yuboring:")
    return WAITING_TEXT

async def qr_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        text = " ".join(context.args)
        qr_img = generate_creative_qr(text)
        await update.message.reply_photo(qr_img, caption=f"✅ QR-kod: `{text[:60]}`", parse_mode="Markdown")
    else:
        await update.message.reply_text("Misol: /qr https://youtube.com")

def _session_summary(uid):
    sess = user_sessions.get(uid, {})
    return (
        f"📋 *Tanlangan parametrlar:*\n"
        f"🎨 Stil: {sess.get('style', '—')}\n"
        f"🌈 Rang: {sess.get('color', '—')}\n"
        f"🖼 Ramka: {sess.get('frame', '—')}\n"
        f"🖼 Logo: {'✅ Bor' if sess.get('logo') else '❌ Yo\'q'}"
    )


# ══════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════
def main():
    print("🚀 Kreativ QR Bot ishga tushdi!")
    app = Application.builder().token(TOKEN).build()

    from telegram.ext import ConversationHandler
    conv = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text),
        ],
        states={
            WAITING_TEXT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text),
            ],
            WAITING_STYLE: [
                CallbackQueryHandler(style_chosen, pattern="^style:"),
            ],
            WAITING_COLOR: [
                CallbackQueryHandler(color_chosen, pattern="^color:"),
            ],
            WAITING_FRAME: [
                CallbackQueryHandler(frame_chosen, pattern="^frame:"),
            ],
            WAITING_LOGO: [
                CallbackQueryHandler(logo_decision, pattern="^logo:"),
                CallbackQueryHandler(do_generate, pattern="^generate$"),
                CallbackQueryHandler(restart, pattern="^restart$"),
                MessageHandler(filters.PHOTO, handle_logo_photo),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text),
            ],
        },
        fallbacks=[CommandHandler("start", start)],
        allow_reentry=True,
    )

    app.add_handler(conv)
    app.add_handler(CommandHandler("qr", qr_command))

    app.run_polling(drop_pending_updates=True, poll_interval=2.0)

if __name__ == "__main__":
    main()
