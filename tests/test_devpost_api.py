import sys
from pathlib import Path
import json

# Додаємо корінь проекту до шляхів імпорту
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

try:
    import httpx
    from src.logger import logger
except ImportError as e:
    print(f"❌ Помилка імпорту бібліотек: {e}")
    print("Рекомендація: перевірте, чи активоване віртуальне середовище (source venv/bin/activate).")
    sys.exit(1)

URL = "https://devpost.com/api/hackathons?status=ended&page=1&per_page=24"

# Реалістичний заголовок для уникнення блокування WAF/Cloudflare
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9"
}

print("=== ПРОГРАМНЕ ДОСЛІДЖЕННЯ DEVPOST API ===")
logger.info(f"Надсилання запиту до API: {URL}")

try:
    with httpx.Client(timeout=15.0) as client:
        response = client.get(URL, headers=HEADERS)
        
        logger.info(f"HTTP статус відповіді: {response.status_code}")
        
        if response.status_code == 403:
            logger.error("Отримано статус 403 Forbidden. Наш User-Agent або IP заблоковано захистом Cloudflare.")
            sys.exit(1)
            
        response.raise_for_status()
        
        # Перевірка валідності JSON-структури
        data = response.json()
        
        if "hackathons" not in data:
            logger.error("Критична помилка: Ключ 'hackathons' відсутній у відповіді API! Структура змінилася.")
            sys.exit(1)
            
        if "meta" not in data:
            logger.warning("Ключ 'meta' відсутній у відповіді API. Можливо, відбулися зміни в структурі пагінації.")
        else:
            meta = data["meta"]
            total = meta.get("total_count", "невідомо")
            page = meta.get("current_page", "невідомо")
            logger.info(f"Метадані успішно зчитано. Загальна кількість: {total}, Сторінка: {page}")
            
        hackathons = data["hackathons"]
        logger.info(f"Кількість хакатонів на поточній сторінці: {len(hackathons)}")
        
        if len(hackathons) > 0:
            print("\n📋 ПРИКЛАД СТРУКТУРИ ДАНИХ (Перші 3 записи):")
            for i, h in enumerate(hackathons[:3]):
                print(f"  [{i+1}] {h.get('title')}")
                print(f"      Організатор: {h.get('organization_name')}")
                print(f"      Адреса сайту: {h.get('url')}")
            print("\n✅ Структуру Devpost JSON API успішно перевірено та підтверджено.")
        else:
            logger.warning("API повернуло порожній список хакатонів.")
            
except httpx.HTTPStatusError as e:
    logger.error(f"Помилка HTTP статусу: {e.response.status_code} - {e.response.text[:200]}")
    sys.exit(1)
except json.JSONDecodeError as e:
    logger.error(f"Сервер повернув не-JSON відповідь (можливо, сторінку блокування Cloudflare): {e}")
    sys.exit(1)
except Exception as e:
    logger.error(f"Виникла неочікувана помилка при з'єднанні: {e}")
    sys.exit(1)
