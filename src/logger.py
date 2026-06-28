import sys
from pathlib import Path
import os
from loguru import logger

# Гарантуємо правильні шляхи імпорту
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import LOG_PATH

# Створюємо директорію для логів, якщо вона відсутня
Path(LOG_PATH).parent.mkdir(parents=True, exist_ok=True)

# --- АНТИКРИХКА ІНІЦІАЛІЗАЦІЯ SENTRY ---
SENTRY_DSN = os.getenv("SENTRY_DSN")

if SENTRY_DSN and SENTRY_DSN != "https://your_sentry_dsn_here" and "sentry.io" in SENTRY_DSN:
    try:
        import sentry_sdk
        from sentry_sdk.integrations.loguru import LoguruIntegration
        
        sentry_sdk.init(
            dsn=SENTRY_DSN,
            # Виправлено: ініціалізуємо інтегратор без параметрів
            integrations=[LoguruIntegration()],
            send_default_pii=True,          # Дозволяє збирати контекст запитів FastAPI
            traces_sample_rate=1.0,
            profiles_sample_rate=1.0,
        )
        logger.info("📡 Sentry SDK успішно ініціалізовано. Моніторинг активний!")
    except Exception as e:
        # У разі будь-якого збою не ламаємо запуск системи
        sys.stderr.write(f"⚠️ Не вдалося ініціалізувати Sentry: {e}\n")

# Налаштовуємо логування в локальний файл через Loguru
logger.add(
    LOG_PATH,
    rotation="10 MB",
    retention="30 days",
    level="INFO",
    encoding="utf-8",
    backtrace=True,
    diagnose=True
)
