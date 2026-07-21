import os
import re
import sys
from pathlib import Path

from loguru import logger

# Гарантуємо правильні шляхи імпорту
PROJECT_ROOT = Path(__file__).resolve().parent.parent

from config.settings import SETTINGS  # noqa: E402


# ==========================================
# 🛡️ АНТИКРИХКИЙ ФІЛЬТР ЧУТЛИВИХ ДАНИХ
# ==========================================
class SensitiveDataFilter:
    """Видаляє API-ключі та паролі з логів до того, як вони будуть збережені."""
    SENSITIVE_PATTERNS = [
        (r'Bearer\s+[A-Za-z0-9\-_.]+', 'Bearer [REDACTED]'),
        (
            r'(?:api[_-]?key|MIMO_API_KEY|OPENROUTER_API_KEY)\s*[=:]\s*["\']?[A-Za-z0-9\-_.]{10,}["\']?',
            'API_KEY=[REDACTED]'
        ),
        (r'password\s*[=:]\s*["\']?[^\s,"\'"}]+["\']?', 'password=[REDACTED]'),
        (r'secret\s*[=:]\s*["\']?[^\s,"\'"}]+["\']?', 'secret=[REDACTED]'),
        (r'sk-[a-zA-Z0-9]{20,}', 'sk-[REDACTED]'),
        (r'sk-or-v1-[a-zA-Z0-9]{20,}', 'sk-or-v1-[REDACTED]'),
        (r'tp-[a-zA-Z0-9]{20,}', 'tp-[REDACTED]'),
        (r'ghp_[a-zA-Z0-9]{36,}', 'ghp_[REDACTED]'),  # GitHub tokens
        (r'xox[baprs]-[a-zA-Z0-9\-]+', 'xox-[REDACTED]'),  # Slack tokens
    ]

    @classmethod
    def redact(cls, message: str) -> str:
        msg = str(message)
        for pattern, replacement in cls.SENSITIVE_PATTERNS:
            msg = re.sub(pattern, replacement, msg, flags=re.IGNORECASE)
        return msg


def redact_secrets(record):
    """Метод-патчер для Loguru, який ФАКТИЧНО змінює текст повідомлення."""
    record["message"] = SensitiveDataFilter.redact(record["message"])


# Застосовуємо глобальний патч до логера
logger = logger.patch(redact_secrets)

SENTRY_PII_ENABLED = os.getenv("SENTRY_PII_ENABLED", "false").lower() == "true"

# Ініціалізація Sentry з урахуванням антикрихких правок безпеки (No PII) та продуктивності
if SETTINGS.sentry_dsn and "sentry.io" in SETTINGS.sentry_dsn:
    try:
        import sentry_sdk
        from sentry_sdk.integrations.loguru import LoguruIntegration
        
        sentry_sdk.init(
            dsn=SETTINGS.sentry_dsn,
            integrations=[LoguruIntegration()],
            send_default_pii=SENTRY_PII_ENABLED,
            traces_sample_rate=0.1 if not SENTRY_PII_ENABLED else 1.0,  # Зменшуємо навантаження
            profiles_sample_rate=0.0,  # Профілювання вимикаємо на AMD A4
            environment=os.getenv("DP_SHW_ENV", "local"),
            before_send=lambda event, hint: None if event.get("level") == "debug" else event
        )
        logger.info(f"📡 Sentry SDK успішно ініціалізовано (PII Protected={not SENTRY_PII_ENABLED}).")
    except ImportError:
        logger.warning("⚠️ sentry_sdk не встановлено, логування помилок у Sentry вимкнено.")

# Конфігурація логера
LOG_PATH = SETTINGS.log_path
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

logger.remove()

logger.add(
    sys.stderr,
    format=(
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level:<8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
        "<level>{message}</level>"
    ),
    level="INFO"
)

logger.add(
    str(LOG_PATH),
    format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<8} | {name}:{function}:{line} - {message}",
    level="INFO",
    rotation="5 MB",
    retention=5,
    compression="zip",
    encoding="utf-8",
    backtrace=False,
    diagnose=False,
    enqueue=True
)

# Окремий файл для помилок
logger.add(
    str(LOG_PATH.parent / "errors.log"),
    format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<8} | {name}:{function}:{line} - {message}",
    level="ERROR",
    rotation="5 MB",
    retention=5,
    compression="zip",
    encoding="utf-8",
    backtrace=False,
    diagnose=False,
    enqueue=True
)

logger.info("✅ Logger ініціалізовано з ротацією та cleanup")
