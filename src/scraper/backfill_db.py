import sys
from pathlib import Path
import json
import time

# Гарантуємо правильні шляхи імпорту
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.logger import logger
from src.scraper.project_detail_scraper import scrape_project_detail
from src.db import get_connection

def run_backfill():
    con = get_connection()
    
    # Вибираємо проекти, які ще не перевірялися на статус перемоги (prize_track є NULL)
    projects = con.execute("""
        SELECT id, project_url FROM projects 
        WHERE prize_track IS NULL AND project_url != ''
    """).fetchall()
    
    logger.info(f"Початок збагачення номінацій переможців для {len(projects)} проектів...")
    
    try:
        for idx, (p_id, p_url) in enumerate(projects, start=1):
            logger.info(f"[{idx}/{len(projects)}] Перевірка нагороди проекту: {p_url}")
            
            pdetail = scrape_project_detail(p_url)
            if pdetail:
                # Отримуємо номінацію за новим селектором span.winner
                prize_track = pdetail.get("prize_track")
                is_winner = prize_track is not None
                
                # Оновлюємо ТІЛЬКИ статус переможця та номінацію (не чіпаючи вже зібрані теги)
                con.execute("""
                    UPDATE projects 
                    SET is_winner = ?, prize_track = ?
                    WHERE id = ?
                """, [is_winner, prize_track, p_id])
                
                # Проміжне збереження для надійності
                if idx % 25 == 0:
                    con.commit()
                    logger.info(f"💾 Збережено прогрес... Оброблено {idx} проектів.")
                    
                time.sleep(0.3)  # Легка затримка
                
        con.commit()
        logger.info("🎉 Збагачення переможців успішно завершено!")
        
    except Exception as e:
        con.rollback()
        logger.error(f"Помилка під час збагачення: {e}")
    finally:
        con.close()

if __name__ == "__main__":
    run_backfill()
