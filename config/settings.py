import os
from pathlib import Path

from dotenv import load_dotenv

# Автоматично завантажуємо змінні з .env файлу
load_dotenv()

# АНТИКРИХКІСТЬ: Тільки абсолютні шляхи для стабільної роботи у фоновому anacron!
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "data" / "dp_shw.duckdb"
CACHE_DIR = PROJECT_ROOT / "data" / "cache"

# Налаштування системи моніторингу помилок Sentry
SENTRY_DSN = os.getenv("SENTRY_DSN")

# АНТИКРИХКІСТЬ: Каскадний AI-роутер (Primary → Fallback)
# 1. Primary: Xiaomi MiMo v2.5 Pro
MIMO_API_KEY = os.getenv("MIMO_API_KEY") or os.getenv("GEMINI_API_KEY")
MIMO_BASE_URL = os.getenv("MIMO_BASE_URL", "https://api.xiaomimimo.com/v1")
MIMO_RPM_LIMIT = int(os.getenv("MIMO_RPM_LIMIT", "100"))
MIMO_DAILY_LIMIT = int(os.getenv("MIMO_DAILY_LIMIT", "5000"))

# 2. Fallback: OpenRouter (Llama 3.3, Qwen 2.5 — безкоштовні моделі)
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
