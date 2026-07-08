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

# Монолітна конфігурація ШІ-моделі Xiaomi MiMo v2.5 Pro (Етапи 1-8)
MIMO_API_KEY = os.getenv("MIMO_API_KEY")
MIMO_BASE_URL = "https://api.xiaomimimo.com/v1"
MIMO_RPM_LIMIT = 100  # Згідно з офіційним лімітом
MIMO_DAILY_LIMIT = 5000 # Достатній ліміт для локальної роботи
