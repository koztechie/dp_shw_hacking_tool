import sys
from pathlib import Path
import re
import json
from bs4 import BeautifulSoup

# Гарантуємо правильні шляхи імпорту
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.logger import logger
from src.scraper.http_client import safe_get

def scrape_hackathon_detail(url: str) -> dict:
    """
    Парсить сторінку конкретного хакатону: призові, теми, спонсори, 
    критерії оцінювання та кількість учасників.
    """
    logger.info(f"Збір деталей для хакатону за адресою: {url}")
    
    response = safe_get(url)
    if not response or not response.text:
        logger.error(f"Не вдалося отримати HTML-вміст для {url}")
        return {}
        
    try:
        soup = BeautifulSoup(response.text, "lxml")

        # 1. Призовий фонд (безпечне отримання)
        prize_el = soup.select_one(".prize-amount")
        prize = prize_el.get_text(strip=True) if prize_el else "Unknown"

        # 2. Теми
        themes = [t.get_text(strip=True) for t in soup.select(".theme-label")]

        # 3. Спонсори (захист від відсутності атрибута alt)
        sponsors = []
        for img in soup.select(".sponsor-logo img"):
            alt = img.get("alt")
            if alt:
                sponsors.append(alt.strip())

        # 4. Критерії оцінювання
        criteria_el = soup.select_one("#judging-criteria")
        criteria = criteria_el.get_text(separator=" ", strip=True) if criteria_el else ""

        # 5. Кількість учасників (захист від ValueError під час конвертації в int)
        participants_el = soup.select_one(".participants-count")
        participants = 0
        if participants_el:
            raw_text = participants_el.get_text(strip=True)
            clean_digits = re.sub(r"\D", "", raw_text)
            participants = int(clean_digits) if clean_digits else 0

        return {
            "url": url,
            "prize_total": prize,
            "themes": themes,
            "sponsors": sponsors,
            "judging_criteria": criteria,
            "participant_count": participants
        }
        
    except Exception as e:
        logger.error(f"Помилка під час парсингу сторінки {url}: {e}")
        return {}

if __name__ == "__main__":
    # Завантажуємо перший хакатон зі списку для локального тестування
    list_file = Path("data/raw/hackathon_list.json")
    if not list_file.exists():
        print("❌ Тестовий список 'data/raw/hackathon_list.json' не знайдено.")
        print("Будь ласка, виконайте спочатку Етап 10.")
        sys.exit(1)
        
    with open(list_file, "r", encoding="utf-8") as f:
        hackathons = json.load(f)
        
    if not hackathons:
        print("❌ Список хакатонів порожній.")
        sys.exit(1)
        
    test_url = hackathons[0].get("url")
    print(f"🔄 Тестуємо детальний скрапер на першому хакатоні: {hackathons[0].get('title')}")
    
    result = scrape_hackathon_detail(test_url)
    print("\n📋 ОТРИМАНІ ДЕТАЛІ ХАКАТОНУ:")
    print(json.dumps(result, indent=2, ensure_ascii=False))
