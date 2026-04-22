import sqlite3
import logging

logger = logging.getLogger(__name__)
# database.py ichida
DB_PATH = "/app/data/quiz_scores.db"


def init_db():
    """Ma'lumotlar bazasini yaratish"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS leaderboard (
            user_id     INTEGER PRIMARY KEY,
            username    TEXT    NOT NULL,
            total_score INTEGER DEFAULT 0,
            games_played INTEGER DEFAULT 0,
            correct_answers INTEGER DEFAULT 0,
            total_questions INTEGER DEFAULT 0
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS game_history (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id     INTEGER,
            category    TEXT,
            players     INTEGER,
            winner_name TEXT,
            winner_score INTEGER,
            played_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()
    logger.info("Database initialized ✅")


def save_game_results(players: dict, chat_id: int, category: str):
    """O'yin natijalarini saqlash"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    for user_id, data in players.items():
        c.execute("""
            INSERT INTO leaderboard (user_id, username, total_score, games_played, correct_answers, total_questions)
            VALUES (?, ?, ?, 1, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username        = excluded.username,
                total_score     = total_score + excluded.total_score,
                games_played    = games_played + 1,
                correct_answers = correct_answers + excluded.correct_answers,
                total_questions = total_questions + excluded.total_questions
        """, (
            user_id,
            data["name"],
            data["score"],
            data.get("correct", 0),
            data.get("total_questions", 0),
        ))

    # O'yin tarixiga yozish
    sorted_p = sorted(players.items(), key=lambda x: x[1]["score"], reverse=True)
    winner = sorted_p[0][1] if sorted_p else {"name": "—", "score": 0}
    c.execute("""
        INSERT INTO game_history (chat_id, category, players, winner_name, winner_score)
        VALUES (?, ?, ?, ?, ?)
    """, (chat_id, category, len(players), winner["name"], winner["score"]))

    conn.commit()
    conn.close()


def get_global_top(limit: int = 10) -> list:
    """Global reytingni olish"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT username, total_score, games_played, correct_answers, total_questions
        FROM leaderboard
        ORDER BY total_score DESC
        LIMIT ?
    """, (limit,))
    rows = c.fetchall()
    conn.close()
    return rows


def get_user_stats(user_id: int) -> dict | None:
    """Foydalanuvchi statistikasini olish"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT username, total_score, games_played, correct_answers, total_questions
        FROM leaderboard WHERE user_id = ?
    """, (user_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        return None
    return {
        "username": row[0],
        "total_score": row[1],
        "games_played": row[2],
        "correct": row[3],
        "total_q": row[4],
        "accuracy": round(row[3] / row[4] * 100, 1) if row[4] > 0 else 0,
    }
