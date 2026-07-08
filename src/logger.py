import sys
import os
from pathlib import Path
from loguru import logger
import sentry_sdk
from sentry_sdk.integrations.loguru import LoguruIntegration

# Гарантуємо правильні шляхи імпорту
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import SENTRY_DSN

# Ініціалізація Sentry з урахуванням антикрихких правок безпеки (No PII) та продуктивності (10% sampling)
if SENTRY_DSN and SENTRY_DSN != "your_sentry_dsn_here" and SENTRY_DSN != "":
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[LoguruIntegration()],
        send_default_pii=False,      # АНТИКРИХКІСТЬ: Захист від витоку IP та Cookies
        traces_sample_rate=0.1,      # Обмежуємо навантаження на процесор (10% запитів)
        profiles_sample_rate=0.1     # Економія ресурсів на профілюванні
    )
    logger.info("📡 Sentry SDK успішно ініціалізовано. Моніторинг активний!")

# Конфігурація Loguru логера
LOG_DIR = PROJECT_ROOT / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

# Очищуємо дефолтні налаштування логера
logger.remove()

# Додаємо вивід у консоль
logger.add(
    sys.stderr,
    format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level:<8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    level="INFO"
)

# Додаємо ротацію логів у файл для автономності
logger.add(
    str(LOG_DIR / "app.log"),
    format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<8} | {name}:{function}:{line} - {message}",
    level="DEBUG",
    rotation="10 MB",
    compression="zip"
)
