import sys
from pathlib import Path
import json
import xml.etree.ElementTree as ET
import httpx

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.logger import logger
from src.scraper.http_client import safe_get
from config.settings import CACHE_DIR

TRENDS_FILE = Path(CACHE_DIR) / "global_trends.json"

def fetch_hacker_news() -> list:
    """Витягує топ-5 обговорень з Hacker News."""
    logger.info("Збір трендів з Hacker News...")
    trends = []
    try:
        with httpx.Client(timeout=10.0) as client:
            top_ids = client.get("https://hacker-news.firebaseio.com/v0/topstories.json").json()
            for item_id in top_ids[:5]:
                item = client.get(f"https://hacker-news.firebaseio.com/v0/item/{item_id}.json").json()
                if item and "title" in item:
                    trends.append(item["title"])
    except Exception as e:
        logger.error(f"Помилка HN API: {e}")
    return trends

def fetch_arxiv_ai() -> list:
    """Витягує 3 найсвіжіші публікації з Artificial Intelligence на ArXiv."""
    logger.info("Збір інновацій з ArXiv (cs.AI)...")
    trends = []
    try:
        url = "https://export.arxiv.org/api/query?search_query=cat:cs.AI&sortBy=submittedDate&sortOrder=descending&max_results=3"
        response = safe_get(url)
        if response and response.text:
            root = ET.fromstring(response.text)
            ns = {'atom': 'http://www.w3.org/2005/Atom'}
            for entry in root.findall('atom:entry', ns):
                title = entry.find('atom:title', ns).text.replace('\n', ' ').strip()
                trends.append(title)
    except Exception as e:
        logger.error(f"Помилка ArXiv API: {e}")
    return trends

def update_global_trends():
    """Агрегує всі тренди і зберігає в локальний кеш."""
    trends_data = {
        "hacker_news_discussions": fetch_hacker_news(),
        "latest_arxiv_ai_papers": fetch_arxiv_ai()
    }
    
    # Зберігаємо в кеш для миттєвого доступу AI-генератором
    TRENDS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(TRENDS_FILE, "w", encoding="utf-8") as f:
        json.dump(trends_data, f, ensure_ascii=False, indent=2)
        
    logger.info("✅ Глобальні технологічні тренди успішно оновлено!")

if __name__ == "__main__":
    update_global_trends()
    print(TRENDS_FILE.read_text())
