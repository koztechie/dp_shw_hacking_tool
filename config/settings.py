import os
from pathlib import Path
from dotenv import load_dotenv

# Динамічно визначаємо корінь проекту (на один рівень вище папки config/)
BASE_DIR = Path(__file__).resolve().parent.parent

# Завантажуємо змінні оточення строго з кореневого .env
load_dotenv(dotenv_path=BASE_DIR / ".env")

MIMO_API_KEY = os.getenv("MIMO_API_KEY")

# Абсолютні шляхи запобігають появі розкиданих баз даних та логів
DB_PATH = str(BASE_DIR / "data" / "dp_shw.duckdb")
LOG_PATH = str(BASE_DIR / "logs" / "app.log")

DEVPOST_BASE_URL = "https://devpost.com"
SCRAPE_DELAY_SECONDS = 2  # затримка між запитами (анти-бан)
MAX_PROJECTS_PER_HACKATHON = 500
MIMO_BASE_URL = "https://api.xiaomimimo.com/v1"

# Кешування запитів до AI
CACHE_DIR = str(BASE_DIR / "data" / "cache")

# Ліміти Xiaomi MiMo API (згідно з офіційною документацією)
MIMO_RPM_LIMIT = 100
MIMO_DAILY_LIMIT = 5000
