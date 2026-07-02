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
    """Парсить деталі хакатону для фонової бази даних."""
    logger.info(f"Збір деталей для хакатону за адресою: {url}")
    
    response = safe_get(url)
    if not response or not response.text:
        logger.error(f"Не вдалося отримати HTML-вміст для {url}")
        return {}
        
    try:
        soup = BeautifulSoup(response.text, "lxml")

        # 1. Призовий фонд
        prize_el = soup.select_one(".prize-amount")
        prize = prize_el.get_text(strip=True) if prize_el else "Unknown"

        # 2. Теми
        themes = [t.get_text(strip=True) for t in soup.select(".theme-label")]

        # 3. Спонсори (мульти-селектор)
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

        # 5. Кількість учасників
        participants_el = soup.select_one(".participants-count")
        participants = 0
        if participants_el:
            clean_digits = re.sub(r"\D", "", participants_el.get_text(strip=True))
            participants = int(clean_digits) if clean_digits else 0

        # 6. Обмеження участі (Eligibility)
        invite_only = False
        students_only = False
        team_required = False

        for info_block in soup.select(".info, .info-with-icon"):
            if "invite only" in info_block.get_text(strip=True).lower():
                invite_only = True
                break

        eligibility_items = soup.select("#eligibility-list li")
        for li in eligibility_items:
            text = li.get_text(strip=True).lower()
            if any(w in text for w in ["student", "high school", "university", "13 to 19"]):
                students_only = True
            if "team required" in text or re.search(r"([2-9])\s*(to|-)\s*\d+\s*members", text):
                team_required = True

        # 7. Мультимодальність: вилучення URL банера за вашим прикладом верстки
        banner_el = soup.select_one("h1.header-image img") or soup.select_one("#logo-container img")
        banner_url = ""
        if banner_el:
            banner_url = banner_el.get("src", "")
        else:
            meta_el = soup.select_one("meta[property=\"og:image\"]")
            if meta_el:
                banner_url = meta_el.get("content", "")

        return {
            "url": url,
            "prize_total": prize,
            "themes": themes,
            "sponsors": sponsors,
            "judging_criteria": criteria,
            "participant_count": participants,
            "invite_only": invite_only,
            "students_only": students_only,
            "team_required": team_required,
            "banner_url": banner_url
        }
        
    except Exception as e:
        logger.error(f"Помилка під час парсингу сторінки {url}: {e}")
        return {}
