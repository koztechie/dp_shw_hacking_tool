import sys
from pathlib import Path
import urllib.parse


from src.logger import logger
from src.scraper.http_client import safe_get

def get_realtime_sponsor_news(sponsors: list) -> str:
    """
    Збирає найсвіжіші новини (Real-Time Ingestion) про технології спонсорів хакатону.
    """
    if not sponsors:
        return "No specific sponsor news at the moment."

    logger.info(f"🔎 Real-Time Ingestion: пошук свіжих новин для спонсорів {sponsors[:3]}...")
    news_items = []

    # Беремо максимум 3 головних спонсорів, щоб не затримувати процес
    for sponsor in sponsors[:3]:
        query = urllib.parse.quote(sponsor)
        url = f"https://hn.algolia.com/api/v1/search_by_date?query={query}&tags=story&hitsPerPage=2"
        
        response = safe_get(url, timeout=5)
        if response and response.status_code == 200:
            try:
                hits = response.json().get("hits", [])
                for hit in hits:
                    title = hit.get("title")
                    if title:
                        news_items.append(f"- {sponsor}: {title}")
            except Exception as e:
                logger.warning(f"Не вдалося розпарсити новини для {sponsor}: {e}")

    if not news_items:
        return "No recent breaking news found for these sponsors."

    return "\n".join(news_items)

if __name__ == "__main__":
    print("=== ТЕСТ REAL-TIME INGESTION ===")
    print(get_realtime_sponsor_news(["OpenAI", "Supabase"]))
