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
    Парсить сторінку конкретного хакарону з використанням багатошарових фолбеків:
    вилучає призові, теми, спонсорів, критерії, учасників та обмеження.
    """
    logger.info(f"Збір деталей для хакатону за адресою: {url}")
    
    response = safe_get(url)
    if not response or not response.text:
        logger.error(f"Не вдалося отримати HTML-вміст для {url}")
        return {}
        
    try:
        soup = BeautifulSoup(response.text, "lxml")

        # 1. Призовий фонд (Багатошаровий фолбек)
        prize = "Unknown"
        prize_el = soup.select_one(".prize-amount")
        if prize_el:
            prize = prize_el.get_text(strip=True)
        else:
            # Спроба 2: пошук лінку призових
            prize_link = soup.select_one("a.prizes-link")
            if prize_link:
                # Очищаємо текст, наприклад "$1,000 in cash" -> "$1,000"
                raw_text = prize_link.get_text(separator=" ", strip=True)
                match = re.search(r"\$[0-9,]+", raw_text)
                prize = match.group(0) if match else raw_text
            else:
                # Спроба 3: пошук будь-якого елемента з атрибутом валюти
                currency_val = soup.select_one("[data-currency-value]")
                if currency_val:
                    prize = f"${currency_val.get_text(strip=True)}"

        # 2. Теми
        themes = [t.get_text(strip=True) for t in soup.select(".theme-label")]

        # 3. Спонсори
        sponsors_images = (
            soup.select("img.sponsor_logo_img") or 
            soup.select("img[class*='sponsor']") or
            soup.select("[id*='sponsor'] img") or
            soup.select(".sponsors img") or
            soup.select(".sponsor img")
        )
        sponsors_list = []
        for img in sponsors_images:
            alt = img.get("alt")
            if alt:
                alt_clean = alt.strip()
                if not any(word in alt_clean.lower() for word in ["devpost", "dft", "for teams"]):
                    name = re.sub(r"(?i)\s*logo\s*", "", alt_clean).strip()
                    if name and len(name) > 1:
                        sponsors_list.append(name)
        sponsors = list(set(sponsors_list))

        # 4. Критерії оцінювання
        criteria_el = soup.select_one("#judging-criteria")
        criteria = criteria_el.get_text(separator=" ", strip=True) if criteria_el else ""

        # 5. Кількість учасників (Багатошаровий фолбек)
        participants = 0
        participants_el = soup.select_one(".participants-count")
        
        if participants_el:
            clean_digits = re.sub(r"\D", "", participants_el.get_text(strip=True))
            participants = int(clean_digits) if clean_digits else 0
        else:
            # Спроба 2: скануємо табличну верстку сайдбару на наявність слова "participants"
            for element in soup.select("td, span, p"):
                text = element.get_text(strip=True).lower()
                if "participants" in text:
                    clean_digits = re.sub(r"\D", "", text)
                    if clean_digits:
                        participants = int(clean_digits)
                        break

        # 6. Обмеження участі (Eligibility & Requirements)
        invite_only = False
        students_only = False
        team_required = False

        # Перевірка Invite only у блоках з інформацією
        for info_block in soup.select(".info, .info-with-icon"):
            if "invite only" in info_block.get_text(strip=True).lower():
                invite_only = True
                break

        # Перевірка списку вимог (Eligibility List)
        eligibility_items = soup.select("#eligibility-list li")
        for li in eligibility_items:
            text = li.get_text(strip=True).lower()
            if any(w in text for w in ["student", "high school", "university", "13 to 19"]):
                students_only = True
            if "team required" in text or re.search(r"([2-9])\s*(to|-)\s*\d+\s*members", text):
                team_required = True

        return {
            "url": url,
            "prize_total": prize,
            "themes": themes,
            "sponsors": sponsors,
            "judging_criteria": criteria,
            "participant_count": participants,
            "invite_only": invite_only,
            "students_only": students_only,
            "team_required": team_required
        }
        
    except Exception as e:
        logger.error(f"Помилка під час парсингу сторінки {url}: {e}")
        return {}

if __name__ == "__main__":
    test_url = "https://haignyc1.devpost.com/"
    print(f"🔄 Повторно тестуємо детальний скрапер з новими фолбеками: {test_url}")
    
    result = scrape_hackathon_detail(test_url)
    
    print("\n📋 ОТРИМАНІ ДЕТАЛІ ХАКАТОНУ:")
    print(json.dumps(result, indent=2, ensure_ascii=False))
