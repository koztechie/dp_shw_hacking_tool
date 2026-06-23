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

def scrape_project_detail(project_url: str) -> dict:
    """
    Парсить індивідуальну сторінку проекту на Devpost:
    витягує посилання на GitHub, демо-посилання, розмір команди, трек перемоги та теги технологій.
    """
    if not project_url or not project_url.startswith("http"):
        logger.warning(f"Пропущено парсинг деталей: некоректна або порожня адреса URL: {project_url}")
        return {}
        
    logger.info(f"Збір деталей проекту за адресою: {project_url}")
    response = safe_get(project_url)
    if not response or not response.text:
        logger.error(f"Не вдалося завантажити HTML для деталей проекту: {project_url}")
        return {}
        
    try:
        soup = BeautifulSoup(response.text, "lxml")
        
        # 1. GitHub URL (безпечний пошук посилання з доменом github.com)
        github_el = soup.find("a", href=re.compile(r"github\.com"))
        github_url = github_el.get("href") if github_el else None
        
        # 2. Demo URL (зовнішнє посилання на деплой застосунку)
        demo_el = soup.select_one(".app-links a")
        demo_url = demo_el.get("href") if demo_el else None
        
        # 3. Розмір команди (підрахунок профілів учасників)
        members = soup.select(".members .user-profile")
        team_size = len(members) if members else 1
        
        # 4. Призовий трек / номінація
        prize_el = soup.select_one(".winner-badge")
        prize_track = prize_el.get_text(strip=True) if prize_el else None
        
        # 5. Теги технологій (новий антикрихкий збір зі сторінки деталей)
        tags_el = soup.select("#built-with li") or soup.select(".cp-tag")
        tech_tags = list(set([t.get_text(strip=True) for t in tags_el if t]))
        
        return {
            "github_url": github_url,
            "demo_url": demo_url,
            "team_size": team_size,
            "prize_track": prize_track,
            "tech_tags": tech_tags  # Нове поле
        }
        
    except Exception as e:
        logger.error(f"Помилка під час парсингу деталей проекту {project_url}: {e}")
        return {}

if __name__ == "__main__":
    from src.scraper.projects_scraper import fetch_hackathon_projects
    
    test_subdomain = "hackmars-3-0-neon"
    print(f"🔄 Отримуємо проекти з {test_subdomain} для пошуку тестового URL...")
    
    projects = fetch_hackathon_projects(test_subdomain)
    
    target_project = None
    for p in projects:
        if p.get("project_url"):
            target_project = p
            break
            
    if not target_project:
        print("❌ Не знайдено жодного проекту з робочим project_url для тесту.")
        sys.exit(1)
        
    print(f"\n🎯 Знайдено тестовий проект: '{target_project.get('title')}'")
    print(f"🔗 URL: {target_project.get('project_url')}")
    
    details = scrape_project_detail(target_project.get("project_url"))
    
    print("\n📋 РЕЗУЛЬТАТ ПАРСИНГУ ДЕТАЛЕЙ ПРОЕКТУ:")
    print(json.dumps(details, indent=2, ensure_ascii=False))
