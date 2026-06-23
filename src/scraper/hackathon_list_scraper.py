import sys
from pathlib import Path
import time
import json

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.logger import logger
from src.scraper.http_client import safe_get
from config.settings import SCRAPE_DELAY_SECONDS

def fetch_ended_hackathons(pages: int = 5) -> list[dict]:
    """Отримує список завершених хакатонів з Devpost API сторінка за сторінкою."""
    hackathons = []
    logger.info(f"Запуск збору списку хакатонів. Заплановано сторінок: {pages}")
    
    for page in range(1, pages + 1):
        url = f"https://devpost.com/api/hackathons?status=ended&page={page}&per_page=24"
        logger.info(f"Збір сторінки {page}...")
        
        response = safe_get(url)
        if not response:
            logger.error(f"Пропуск сторінки {page} через критичну помилку завантаження.")
            continue
        
        try:
            data = response.json()
            batch = data.get("hackathons", [])
            hackathons.extend(batch)
            logger.info(f"Сторінку {page} успішно оброблено. Зчитано записів: {len(batch)}")
        except Exception as e:
            logger.error(f"Помилка парсингу JSON на сторінці {page}: {e}")
            
        # Затримка між сторінками (анти-бан)
        time.sleep(SCRAPE_DELAY_SECONDS)
        
    return hackathons

if __name__ == "__main__":
    # Гарантуємо існування папки сирих даних
    Path("data/raw").mkdir(parents=True, exist_ok=True)
    
    # Скрапимо перші 5 сторінок (120 записів)
    result = fetch_ended_hackathons(pages=5)
    logger.info(f"Збір списку завершено. Всього отримано хакатонів: {len(result)}")
    
    output_file = Path("data/raw/hackathon_list.json")
    try:
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        logger.info(f"Дані успішно збережено у файл: {output_file}")
    except Exception as e:
        logger.error(f"Помилка при збереженні даних у файл: {e}")
