import sys
import json
import tempfile
from pathlib import Path
from datetime import datetime
from filelock import FileLock

from config.settings import CACHE_DIR, MIMO_DAILY_LIMIT, MIMO_RPM_LIMIT
from src.logger import logger

RATE_FILE = Path(CACHE_DIR) / "rate_limit.json"
LOCK_FILE = Path(tempfile.gettempdir()) / "dp_shw_rate.lock"

def check_and_increment() -> bool:
    """
    Перевіряє, чи не вичерпано ліміти MiMo API з атомарним блокуванням.
    """
    now = datetime.now()
    current_date = now.strftime("%Y-%m-%d")
    current_minute = now.strftime("%H:%M")

    # Створюємо батьківську директорію якщо її немає
    RATE_FILE.parent.mkdir(parents=True, exist_ok=True)

    lock = FileLock(str(LOCK_FILE), timeout=5)
    try:
        with lock:
            # Дефолтний стан
            state = {"date": current_date, "daily_count": 0, "minute_counts": {}}

            # Безпечне читання
            if RATE_FILE.exists():
                try:
                    with open(RATE_FILE, "r", encoding="utf-8") as f:
                        state = json.load(f)
                except Exception:
                    pass  # Якщо файл пошкоджений, почнемо з нуля

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
            if daily >= MIMO_DAILY_LIMIT:
                logger.warning(f"🛑 Досягнуто денний ліміт MiMo ({MIMO_DAILY_LIMIT}).")
                return False
                
            if minute >= MIMO_RPM_LIMIT:
                logger.warning(f"🛑 Досягнуто хвилинний ліміт MiMo ({MIMO_RPM_LIMIT} req/min).")
                return False

            # Інкремент
            state["daily_count"] = daily + 1
            state["minute_counts"][current_minute] = minute + 1

            # Атомарний запис через temp + replace
            temp_file = RATE_FILE.with_suffix('.tmp')
            try:
                with open(temp_file, "w", encoding="utf-8") as f:
                    json.dump(state, f)
                temp_file.replace(RATE_FILE)
            except Exception as e:
                logger.error(f"Не вдалося записати лічильник: {e}")
                
            return True
            
    except Exception as e:
        logger.error(f"Помилка блокування RateLimiter: {e}")
        # Fail-open if lock fails (to prevent complete downtime, but you can change this)
        return True
