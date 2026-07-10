import os
from pathlib import Path

from dotenv import load_dotenv

# Автоматично завантажуємо змінні з .env файлу
load_dotenv()

# Гарантуємо можливість імпорту src
import sys  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.utils import SecretManager, safe_path  # noqa: E402

# АНТИКРИХКІСТЬ: Тільки абсолютні безпечні шляхи (Path Traversal Protection)
DB_PATH = safe_path(PROJECT_ROOT, "data/dp_shw.duckdb")
CACHE_DIR = safe_path(PROJECT_ROOT, "data/cache")

secret_manager = SecretManager()

# Налаштування системи моніторингу помилок Sentry
SENTRY_DSN = os.getenv("SENTRY_DSN")

# АНТИКРИХКІСТЬ: Каскадний AI-роутер (Primary → Fallback) з шифруванням
# 1. Primary: Xiaomi MiMo v2.5 Pro
enc_mimo = os.getenv("MIMO_API_KEY_ENCRYPTED")
MIMO_API_KEY = (
    secret_manager.decrypt(enc_mimo.encode())
    if enc_mimo
    else (os.getenv("MIMO_API_KEY") or os.getenv("GEMINI_API_KEY"))
)
MIMO_BASE_URL = os.getenv("MIMO_BASE_URL", "https://api.xiaomimimo.com/v1")
MIMO_RPM_LIMIT = int(os.getenv("MIMO_RPM_LIMIT", "100"))
MIMO_DAILY_LIMIT = int(os.getenv("MIMO_DAILY_LIMIT", "5000"))

# 2. Fallback: OpenRouter (Llama 3.3, Qwen 2.5 — безкоштовні моделі)
enc_openrouter = os.getenv("OPENROUTER_API_KEY_ENCRYPTED")
OPENROUTER_API_KEY = (
    secret_manager.decrypt(enc_openrouter.encode()) if enc_openrouter else os.getenv("OPENROUTER_API_KEY")
)
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
