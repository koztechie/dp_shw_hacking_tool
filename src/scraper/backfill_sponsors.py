import sys
from pathlib import Path
import json
import time
import re
from bs4 import BeautifulSoup

# Гарантуємо правильні шляхи імпорту

from src.logger import logger
from src.scraper.http_client import safe_get
from src.db import get_connection

def scrape_sponsors_robust(soup) -> list:
    """
    Збирає спонсорів за допомогою гнучких мульти-селекторів.
    Повністю сумісний з новими класами (sponsor_logo_img) та контейнерами (article).
    """
    sponsors = []
    
    # Шукаємо зображення спонсорів за точними новими класами та батьківськими контейнерами
    images = (
        soup.select("img.sponsor_logo_img") or           # Новий шаблон (підкреслення)
        soup.select("img[class*='sponsor']") or          # Будь-яка картинка з класом sponsor
        soup.select("[id*='sponsor'] img") or            # Всередині будь-яких контейнерів (div, article) з id="*sponsor*"
        soup.select("[class*='sponsor'] img") or         # Всередині контейнерів із класом "*sponsor*"
        soup.select(".sponsor-logo img")                 # Класичний фолбек
    )
    
    for img in images:
        alt = img.get("alt")
        if alt:
            alt_clean = alt.strip()
            
            # Повністю ігноруємо службові логотипи Devpost
            if any(word in alt_clean.lower() for word in ["devpost", "dft", "for teams"]):
                continue
                
            # Очищуємо від слова "logo", якщо воно присутнє в alt
            sponsor_name = re.sub(r"(?i)\s*logo\s*", "", alt_clean).strip()
            
            if sponsor_name and len(sponsor_name) > 1:
                sponsors.append(sponsor_name)
                
    return list(set(sponsors))

def backfill_sponsors():
    con = get_connection()
    
    # Отримуємо всі хакатони
    hackathons = con.execute("SELECT id, url, title FROM hackathons").fetchall()
    logger.info(f"Початок пере-перевірки спонсорів для {len(hackathons)} хакатонів...")
    
    updated_count = 0
    
    for idx, (h_id, h_url, h_title) in enumerate(hackathons, start=1):
        response = safe_get(h_url)
        if not response or not response.text:
            continue
            
        try:
            soup = BeautifulSoup(response.text, "lxml")
            sponsors = scrape_sponsors_robust(soup)
            
            if sponsors:
                # Оновлюємо спонсорів у базі
                con.execute(
                    "UPDATE hackathons SET sponsors = ? WHERE id = ?",
                    [json.dumps(sponsors, ensure_ascii=False), h_id]
                )
                logger.info(f"[{idx}/{len(hackathons)}] 🏆 Оновлено спонсорів для {h_title}: {sponsors}")
                updated_count += 1
            else:
                logger.info(f"[{idx}/{len(hackathons)}] Спонсорів для {h_title} не знайдено.")
                
        except Exception as e:
            logger.error(f"Помилка збору для {h_title}: {e}")
            
        time.sleep(0.5)  # Пауза для безпеки
        
    con.close()
    logger.info(f"🎉 Процедуру завершено! Збагачено хакатонів: {updated_count}")

if __name__ == "__main__":
    backfill_sponsors()
