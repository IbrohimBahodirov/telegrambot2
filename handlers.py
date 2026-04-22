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
# Вспомогательные функции
# ──────────────────────────────────────────────

def get_games(context: ContextTypes.DEFAULT_TYPE) -> dict:
    if "games" not in context.bot_data:
        context.bot_data["games"] = {}
    return context.bot_data["games"]


def get_poll_map(context: ContextTypes.DEFAULT_TYPE) -> dict:
    """poll_id → chat_id карта"""
    if "poll_map" not in context.bot_data:
        context.bot_data["poll_map"] = {}
    return context.bot_data["poll_map"]


def build_lobby_text(game: dict) -> str:
    players_text = "\n".join(
        f"  • {p['name']}" for p in game["players"].values()
    )
    return (
        f"🎮 *Новая игра Quiz!*\n\n"
        f"📁 Категория: *{game['category_name']}*\n"
        f"❓ Количество вопросов: *{game['total']} шт.*\n"
        f"⏱ Время на вопрос: *{QUESTION_TIMEOUT} секунд*\n"
        f"⚡ Бонус за скорость: *+{MAX_SPEED_BONUS} очков*\n\n"
        f"👥 *Участники ({len(game['players'])} чел.):*\n"
        f"{players_text}\n\n"
        f"Нажмите ✋ чтобы присоединиться!\n"
        f"Создатель нажимает ▶️ для начала."
    )


def build_scoreboard(players: dict, total_q: int, show_correct: bool = True) -> str:
    sorted_p = sorted(players.items(), key=lambda x: x[1]["score"], reverse=True)
    medals = ["🥇", "🥈", "🥉"]
    lines = []
    for i, (_, p) in enumerate(sorted_p):
        medal = medals[i] if i < 3 else f"*{i+1}.*"
        extra = f" ({p['correct']}/{total_q} ✅)" if show_correct else ""
        lines.append(f"{medal} {p['name']}: *{p['score']}* очков{extra}")
    return "\n".join(lines)


# ──────────────────────────────────────────────
# Основные команды
# ──────────────────────────────────────────────

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "👋 Добро пожаловать в *Quiz Bot*!\n\n"
        "🌐 Вопросы на *разные темы* — берутся из интернета!\n\n"
        "🎮 *Команды:*\n"
        "├ /quiz — Начать новую игру\n"
        "├ /top — Глобальный рейтинг 🏆\n"
        "├ /mystats — Моя статистика 📊\n"
        "├ /stop — Остановить игру 🛑\n"
        "└ /help — Правила ℹ️\n\n"
        "📌 *Добавьте в группу и соревнуйтесь с друзьями!*"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📖 *Правила игры*\n\n"
        "1️⃣ Введите команду /quiz\n"
        "2️⃣ Выберите категорию и количество вопросов\n"
        "3️⃣ Участники нажимают ✋ чтобы войти\n"
        "4️⃣ Создатель нажимает ▶️ для начала\n"
        "5️⃣ На каждый вопрос *20 секунд*\n\n"
        "🏆 *Система очков:*\n"
        f"• Правильный ответ: *{BASE_POINTS} очков*\n"
        f"• Бонус за скорость: *+{MAX_SPEED_BONUS} очков* (быстрее = больше)\n"
        "• Неправильный ответ: *0 очков*\n\n"
        "💡 *Совет:* Отвечайте быстрее — не теряйте бонус!"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def quiz_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    games = get_games(context)

    if chat_id in games and games[chat_id]["status"] != "finished":
        await update.message.reply_text(
            "⚠️ В этом чате уже есть активная игра!\n"
            "Для остановки: /stop"
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
        "🎯 *Выберите категорию:*",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown",
    )


async def top_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = get_global_top()
    if not rows:
        await update.message.reply_text("Ещё никто не играл. Будьте первым! 🎮")
        return

    medals = ["🥇", "🥈", "🥉"]
    lines = []
    for i, (name, score, games_p, correct, total_q) in enumerate(rows):
        medal = medals[i] if i < 3 else f"{i+1}."
        acc = round(correct / total_q * 100, 0) if total_q > 0 else 0
        lines.append(f"{medal} *{name}*: {score} очков | {games_p} игр | {acc}% точность")

    await update.message.reply_text(
        "🏆 *Глобальный рейтинг — Топ 10*\n\n" + "\n".join(lines),
        parse_mode="Markdown",
    )


async def mystats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    stats = get_user_stats(user.id)
    if not stats:
        await update.message.reply_text("Вы ещё не играли. Начните с /quiz!")
        return

    await update.message.reply_text(
        f"📊 *{stats['username']} — Статистика*\n\n"
        f"🏆 Всего очков: *{stats['total_score']}*\n"
        f"🎮 Игр сыграно: *{stats['games_played']}*\n"
        f"✅ Правильных ответов: *{stats['correct']}/{stats['total_q']}*\n"
        f"🎯 Точность: *{stats['accuracy']}%*",
        parse_mode="Markdown",
    )


async def stop_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user
    games = get_games(context)

    if chat_id not in games or games[chat_id]["status"] == "finished":
        await update.message.reply_text("Сейчас нет активной игры.")
        return

    game = games[chat_id]

    is_creator = user.id == game["creator_id"]
    try:
        member = await context.bot.get_chat_member(chat_id, user.id)
        is_admin = member.status in ("administrator", "creator")
    except TelegramError:
        is_admin = False

    if not is_creator and not is_admin:
        await update.message.reply_text("⚠️ Остановить игру может только создатель или админ!")
        return

    game["status"] = "finished"
    _cancel_jobs(context, chat_id)
    del games[chat_id]

    await update.message.reply_text("🛑 Игра остановлена.")


# ──────────────────────────────────────────────
# Callback query handlers
# ──────────────────────────────────────────────

async def category_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    cat_key = query.data[4:]
    if cat_key not in CATEGORIES:
        return

    cat_name, _ = CATEGORIES[cat_key]

    keyboard = [
        [InlineKeyboardButton(f"🔢 {n} вопросов", callback_data=f"cnt_{cat_key}_{n}")
         for n in QUESTION_COUNTS[:2]],
        [InlineKeyboardButton(f"🔢 {n} вопросов", callback_data=f"cnt_{cat_key}_{n}")
         for n in QUESTION_COUNTS[2:]],
    ]

    await query.edit_message_text(
        f"✅ *{cat_name}* выбрана!\n\n❓ *Сколько вопросов?*",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown",
    )


async def count_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    raw = query.data[4:]
    last_underscore = raw.rfind("_")
    cat_key = raw[:last_underscore]
    count   = int(raw[last_underscore + 1:])

    if cat_key not in CATEGORIES:
        await query.answer("⚠️ Категория не найдена!", show_alert=True)
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
        [InlineKeyboardButton("✋ Присоединиться", callback_data="join_game")],
        [InlineKeyboardButton("▶️ Начать игру", callback_data="start_game")],
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
        await query.answer("⚠️ Игра не найдена или уже началась!", show_alert=True)
        return

    game = games[chat_id]

    if user.id in game["players"]:
        await query.answer("✅ Вы уже в игре!", show_alert=False)
        return

    game["players"][user.id] = {
        "name": user.first_name,
        "score": 0,
        "correct": 0,
        "total_questions": game["total"],
        "answered_current": False,
    }

    await query.answer(f"✋ {user.first_name} присоединился!")

    keyboard = [
        [InlineKeyboardButton("✋ Присоединиться", callback_data="join_game")],
        [InlineKeyboardButton("▶️ Начать игру", callback_data="start_game")],
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
        await query.answer("Игра не найдена!", show_alert=True)
        return

    game = games[chat_id]

    if user.id != game["creator_id"]:
        await query.answer("⚠️ Начать игру может только создатель!", show_alert=True)
        return

    if game["status"] != "waiting":
        await query.answer("Игра уже началась!", show_alert=True)
        return

    await query.answer("🚀 Игра начинается!")
    await query.edit_message_text(
        f"⏳ *Загрузка вопросов...*\n\n"
        f"📁 {game['category_name']} | ❓ {game['total']} вопросов",
        parse_mode="Markdown",
    )

    questions = await fetch_questions(game["category_id"], game["total"])

    if not questions:
        await context.bot.send_message(
            chat_id,
            "❌ Не удалось загрузить вопросы. Проверьте интернет и попробуйте /quiz снова."
        )
        if chat_id in games:
            del games[chat_id]
        return

    game["questions"] = questions
    game["status"] = "running"

    players_list = ", ".join(p["name"] for p in game["players"].values())
    await context.bot.send_message(
        chat_id,
        f"🎮 *ИГРА НАЧАЛАСЬ!*\n\n"
        f"👥 Участники: {players_list}\n"
        f"⚡ Отвечайте быстрее — получайте бонус!\n\n"
        f"Готовы? 3... 2... 1... 🚀",
        parse_mode="Markdown",
    )

    await asyncio.sleep(2)
    await send_next_question(context, chat_id)


# ──────────────────────────────────────────────
# Логика игры
# ──────────────────────────────────────────────

async def send_next_question(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    games = get_games(context)
    if chat_id not in games:
        return

    game = games[chat_id]

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
            explanation=f"✅ Правильно: {q['answers'][q['correct_idx']]}",
        )
    except TelegramError as e:
        logger.error(f"Ошибка отправки опроса: {e}")
        return

    game["current_poll_id"]     = msg.poll.id
    game["current_poll_msg_id"] = msg.message_id
    game["correct_option"]      = q["correct_idx"]

    get_poll_map(context)[msg.poll.id] = chat_id

    _cancel_jobs(context, chat_id)
    if context.job_queue is None:
        logger.error("JobQueue не установлен! Выполните: pip install python-telegram-bot[job-queue]")
        return
    context.job_queue.run_once(
        _next_question_job,
        when=QUESTION_TIMEOUT + 2,
        data={"chat_id": chat_id, "q_idx": q_idx},
        name=f"nq_{chat_id}",
    )


async def _next_question_job(context: ContextTypes.DEFAULT_TYPE):
    """Переход к следующему вопросу после таймера"""
    data = context.job.data
    chat_id = data["chat_id"]
    q_idx   = data["q_idx"]

    games = get_games(context)
    if chat_id not in games:
        return

    game = games[chat_id]

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
            f"📊 *Текущий счёт:*\n{scoreboard}\n\n"
            f"⏭ Следующий вопрос через {SCORE_DISPLAY_PAUSE} сек...",
            parse_mode="Markdown",
        )
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
    """Отправка следующего вопроса после паузы"""
    data = context.job.data
    chat_id = data["chat_id"]

    games = get_games(context)
    if chat_id not in games:
        return
    if games[chat_id]["status"] != "running":
        return

    await send_next_question(context, chat_id)


async def poll_answer_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ответа пользователя на опрос"""
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

    # Agar barcha o'yinchilar javob bergan bo'lsa — 2 soniyada keyingi savolga o'tish
    all_answered = all(p["answered_current"] for p in game["players"].values())
    if all_answered:
        _cancel_jobs(context, chat_id)
        if context.job_queue is not None:
            context.job_queue.run_once(
                _next_question_job,
                when=2,
                data={"chat_id": chat_id, "q_idx": game["current"]},
                name=f"nq_{chat_id}",
            )


async def finish_game(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    """Завершение игры и показ результатов"""
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
            f"{medal} *{p['name']}*: {p['score']} очков  "
            f"({p['correct']}/{game['total']} ✅  {acc}%)"
        )

    winner = sorted_p[0][1]["name"] if sorted_p else "—"

    await context.bot.send_message(
        chat_id,
        f"🏁 *ИГРА ОКОНЧЕНА!*\n\n"
        f"📁 {game['category_name']} | ❓ {game['total']} вопросов\n\n"
        f"*🏆 Итоговые результаты:*\n"
        + "\n".join(lines)
        + f"\n\n🎉 Победитель: *{winner}* — Поздравляем!\n\n"
          f"🔄 Новая игра: /quiz\n"
          f"🏆 Глобальный рейтинг: /top",
        parse_mode="Markdown",
    )

    save_game_results(game["players"], chat_id, game["category_name"])

    _cancel_jobs(context, chat_id)
    if chat_id in games:
        del games[chat_id]


def _cancel_jobs(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    """Отмена всех запланированных задач для чата"""
    if context.job_queue is None:
        logger.warning("JobQueue не установлен! Выполните: pip install python-telegram-bot[job-queue]")
        return
    for job_name in [f"nq_{chat_id}", f"delay_{chat_id}"]:
        for job in context.job_queue.get_jobs_by_name(job_name):
            job.schedule_removal()
