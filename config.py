import os
from dotenv import load_dotenv

load_dotenv()

TOKEN = "8679150899:AAEC42nNDpuBsDYAARKCWtYroem5vpOVBRQ"

QUESTION_TIMEOUT = 20       # har bir savol uchun vaqt (soniya)
LOBBY_TIMEOUT = 60        # lobby kutish vaqti (soniya)
SCORE_DISPLAY_PAUSE = 1    # natijalar ko'rsatilgandan keyingi pauza

# OpenTDB kategoriyalari
CATEGORIES =  {
"гео": ("🌍 География", 22),
"история": ("📚 История", 23),
"наука": ("🔬 Наука и природа", 17),
"математика": ("➗ Математика", 19),
"зоопарк": ("🐾 Животные", 27),
"компьютер": ("💻 Компьютер", 18),
"спорт": ("⚽ Спорт", 21),
"кино": ("🎬 Фильмы", 11),
"музыка": ("🎵 Музыка", 12),
"знаменитости": ("🌟 Знаменитости", 26),
}

QUESTION_COUNTS = [5, 10, 15, 20]

# Ball tizimi
BASE_POINTS = 10
MAX_SPEED_BONUS = 10
