import sys
from pathlib import Path
import time
import httpx

# Додаємо корінь проекту до sys.path

from src.logger import logger

import threading

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9"
}

MAX_RETRIES = 3
RETRY_DELAY = 5

class HTTPClientManager:
    def __init__(self):
        self._client = None
        self._lock = threading.Lock()
        self._semaphore = threading.Semaphore(3)  # Макс 3 одночасних з'єднання для захисту AMD A4 та уникнення 429
    
    @property
    def client(self):
        if self._client is None:
            with self._lock:
                if self._client is None:
                    # Connection pooling & keep-alive!
                    limits = httpx.Limits(max_keepalive_connections=5, max_connections=10)
                    self._client = httpx.Client(headers=HEADERS, limits=limits, follow_redirects=True)
        return self._client
    
    def get(self, url: str, timeout: int = 20) -> httpx.Response | None:
        with self._semaphore:  # Контрольована конкурентність
            for attempt in range(1, MAX_RETRIES + 1):
                try:
                    r = self.client.get(url, timeout=timeout)
                    
                    # Обробка Rate Limit (429)
                    if r.status_code == 429:
                        retry_after = int(r.headers.get("Retry-After", 60))
                        logger.warning(f"Отримано статус 429 (Rate Limit). Очікування {retry_after} секунд перед спробою {attempt}/{MAX_RETRIES}...")
                        time.sleep(retry_after)
                        continue
                        
                    # Якщо 404 — це штатна поведінка закінчення галереї, повертаємо відразу
                    if r.status_code == 404:
                        return r
                        
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
            
    def close(self):
        if self._client:
            self._client.close()

http_manager = HTTPClientManager()

def safe_get(url: str, timeout: int = 20) -> httpx.Response | None:
    """Зворотна сумісність для існуючого синхронного коду"""
    return http_manager.get(url, timeout)
