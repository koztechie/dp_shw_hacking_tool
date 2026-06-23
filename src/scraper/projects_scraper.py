import sys
from pathlib import Path
import re
import time
import json
from bs4 import BeautifulSoup

# Гарантуємо правильні шляхи імпорту
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.logger import logger
from src.scraper.http_client import safe_get
from config.settings import SCRAPE_DELAY_SECONDS, MAX_PROJECTS_PER_HACKATHON

def extract_subdomain(url: str) -> str:
    """
    Вилучає субдомен Devpost з повного URL.
    Приклад: https://ai-hackathon-2026.devpost.com/ -> ai-hackathon-2026
    """
    clean = url.replace("https://", "").replace("http://", "").strip("/")
    parts = clean.split(".")
    return parts[0]

def fetch_hackathon_projects(hackathon_subdomain: str) -> list[dict]:
    """
    Парсить усі проекти конкретного хакарону з його галереї проектів.
    """
    projects = []
    page = 1
    logger.info(f"Запуск збору проектів для субдомену: {hackathon_subdomain}")
    
    while len(projects) < MAX_PROJECTS_PER_HACKATHON:
        url = f"https://{hackathon_subdomain}.devpost.com/project-gallery?page={page}"
        logger.info(f"Збір проектів, сторінка {page}...")
        
        response = safe_get(url)
        
        if not response:
            logger.warning("З'єднання повернуло None. Перериваємо цикл.")
            break
            
        if response.status_code == 404:
            logger.info(f"Отримано статус 404 на сторінці {page}. Галерею успішно зчитано повністю.")
            break
            
        try:
            soup = BeautifulSoup(response.text, "lxml")
            cards = soup.select(".software-entry")
            
            if not cards:
                logger.info(f"На сторінці {page} більше немає карток проектів. Завершуємо збір.")
                break
                
            for card in cards:
                title_el = card.select_one("h5")
                desc_el = card.select_one(".entry-body p")
                tags = [t.get_text(strip=True) for t in card.select(".software-entry-tags span")]
                
                # Безпечний парсинг лайків
                likes_el = card.select_one(".like-count")
                likes = 0
                if likes_el:
                    likes_raw = re.sub(r"\D", "", likes_el.get_text(strip=True))
                    likes = int(likes_raw) if likes_raw else 0
                    
                # УНІВЕРСАЛЬНИЙ ТА СТІЙКИЙ ПОШУК ПОСИЛАННЯ НА ПРОЕКТ
                project_url = ""
                
                # Спроба 1: Батьківський елемент є посиланням (як на hackmars)
                parent_a = card.find_parent("a")
                if parent_a and parent_a.get("href"):
                    project_url = parent_a.get("href")
                # Спроба 2: Сама картка є посиланням
                elif card.name == "a" and card.get("href"):
                    project_url = card.get("href")
                # Спроба 3: Посилання всередині картки (старі шаблони)
                else:
                    link_el = None
                    for a in card.select("a[href]"):
                        href = a.get("href", "")
                        if "/software/" in href or "/submissions/" in href:
                            link_el = a
                            break
                    if not link_el:
                        link_el = card.select_one("a.block-wrapper-link")
                    if link_el:
                        project_url = link_el.get("href", "")
                
                # Очищення та префікс домену
                if project_url:
                    project_url = project_url if project_url.startswith("http") else "https://devpost.com" + project_url
                
                # Визначення переможця
                winner_badge = card.select_one(".winner-badge")
                is_winner = winner_badge is not None

                projects.append({
                    "title": title_el.get_text(strip=True) if title_el else "",
                    "description": desc_el.get_text(strip=True) if desc_el else "",
                    "tech_tags": tags,
                    "likes": likes,
                    "project_url": project_url,
                    "is_winner": is_winner
                })
                
            logger.info(f"Сторінка {page}: успішно зчитано {len(cards)} проектів.")
            page += 1
            time.sleep(SCRAPE_DELAY_SECONDS)
            
        except Exception as e:
            logger.error(f"Помилка під час обробки сторінки {page}: {e}")
            break
            
    return projects[:MAX_PROJECTS_PER_HACKATHON]

if __name__ == "__main__":
    list_file = Path("data/raw/hackathon_list.json")
    if not list_file.exists():
        print("❌ Тестовий список 'data/raw/hackathon_list.json' не знайдено.")
        sys.exit(1)
        
    with open(list_file, "r", encoding="utf-8") as f:
        hackathons = json.load(f)
        
    first_hackathon = hackathons[1]  # Використовуємо індекс 1 для HackMars 3.0: NEON
    subdomain = extract_subdomain(first_hackathon.get("url"))
    
    result = fetch_hackathon_projects(subdomain)
    print(f"\n✅ Збір завершено. Всього знайдено проектів: {len(result)}")
    if len(result) > 0:
        print("\n📋 ПРИКЛАД ПЕРШОГО ПРОЕКТУ З ОНОВЛЕНИМ URL:")
        print(json.dumps(result[0], indent=2, ensure_ascii=False))
