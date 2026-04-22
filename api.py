import aiohttp
import random
import logging
from urllib.parse import unquote

logger = logging.getLogger(__name__)

OPENTDB_URL = "https://opentdb.com/api.php"


async def fetch_questions(category_id: int, amount: int) -> list[dict]:
    """
    OpenTrivia DB dan savollar yuklash.
    Qaytaradi: [{"question": str, "answers": list, "correct_idx": int}, ...]
    """
    params = {
        "amount":   amount,
        "category": category_id,
        "type":     "multiple",
        "encode":   "url3986",
        "lang":     "ru",
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

        questions = []
        for q in data["results"]:
            question  = unquote(q["question"])
            correct   = unquote(q["correct_answer"])
            incorrect = [unquote(a) for a in q["incorrect_answers"]]

            answers = incorrect + [correct]
            random.shuffle(answers)
            correct_idx = answers.index(correct)

            # Telegram poll: savol max 300, variant max 100 belgi
            question = question[:295]
            answers  = [a[:95] for a in answers]

            questions.append({
                "question":    question,
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
