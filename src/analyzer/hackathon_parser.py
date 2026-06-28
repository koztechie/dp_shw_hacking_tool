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

def _extract_data_from_soup(soup: BeautifulSoup, url: str) -> dict:
    """Базова функція вилучення даних з DOM-дерева."""
    
    # 1. Базова інформація
    title_el = soup.select_one("h1")
    title = title_el.get_text(strip=True) if title_el else "Unknown"

    # 2. Призовий фонд (Багатошаровий фолбек з Етапу 11)
    prize = "Unknown"
    prize_el = soup.select_one(".prize-amount")
    if prize_el:
        prize = prize_el.get_text(strip=True)
    else:
        prize_link = soup.select_one("a.prizes-link")
        if prize_link:
            raw_text = prize_link.get_text(separator=" ", strip=True)
            match = re.search(r"\$[0-9,]+", raw_text)
            prize = match.group(0) if match else raw_text
        else:
            currency_val = soup.select_one("[data-currency-value]")
            if currency_val:
                prize = f"${currency_val.get_text(strip=True)}"

    # 3. Теми
    themes = [t.get_text(strip=True) for t in soup.select(".theme-label")]

    # 4. Спонсори (Антикрихкий мульти-селектор)
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

    # 5. Текстові блоки для ШІ-аналізу
    criteria_el = soup.select_one("#judging-criteria")
    criteria = criteria_el.get_text(separator=" ", strip=True) if criteria_el else ""

    about_el = soup.select_one("#about")
    about = about_el.get_text(separator=" ", strip=True) if about_el else ""

    prizes_el = soup.select_one("#prizes")
    prizes_text = prizes_el.get_text(separator=" ", strip=True) if prizes_el else ""

    # 6. Обмеження участі (Ранні фільтри)
    invite_only = False
    students_only = False
    team_required = False

    for info_block in soup.select(".info, .info-with-icon"):
        if "invite only" in info_block.get_text(strip=True).lower():
            invite_only = True
            break

    for li in soup.select("#eligibility-list li"):
        text = li.get_text(strip=True).lower()
        if any(w in text for w in ["student", "high school", "university", "13 to 19"]):
            students_only = True
        if "team required" in text or re.search(r"([2-9])\s*(to|-)\s*\d+\s*members", text):
            team_required = True

    # 7. Підготовка до Етапу 31.1: Знаходимо URL правил
    rules_el = soup.select_one("a[href$='/rules']")
    rules_url = ""
    if rules_el:
        href = rules_el.get("href", "")
        # Перетворюємо відносний шлях у повний
        if href.startswith("http"):
            rules_url = href
        else:
            base_domain = url.split("/project-gallery")[0].rstrip("/")
            rules_url = base_domain + href

    return {
        "url": url,
        "title": title,
        "prize_total": prize,
        "themes": themes,
        "sponsors": sponsors,
        "judging_criteria": criteria,
        "about": about,
        "prizes_detail": prizes_text,
        "invite_only": invite_only,
        "students_only": students_only,
        "team_required": team_required,
        "rules_url": rules_url
    }

def parse_hackathon_from_url(url: str) -> dict:
    """Парсить сторінку майбутнього або поточного хакатону з мережі."""
    logger.info(f"Завантаження хакатону: {url}")
    r = safe_get(url)
    if not r or not r.text:
        return {}
    soup = BeautifulSoup(r.text, "lxml")
    return _extract_data_from_soup(soup, url)

def parse_hackathon_from_html(html_content: str, base_url: str = "local_file") -> dict:
    """Парсить з вивантаженого HTML файлу (офлайн режим)."""
    soup = BeautifulSoup(html_content, "lxml")
    return _extract_data_from_soup(soup, base_url)

if __name__ == "__main__":
    test_url = "https://haignyc1.devpost.com/"
    print(f"🔄 Тестуємо парсер для AI-аналізатора: {test_url}")
    result = parse_hackathon_from_url(test_url)
    
    # Виводимо ключові метрики для перевірки (щоб не засмічувати консоль великими текстами)
    summary = {k: v for k, v in result.items() if k not in ['about', 'judging_criteria', 'prizes_detail']}
    print("\n📋 ОТРИМАНА СТРУКТУРА (без довгих текстів):")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
