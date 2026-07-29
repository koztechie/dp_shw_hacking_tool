import sys
from pathlib import Path
import time
import json


from src.logger import logger
from src.scraper.http_client import safe_get
from config.settings import SCRAPE_DELAY_SECONDS

def fetch_ended_hackathons(max_pages: int = 50) -> list[dict]:
    """Отримує список завершених хакатонів з Devpost API сторінка за сторінкою."""
    hackathons = []
    logger.info(f"Запуск збору списку хакатонів. Заплановано до {max_pages} сторінок.")
    
    for page in range(1, max_pages + 1):
        url = f"https://devpost.com/api/hackathons?status=ended&page={page}&per_page=24"
        logger.info(f"Збір сторінки {page}...")
        
        response = safe_get(url)
        if not response:
            logger.error(f"Пропуск сторінки {page} через критичну помилку завантаження.")
            break
        
        try:
            data = response.json()
            batch = data.get("hackathons", [])
            if not batch:
                logger.info(f"Отримано порожній список на сторінці {page}. Збір завершено.")
                break
            hackathons.extend(batch)
            logger.info(f"Сторінку {page} успішно оброблено. Зчитано записів: {len(batch)}")
        except Exception as e:
            logger.error(f"Помилка парсингу JSON на сторінці {page}: {e}")
            break
            
        # Затримка між сторінками (анти-бан)
        time.sleep(SCRAPE_DELAY_SECONDS)
        
    return hackathons

if __name__ == "__main__":
    # Гарантуємо існування папки сирих даних
    Path("data/raw").mkdir(parents=True, exist_ok=True)
    
    # Скрапимо до 50 сторінок
    result = fetch_ended_hackathons(max_pages=50)
    logger.info(f"Збір списку завершено. Всього отримано хакатонів: {len(result)}")
    
    output_file = Path("data/raw/hackathon_list.json")
    try:
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        logger.info(f"Дані успішно збережено у файл: {output_file}")
    except Exception as e:
        logger.error(f"Помилка при збереженні даних у файл: {e}")
