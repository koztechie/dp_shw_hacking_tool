import ipaddress
import socket
import threading
import time
from urllib.parse import urlparse

import httpx

from src.logger import logger

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
    "Accept": "text/html,application/json",
    "Accept-Language": "en-US,en;q=0.9",
}

MAX_RETRIES = 3
RETRY_DELAY = 5
ALLOWED_DOMAINS = {"devpost.com", "api.github.com", "github.com"}


def _is_safe_redirect(url: str) -> bool:
    """Перевіряє кожен redirect URL на SSRF."""
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("https", "http"):
            return False
        netloc = parsed.netloc.lower().split(":")[0]

        # Блокуємо IP-адреси
        try:
            ip = ipaddress.ip_address(netloc)
            if ip.is_private or ip.is_loopback or ip.is_reserved or ip.is_link_local:
                return False
        except ValueError:
            pass

        # Whitelist доменів
        if not any(netloc == d or netloc.endswith(f".{d}") for d in ALLOWED_DOMAINS):
            return False

        # DNS resolution check
        resolved = socket.getaddrinfo(netloc, None)
        for _, _, _, _, sockaddr in resolved:
            ip_obj = ipaddress.ip_address(sockaddr[0])
            if ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_reserved:
                return False

        return True
    except Exception:
        return False


class HTTPClientManager:
    def __init__(self):
        self._client = None
        self._lock = threading.Lock()
        self._semaphore = threading.Semaphore(3)

    @property
    def client(self):
        if self._client is None:
            with self._lock:
                if self._client is None:
                    limits = httpx.Limits(
                        max_keepalive_connections=5,
                        max_connections=10,
                    )
                    # КРИТИЧНО: follow_redirects=False
                    # Redirect-и обробляються вручну з перевіркою
                    self._client = httpx.Client(
                        headers=HEADERS,
                        limits=limits,
                        follow_redirects=False,  # ← ЗАБОРОНА авто-redirect
                        timeout=httpx.Timeout(20.0, connect=10.0),
                    )
        return self._client

    def get(self, url: str, timeout: int = 20, max_redirects: int = 3) -> httpx.Response | None:
        with self._semaphore:
            current_url = url
            for redirect_count in range(max_redirects + 1):
                for attempt in range(1, MAX_RETRIES + 1):
                    try:
                        r = self.client.get(current_url, timeout=timeout)

                        # Обробка redirect ВРУЧНУ з перевіркою
                        if r.status_code in (301, 302, 303, 307, 308):
                            location = r.headers.get("location", "")
                            if not location:
                                return None
                            # Резолвімо відносний URL
                            if location.startswith("/"):
                                parsed = urlparse(current_url)
                                location = f"{parsed.scheme}://{parsed.netloc}{location}"

                            if not _is_safe_redirect(location):
                                logger.warning(
                                    f"🚨 SSRF BLOCKED: Redirect to {location}"
                                )
                                return None

                            current_url = location
                            break  # Переходимо до наступного redirect

                        if r.status_code == 429:
                            retry_after = int(r.headers.get("Retry-After", 60))
                            time.sleep(min(retry_after, 30))
                            continue

                        if r.status_code == 404:
                            return r

                        r.raise_for_status()
                        return r

                    except (httpx.ConnectError, httpx.TimeoutException) as e:
                        logger.warning(f"Attempt {attempt}/{MAX_RETRIES} failed: {e}")
                        time.sleep(RETRY_DELAY * attempt)
                    except Exception as e:
                        logger.error(f"Unexpected error: {e}")
                        time.sleep(RETRY_DELAY * attempt)
                else:
                    return None  # Всі спроби вичерпані

            return None  # Забагато redirect-ів

    def close(self):
        if self._client:
            self._client.close()


http_manager = HTTPClientManager()


def safe_get(url: str, timeout: int = 20) -> httpx.Response | None:
    return http_manager.get(url, timeout)
