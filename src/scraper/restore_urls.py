import sys
from pathlib import Path
import json
import time

# Гарантуємо правильні шляхи імпорту

from src.logger import logger
from src.scraper.projects_scraper import fetch_hackathon_projects, extract_subdomain
from src.db import get_connection

def run_restore():
    con = get_connection()
    
    # Отримуємо всі завантажені хакатони з бази даних
    hackathons = con.execute("SELECT id, url, title FROM hackathons").fetchall()
    logger.info(f"Початок швидкого відновлення посилань для {len(hackathons)} хакатонів...")
    
    for idx, (h_id, h_url, h_title) in enumerate(hackathons, start=1):
        try:
            subdomain = extract_subdomain(h_url)
            logger.info(f"[{idx}/{len(hackathons)}] Сканування галереї хакатону: {h_title}...")
            
            # Зчитуємо список проектів з галереї (це відбувається дуже швидко)
            projects = fetch_hackathon_projects(subdomain)
            
            # Відкриваємо транзакцію для безпеки
            con.execute("BEGIN")
            
            for p in projects:
                p_title = p.get("title")
                p_url = p.get("project_url")
                
                if p_title and p_url:
                    # Оновлюємо посилання для проекту з такою назвою у межах цього хакатону
                    con.execute("""
                        UPDATE projects 
                        SET project_url = ? 
                        WHERE hackathon_id = ? 
                          AND title = ? 
                          AND (project_url IS NULL OR project_url = '')
                    """, [p_url, h_id, p_title])
                    
            con.commit()
            logger.info(f"  [ОК] Відновлено посилання для хакатону: {h_title}")
            
        except Exception as e:
            con.rollback()
            logger.error(f"  [ПОМИЛКА] Не вдалося відновити дані для {h_title}: {e}")
            
        # Невелика пауза між хакатонами для безпеки
        time.sleep(1)
        
    con.close()
    logger.info("🎉 Процедуру відновлення посилань успішно завершено!")

if __name__ == "__main__":
    run_restore()
