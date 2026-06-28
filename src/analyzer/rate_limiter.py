import sys
import json
from pathlib import Path
from datetime import datetime

# Гарантуємо правильні шляхи імпорту
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import CACHE_DIR, GEMINI_DAILY_LIMIT, GEMINI_RPM_LIMIT
from src.logger import logger

RATE_FILE = Path(CACHE_DIR) / "rate_limit.json"

def check_and_increment() -> bool:
    """
    Перевіряє, чи не вичерпано ліміти Gemini API.
    Якщо ліміт дозволяє - інкрементує лічильник та повертає True.
    Якщо вичерпано - повертає False.
    """
    now = datetime.now()
    current_date = now.strftime("%Y-%m-%d")
    current_minute = now.strftime("%H:%M")

    # Дефолтний стан
    state = {"date": current_date, "daily_count": 0, "minute_counts": {}}

    # Безпечне читання
    if RATE_FILE.exists():
        try:
            with open(RATE_FILE, "r", encoding="utf-8") as f:
                state = json.load(f)
        except Exception:
            pass  # Якщо файл пошкоджений, почнемо з нуля (це безпечніше, ніж падіння)

    # Скидання лічильника опівночі
    if state.get("date") != current_date:
        state = {"date": current_date, "daily_count": 0, "minute_counts": {}}

    # Очищуємо стару статистику хвилин для економії місця
    state["minute_counts"] = {
        k: v for k, v in state.get("minute_counts", {}).items() 
        if k == current_minute
    }

    daily = state.get("daily_count", 0)
    minute = state["minute_counts"].get(current_minute, 0)

    # Перевірка лімітів
    if daily >= GEMINI_DAILY_LIMIT:
        logger.warning(f"🛑 Досягнуто денний ліміт Gemini ({GEMINI_DAILY_LIMIT}).")
        return False
        
    if minute >= GEMINI_RPM_LIMIT:
        logger.warning(f"🛑 Досягнуто хвилинний ліміт Gemini ({GEMINI_RPM_LIMIT} req/min).")
        return False

    # Інкремент
    state["daily_count"] = daily + 1
    state["minute_counts"][current_minute] = minute + 1

    # Безпечний запис
    try:
        with open(RATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f)
    except Exception as e:
        logger.error(f"Не вдалося записати лічильник: {e}")

    return True
