import aiohttp
import asyncio
import random
import logging
from urllib.parse import unquote
from concurrent.futures import ThreadPoolExecutor
from deep_translator import GoogleTranslator

logger = logging.getLogger(__name__)

OPENTDB_URL = "https://opentdb.com/api.php"

# Thread pool — tarjima uchun (deep_translator sinxron)
_executor = ThreadPoolExecutor(max_workers=10)


def _translate_one(text: str) -> str:
    """Bitta matnni rus tiliga tarjima qilish"""
    try:
        return GoogleTranslator(source="en", target="ru").translate(text) or text
    except Exception:
        return text  # tarjima bo'lmasa asl matn


async def _translate_all_parallel(texts: list) -> list:
    """Barcha matnlarni parallel thread'larda tarjima qilish"""
    loop = asyncio.get_event_loop()
    tasks = [loop.run_in_executor(_executor, _translate_one, t) for t in texts]
    return await asyncio.gather(*tasks)


async def fetch_questions(category_id: int, amount: int) -> list:
    """
    OpenTrivia DB dan savollar yuklash va parallel tarjima qilish.
    Qaytaradi: [{"question": str, "answers": list, "correct_idx": int}, ...]
    """
    params = {
        "amount":   amount,
        "category": category_id,
        "type":     "multiple",
        "encode":   "url3986",
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                OPENTDB_URL,
                params=params,
                timeout=aiohttp.ClientTimeout(total=12)
            ) as resp:
                data = await resp.json()

        if data.get("response_code") != 0:
            logger.warning(f"OpenTDB response_code={data.get('response_code')}")
            return []

        # Barcha savol va javoblarni olish
        raw = []
        for q in data["results"]:
            question  = unquote(q["question"])
            correct   = unquote(q["correct_answer"])
            incorrect = [unquote(a) for a in q["incorrect_answers"]]
            raw.append((question, correct, incorrect))

        # Tarjima uchun barcha matnlarni yig'ish (savol + 1 to'g'ri + 3 noto'g'ri)
        all_texts = []
        for question, correct, incorrect in raw:
            all_texts.append(question)
            all_texts.append(correct)
            all_texts.extend(incorrect)

        # PARALLEL tarjima — hammasi bir vaqtda
        translated = await _translate_all_parallel(all_texts)

        # Tarjima qilingan matnlarni savollar ichiga joylashtirish
        questions = []
        idx = 0
        for _ in raw:
            t_question  = translated[idx];      idx += 1
            t_correct   = translated[idx];      idx += 1
            t_incorrect = translated[idx:idx+3]; idx += 3

            answers = t_incorrect + [t_correct]
            random.shuffle(answers)
            correct_idx = answers.index(t_correct)

            t_question = t_question[:295]
            answers    = [a[:95] for a in answers]

            questions.append({
                "question":    t_question,
                "answers":     answers,
                "correct_idx": correct_idx,
            })

        return questions

    except aiohttp.ClientError as e:
        logger.error(f"Network error fetching questions: {e}")
        return []
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return []
