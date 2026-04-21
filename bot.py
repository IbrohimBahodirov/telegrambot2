import time
import asyncio
import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.error import TelegramError

from config import (
    CATEGORIES, QUESTION_COUNTS,
    QUESTION_TIMEOUT, SCORE_DISPLAY_PAUSE,
    BASE_POINTS, MAX_SPEED_BONUS,
)
from api import fetch_questions
from database import save_game_results, get_global_top, get_user_stats

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# Yordamchi funksiyalar
# ──────────────────────────────────────────────

def get_games(context: ContextTypes.DEFAULT_TYPE) -> dict:
    if "games" not in context.bot_data:
        context.bot_data["games"] = {}
    return context.bot_data["games"]


def get_poll_map(context: ContextTypes.DEFAULT_TYPE) -> dict:
    """poll_id → chat_id xaritasi"""
    if "poll_map" not in context.bot_data:
        context.bot_data["poll_map"] = {}
    return context.bot_data["poll_map"]


def build_lobby_text(game: dict) -> str:
    players_text = "\n".join(
        f"  • {p['name']}" for p in game["players"].values()
    )
    return (
        f"🎮 *Yangi Quiz O'yini!*\n\n"
        f"📁 Kategoriya: *{game['category_name']}*\n"
        f"❓ Savollar soni: *{game['total']} ta*\n"
        f"⏱ Har bir savol: *{QUESTION_TIMEOUT} soniya*\n"
        f"⚡ Tezlik bonusi: *+{MAX_SPEED_BONUS} ball*\n\n"
        f"👥 *Ishtirokchilar ({len(game['players'])} ta):*\n"
        f"{players_text}\n\n"
        f"Qo'shilish uchun ✋ tugmasini bosing!\n"
        f"Yaratuvchi ▶️ tugmasini bosib boshlaydi."
    )


def build_scoreboard(players: dict, total_q: int, show_correct: bool = True) -> str:
    sorted_p = sorted(players.items(), key=lambda x: x[1]["score"], reverse=True)
    medals = ["🥇", "🥈", "🥉"]
    lines = []
    for i, (_, p) in enumerate(sorted_p):
        medal = medals[i] if i < 3 else f"*{i+1}.*"
        extra = f" ({p['correct']}/{total_q} ✅)" if show_correct else ""
        lines.append(f"{medal} {p['name']}: *{p['score']}* ball{extra}")
    return "\n".join(lines)


# ──────────────────────────────────────────────
# Asosiy komandalar
# ──────────────────────────────────────────────

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "👋 *Quiz Bot*ga xush kelibsiz!\n\n"
        "🌐 Savollar *turli mavzularda* — internet saytlaridan olinadi!\n\n"
        "🎮 *Komandalar:*\n"
        "├ /quiz — Yangi o'yin boshlash\n"
        "├ /top — Global reyting 🏆\n"
        "├ /mystats — Mening statistikam 📊\n"
        "├ /stop — O'yinni to'xtatish 🛑\n"
        "└ /help — Qoidalar ℹ️\n\n"
        "📌 *Guruhga qo'shing va do'stlar bilan raqobatlashing!*"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📖 *O'yin qoidalari*\n\n"
        "1️⃣ /quiz buyrug'ini bering\n"
        "2️⃣ Kategoriya va savol sonini tanlang\n"
        "3️⃣ Ishtirokchilar ✋ tugmasi bilan qo'shiladi\n"
        "4️⃣ Yaratuvchi ▶️ tugmasini bosib boshlaydi\n"
        "5️⃣ Har bir savolga *20 soniya* vaqt bor\n\n"
        "🏆 *Ball tizimi:*\n"
        f"• To'g'ri javob: *{BASE_POINTS} ball*\n"
        f"• Tezlik bonusi: *+{MAX_SPEED_BONUS} ball* (tezroq = ko'proq)\n"
        "• Noto'g'ri javob: *0 ball*\n\n"
        "💡 *Maslahat:* Tezroq javob bering — bonusni yo'qotmang!"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def quiz_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    games = get_games(context)

    if chat_id in games and games[chat_id]["status"] != "finished":
        await update.message.reply_text(
            "⚠️ Bu chatda allaqachon aktiv o'yin bor!\n"
            "To'xtatish uchun /stop"
        )
        return

    keyboard = []
    row = []
    for key, (name, _) in CATEGORIES.items():
        row.append(InlineKeyboardButton(name, callback_data=f"cat_{key}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    await update.message.reply_text(
        "🎯 *Kategoriyani tanlang:*",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown",
    )


async def top_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = get_global_top()
    if not rows:
        await update.message.reply_text("Hali hech kim o'ynamagan. Birinchi bo'ling! 🎮")
        return

    medals = ["🥇", "🥈", "🥉"]
    lines = []
    for i, (name, score, games_p, correct, total_q) in enumerate(rows):
        medal = medals[i] if i < 3 else f"{i+1}."
        acc = round(correct / total_q * 100, 0) if total_q > 0 else 0
        lines.append(f"{medal} *{name}*: {score} ball | {games_p} o'yin | {acc}% aniqlik")

    await update.message.reply_text(
        "🏆 *Global Reyting — Top 10*\n\n" + "\n".join(lines),
        parse_mode="Markdown",
    )


async def mystats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    stats = get_user_stats(user.id)
    if not stats:
        await update.message.reply_text("Siz hali o'ynamagansiz. /quiz bilan boshlang!")
        return

    await update.message.reply_text(
        f"📊 *{stats['username']} — Statistika*\n\n"
        f"🏆 Jami ball: *{stats['total_score']}*\n"
        f"🎮 O'yinlar: *{stats['games_played']}*\n"
        f"✅ To'g'ri javoblar: *{stats['correct']}/{stats['total_q']}*\n"
        f"🎯 Aniqlik: *{stats['accuracy']}%*",
        parse_mode="Markdown",
    )


async def stop_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user
    games = get_games(context)

    # ✅ FIX: "finished" bo'lsa ham yo'q deb hisoblash
    if chat_id not in games or games[chat_id]["status"] == "finished":
        await update.message.reply_text("Hozir aktiv o'yin yo'q.")
        return

    game = games[chat_id]

    is_creator = user.id == game["creator_id"]
    try:
        member = await context.bot.get_chat_member(chat_id, user.id)
        is_admin = member.status in ("administrator", "creator")
    except TelegramError:
        is_admin = False

    if not is_creator and not is_admin:
        await update.message.reply_text("⚠️ Faqat o'yin yaratuvchisi yoki admin to'xtatishi mumkin!")
        return

    # ✅ FIX: Avval status o'zgartir, keyin joblarni bekor qil, keyin o'chir
    game["status"] = "finished"
    _cancel_jobs(context, chat_id)
    del games[chat_id]

    await update.message.reply_text("🛑 O'yin to'xtatildi.")


# ──────────────────────────────────────────────
# Callback query handler'lar
# ──────────────────────────────────────────────

async def category_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    cat_key = query.data[4:]  # "cat_" ni olib tashlash
    if cat_key not in CATEGORIES:
        return

    cat_name, _ = CATEGORIES[cat_key]

    keyboard = [
        [InlineKeyboardButton(f"🔢 {n} savol", callback_data=f"cnt_{cat_key}_{n}")
         for n in QUESTION_COUNTS[:2]],
        [InlineKeyboardButton(f"🔢 {n} savol", callback_data=f"cnt_{cat_key}_{n}")
         for n in QUESTION_COUNTS[2:]],
    ]

    await query.edit_message_text(
        f"✅ *{cat_name}* tanlandi!\n\n❓ *Nechta savol bo'lsin?*",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown",
    )


async def count_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    # ✅ FIX: "cnt_geo_10" → rsplit bilan oxiridan ajratish
    raw = query.data[4:]                      # "geo_10"
    last_underscore = raw.rfind("_")
    cat_key = raw[:last_underscore]           # "geo"
    count   = int(raw[last_underscore + 1:]) # 10

    if cat_key not in CATEGORIES:
        await query.answer("⚠️ Kategoriya topilmadi!", show_alert=True)
        return

    cat_name, cat_id = CATEGORIES[cat_key]
    chat_id = update.effective_chat.id
    user = update.effective_user
    games = get_games(context)

    games[chat_id] = {
        "chat_id":       chat_id,
        "creator_id":    user.id,
        "category":      cat_key,
        "category_id":   cat_id,
        "category_name": cat_name,
        "total":         count,
        "current":       0,
        "questions":     [],
        "players": {
            user.id: {"name": user.first_name, "score": 0, "correct": 0,
                      "total_questions": count, "answered_current": False}
        },
        "status":               "waiting",
        "lobby_message_id":     None,
        "current_poll_id":      None,
        "current_poll_msg_id":  None,
        "correct_option":       None,
        "question_start_time":  None,
    }

    keyboard = [
        [InlineKeyboardButton("✋ Qo'shilish", callback_data="join_game")],
        [InlineKeyboardButton("▶️ O'yinni boshlash", callback_data="start_game")],
    ]

    msg = await query.edit_message_text(
        build_lobby_text(games[chat_id]),
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown",
    )
    games[chat_id]["lobby_message_id"] = msg.message_id


async def join_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = update.effective_chat.id
    user = update.effective_user
    games = get_games(context)

    if chat_id not in games or games[chat_id]["status"] != "waiting":
        await query.answer("⚠️ O'yin mavjud emas yoki boshlangan!", show_alert=True)
        return

    game = games[chat_id]

    if user.id in game["players"]:
        await query.answer("✅ Siz allaqachon qo'shilgansiz!", show_alert=False)
        return

    game["players"][user.id] = {
        "name": user.first_name,
        "score": 0,
        "correct": 0,
        "total_questions": game["total"],
        "answered_current": False,
    }

    await query.answer(f"✋ {user.first_name} qo'shildi!")

    keyboard = [
        [InlineKeyboardButton("✋ Qo'shilish", callback_data="join_game")],
        [InlineKeyboardButton("▶️ O'yinni boshlash", callback_data="start_game")],
    ]
    try:
        await query.edit_message_text(
            build_lobby_text(game),
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown",
        )
    except TelegramError:
        pass


async def start_game_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = update.effective_chat.id
    user = update.effective_user
    games = get_games(context)

    if chat_id not in games:
        await query.answer("O'yin topilmadi!", show_alert=True)
        return

    game = games[chat_id]

    if user.id != game["creator_id"]:
        await query.answer("⚠️ Faqat yaratuvchi boshlashi mumkin!", show_alert=True)
        return

    if game["status"] != "waiting":
        await query.answer("O'yin allaqachon boshlangan!", show_alert=True)
        return

    await query.answer("🚀 O'yin boshlanmoqda!")
    await query.edit_message_text(
        f"⏳ *Savollar yuklanmoqda...*\n\n"
        f"📁 {game['category_name']} | ❓ {game['total']} ta savol",
        parse_mode="Markdown",
    )

    questions = await fetch_questions(game["category_id"], game["total"])

    if not questions:
        await context.bot.send_message(
            chat_id,
            "❌ Savollarni yuklab bo'lmadi. Internetni tekshiring va /quiz bilan qayta urinib ko'ring."
        )
        if chat_id in games:
            del games[chat_id]
        return

    game["questions"] = questions
    game["status"] = "running"

    players_list = ", ".join(p["name"] for p in game["players"].values())
    await context.bot.send_message(
        chat_id,
        f"🎮 *O'YIN BOSHLANDI!*\n\n"
        f"👥 Ishtirokchilar: {players_list}\n"
        f"⚡ Tezroq javob bering — bonus ball oling!\n\n"
        f"Tayyormisiz? 3... 2... 1... 🚀",
        parse_mode="Markdown",
    )

    await asyncio.sleep(2)
    await send_next_question(context, chat_id)


# ──────────────────────────────────────────────
# O'yin logikasi
# ──────────────────────────────────────────────

async def send_next_question(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    games = get_games(context)
    if chat_id not in games:
        return

    game = games[chat_id]

    # ✅ FIX: O'yin to'xtatilgan bo'lsa chiqish
    if game["status"] != "running":
        return

    if game["current"] >= game["total"]:
        await finish_game(context, chat_id)
        return

    q_idx = game["current"]
    q = game["questions"][q_idx]

    for player in game["players"].values():
        player["answered_current"] = False

    game["question_start_time"] = time.time()

    try:
        msg = await context.bot.send_poll(
            chat_id=chat_id,
            question=f"❓ {q_idx + 1}/{game['total']}: {q['question']}",
            options=q["answers"],
            type="quiz",
            correct_option_id=q["correct_idx"],
            is_anonymous=False,
            open_period=QUESTION_TIMEOUT,
            explanation=f"✅ To'g'ri: {q['answers'][q['correct_idx']]}",
        )
    except TelegramError as e:
        logger.error(f"Poll yuborishda xato: {e}")
        return

    game["current_poll_id"]     = msg.poll.id
    game["current_poll_msg_id"] = msg.message_id
    game["correct_option"]      = q["correct_idx"]

    get_poll_map(context)[msg.poll.id] = chat_id

    # Eski joblarni bekor qilib yangi yaratish
    _cancel_jobs(context, chat_id)
    if context.job_queue is None:
        logger.error("JobQueue yo'q! 'pip install python-telegram-bot[job-queue]' bajaring.")
        return
    context.job_queue.run_once(
        _next_question_job,
        when=QUESTION_TIMEOUT + 2,
        data={"chat_id": chat_id, "q_idx": q_idx},
        name=f"nq_{chat_id}",
    )


async def _next_question_job(context: ContextTypes.DEFAULT_TYPE):
    """Timer tugagach keyingi savolga o'tish"""
    data = context.job.data
    chat_id = data["chat_id"]
    q_idx   = data["q_idx"]

    games = get_games(context)
    if chat_id not in games:
        return

    game = games[chat_id]

    # ✅ FIX: O'yin to'xtatilgan yoki eski job bo'lsa o'tkazib yuborish
    if game["status"] != "running":
        return
    if game["current"] != q_idx:
        return

    game["current"] += 1
    remaining = game["total"] - game["current"]

    scoreboard = build_scoreboard(game["players"], game["total"], show_correct=False)

    if remaining > 0:
        await context.bot.send_message(
            chat_id,
            f"📊 *Joriy natijalar:*\n{scoreboard}\n\n"
            f"⏭ Keyingi savol {SCORE_DISPLAY_PAUSE} soniyada...",
            parse_mode="Markdown",
        )
        # ✅ FIX: asyncio.sleep o'rniga job_queue — to'g'ri asinxron oqim
        if context.job_queue is None:
            return
        context.job_queue.run_once(
            _send_next_question_job,
            when=SCORE_DISPLAY_PAUSE,
            data={"chat_id": chat_id},
            name=f"delay_{chat_id}",
        )
    else:
        await finish_game(context, chat_id)


async def _send_next_question_job(context: ContextTypes.DEFAULT_TYPE):
    """Pauza tugagach keyingi savolni yuborish"""
    data = context.job.data
    chat_id = data["chat_id"]

    games = get_games(context)
    if chat_id not in games:
        return
    if games[chat_id]["status"] != "running":
        return

    await send_next_question(context, chat_id)


async def poll_answer_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Foydalanuvchi poll javobini qayta ishlash"""
    answer  = update.poll_answer
    poll_id = answer.poll_id
    user    = answer.user

    poll_map = get_poll_map(context)
    if poll_id not in poll_map:
        return

    chat_id = poll_map[poll_id]
    games   = get_games(context)
    if chat_id not in games:
        return

    game = games[chat_id]
    if game.get("current_poll_id") != poll_id:
        return

    if user.id not in game["players"]:
        game["players"][user.id] = {
            "name": user.first_name,
            "score": 0,
            "correct": 0,
            "total_questions": game["total"],
            "answered_current": False,
        }

    player = game["players"][user.id]
    if player["answered_current"]:
        return

    player["answered_current"] = True

    if answer.option_ids and answer.option_ids[0] == game["correct_option"]:
        elapsed      = time.time() - game["question_start_time"]
        speed_bonus  = max(0, int(MAX_SPEED_BONUS * (1 - elapsed / QUESTION_TIMEOUT)))
        earned       = BASE_POINTS + speed_bonus
        player["score"]   += earned
        player["correct"] += 1


async def finish_game(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    """O'yinni yakunlash va natijalarni ko'rsatish"""
    games = get_games(context)
    if chat_id not in games:
        return

    game = games[chat_id]
    game["status"] = "finished"

    sorted_p = sorted(game["players"].items(), key=lambda x: x[1]["score"], reverse=True)
    medals   = ["🥇", "🥈", "🥉"]
    lines    = []

    for i, (_, p) in enumerate(sorted_p):
        medal = medals[i] if i < 3 else f"{i+1}."
        acc   = round(p["correct"] / game["total"] * 100)
        lines.append(
            f"{medal} *{p['name']}*: {p['score']} ball  "
            f"({p['correct']}/{game['total']} ✅  {acc}%)"
        )

    winner = sorted_p[0][1]["name"] if sorted_p else "—"

    await context.bot.send_message(
        chat_id,
        f"🏁 *O'YIN TUGADI!*\n\n"
        f"📁 {game['category_name']} | ❓ {game['total']} savol\n\n"
        f"*🏆 Yakuniy natijalar:*\n"
        + "\n".join(lines)
        + f"\n\n🎉 G'olib: *{winner}* — Tabriklaymiz!\n\n"
          f"🔄 Yangi o'yin: /quiz\n"
          f"🏆 Global reyting: /top",
        parse_mode="Markdown",
    )

    save_game_results(game["players"], chat_id, game["category_name"])

    _cancel_jobs(context, chat_id)
    if chat_id in games:
        del games[chat_id]


def _cancel_jobs(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    """Chat uchun rejalashtirilgan barcha ishlarni bekor qilish"""
    if context.job_queue is None:
        logger.warning("JobQueue o'rnatilmagan! 'pip install python-telegram-bot[job-queue]' bajaring.")
        return
    for job_name in [f"nq_{chat_id}", f"delay_{chat_id}"]:
        for job in context.job_queue.get_jobs_by_name(job_name):
            job.schedule_removal()

