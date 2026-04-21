import logging
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    PollAnswerHandler,
)

from config import TOKEN
from database import init_db
from handlers import (
    start_cmd,
    help_cmd,
    quiz_cmd,
    top_cmd,
    mystats_cmd,
    stop_cmd,
    category_callback,
    count_callback,
    join_callback,
    start_game_callback,
    poll_answer_handler,
)

logging.basicConfig(
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def main():
    init_db()

    app = Application.builder().token(TOKEN).build()

    # Komandalar
    app.add_handler(CommandHandler("start",    start_cmd))
    app.add_handler(CommandHandler("help",     help_cmd))
    app.add_handler(CommandHandler("quiz",     quiz_cmd))
    app.add_handler(CommandHandler("top",      top_cmd))
    app.add_handler(CommandHandler("mystats",  mystats_cmd))
    app.add_handler(CommandHandler("stop",     stop_cmd))

    # Callback query'lar
    app.add_handler(CallbackQueryHandler(category_callback,   pattern=r"^cat_"))
    app.add_handler(CallbackQueryHandler(count_callback,      pattern=r"^cnt_"))
    app.add_handler(CallbackQueryHandler(join_callback,       pattern=r"^join_game$"))
    app.add_handler(CallbackQueryHandler(start_game_callback, pattern=r"^start_game$"))

    # Poll javoblari
    app.add_handler(PollAnswerHandler(poll_answer_handler))

    logger.info("🤖 Запущен Quiz Bot!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
