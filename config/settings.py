import os
from pathlib import Path
from dotenv import load_dotenv

# Динамічно визначаємо корінь проекту (на один рівень вище папки config/)
BASE_DIR = Path(__file__).resolve().parent.parent

# Завантажуємо змінні оточення строго з кореневого .env
load_dotenv(dotenv_path=BASE_DIR / ".env")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Абсолютні шляхи запобігають появі розкиданих баз даних та логів
DB_PATH = str(BASE_DIR / "data" / "dp_shw.duckdb")
LOG_PATH = str(BASE_DIR / "logs" / "app.log")

DEVPOST_BASE_URL = "https://devpost.com"
SCRAPE_DELAY_SECONDS = 2  # затримка між запитами (анти-бан)
MAX_PROJECTS_PER_HACKATHON = 500
GEMINI_MODEL = "gemini-3.5-flash"

# Кешування запитів до AI
CACHE_DIR = str(BASE_DIR / "data" / "cache")

# Ліміти Gemini API (Free Tier)
GEMINI_DAILY_LIMIT = 1500
GEMINI_RPM_LIMIT = 15
