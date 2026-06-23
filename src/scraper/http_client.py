import sys
from pathlib import Path
import time
import httpx

# Додаємо корінь проекту до sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.logger import logger

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9"
}

MAX_RETRIES = 3
RETRY_DELAY = 5

def safe_get(url: str, timeout: int = 20) -> httpx.Response | None:
    """
    Виконує безпечний GET-запит із обробкою помилок, 
    автоматичними повторними спробами та очікуванням при 429 Rate Limit.
    """
    for attempt in range(1, MAX_RETRIES + 1):
        # Відрізок коду з src/scraper/http_client.py
        try:
            with httpx.Client(timeout=timeout) as client:
                r = client.get(url, headers=HEADERS)
                
                # Антикрихкість: якщо сторінку не знайдено, не ретраїмо (це кінець галереї)
                if r.status_code == 404:
                    return r
                    
                # Обробка Rate Limit (429)
                if r.status_code == 429:
                    logger.warning(f"Отримано статус 429 (Rate Limit). Очікування 60 секунд перед спробою {attempt}/{MAX_RETRIES}...")
                    time.sleep(60)
                    continue
                    
                r.raise_for_status()
                return r
                
        except httpx.HTTPStatusError as e:
            logger.warning(f"Спроба {attempt}/{MAX_RETRIES} не вдалася (HTTP {e.response.status_code}) для {url}")
            time.sleep(RETRY_DELAY * attempt)
        except (httpx.ConnectError, httpx.TimeoutException) as e:
            logger.warning(f"Спроба {attempt}/{MAX_RETRIES} не вдалася (Помилка мережі/Таймаут: {e}) для {url}")
            time.sleep(RETRY_DELAY * attempt)
        except Exception as e:
            logger.error(f"Неочікувана помилка під час спроби {attempt}/{MAX_RETRIES} для {url}: {e}")
            time.sleep(RETRY_DELAY * attempt)
            
    logger.error(f"Усі спроби ({MAX_RETRIES}) для {url} вичерпано. Повертаємо None.")
    return None
