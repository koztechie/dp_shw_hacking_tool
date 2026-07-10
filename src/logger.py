import re
import sys
from pathlib import Path

import sentry_sdk
from loguru import logger
from sentry_sdk.integrations.loguru import LoguruIntegration

# Гарантуємо правильні шляхи імпорту
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import SENTRY_DSN  # noqa: E402


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

# Ініціалізація Sentry з урахуванням антикрихких правок безпеки (No PII) та продуктивності
if SENTRY_DSN and SENTRY_DSN != "your_sentry_dsn_here" and SENTRY_DSN != "":
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[LoguruIntegration()],
        send_default_pii=False,
        traces_sample_rate=0.1,
        profiles_sample_rate=0.1
    )
    logger.info("📡 Sentry SDK успішно ініціалізовано (PII Protected).")

# Конфігурація логера
LOG_DIR = PROJECT_ROOT / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

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
    str(LOG_DIR / "app.log"),
    format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<8} | {name}:{function}:{line} - {message}",
    level="DEBUG",
    rotation="10 MB",
    compression="zip"
)
