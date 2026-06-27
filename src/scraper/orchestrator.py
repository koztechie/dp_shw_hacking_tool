import sys
from pathlib import Path
import json
import time
import uuid

# Гарантуємо правильні шляхи імпорту
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.logger import logger
from src.scraper.hackathon_list_scraper import fetch_ended_hackathons
from src.scraper.hackathon_detail_scraper import scrape_hackathon_detail
from src.scraper.projects_scraper import fetch_hackathon_projects, extract_subdomain
from src.scraper.project_detail_scraper import scrape_project_detail
from src.scraper.github_scraper import get_github_metrics
from src.db import get_connection, init_db

def run_full_ingestion(pages: int = 5):
    """
    Повний цикл збору даних з Devpost:
    список -> деталі хакатону -> проекти -> деталі проектів -> GitHub.
    Оркестратор повністю збагачує та записує project_url для повної аналітики.
    """
    logger.info("Запуск ініціалізації бази даних згідно з оновленою схемою дат...")
    init_db()
    
    con = get_connection()
    try:
        hackathons_list = fetch_ended_hackathons(pages=pages)
        logger.info(f"Отримано список із {len(hackathons_list)} хакатонів. Починаємо оркестрацію...")
        
        for idx, h in enumerate(hackathons_list, start=1):
            h_url = h.get("url", "")
            if not h_url:
                continue
                
            h_id = str(uuid.uuid5(uuid.NAMESPACE_URL, h_url))
            
            # 1. Перевірка дублікатів (захист від повторної обробки)
            exists = con.execute("SELECT id FROM hackathons WHERE id = ?", [h_id]).fetchone()
            if exists:
                logger.info(f"[{idx}/{len(hackathons_list)}] Пропущено (вже є в БД): {h.get('title')}")
                continue
                
            logger.info(f"[{idx}/{len(hackathons_list)}] Початок збору даних для: {h.get('title')}...")
            
            # Повна ізоляція обробки кожного хакатону в транзакцію
            try:
                # Відкриваємо явну транзакцію в DuckDB
                con.execute("BEGIN")
                
                # 2. Збір деталей хакатону
                detail = scrape_hackathon_detail(h_url)
                
                con.execute("""
                    INSERT INTO hackathons VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, current_timestamp)
                """, [
                    h_id, h_url, h.get("title"), h.get("organization_name"),
                    h.get("submission_period_dates", "")[:10] or None,
                    h.get("submission_period_dates", "")[-10:] or None,
                    detail.get("prize_total"),
                    detail.get("participant_count", 0),
                    json.dumps(detail.get("themes", [])),
                    json.dumps(detail.get("sponsors", [])),
                    detail.get("judging_criteria", "")
                ])
                
                # 3. Збір проектів хакатону
                subdomain = extract_subdomain(h_url)
                projects = fetch_hackathon_projects(subdomain)
                logger.info(f"Знайдено проектів для обробки: {len(projects)}")
                
                # 4. Обробка деталей та метрик кожного проекту
                for p_idx, p in enumerate(projects, start=1):
                    p_url = p.get("project_url", "")
                    p_id = str(uuid.uuid5(uuid.NAMESPACE_URL, p_url if p_url else p["title"] + h_id))
                    
                    pdetail = scrape_project_detail(p_url) if p_url else {}
                    
                    # 5. Збір GitHub-метрик
                    github_url = pdetail.get("github_url", "")
                    github = get_github_metrics(github_url) if github_url else {}
                    
                    readme_length = github.get("readme_length", 0)
                    commit_count = github.get("commit_count_48h", 0)
                    
                    # Безпечне об'єднання: беремо теги з деталей
                    tech_tags = pdetail.get("tech_tags") or p.get("tech_tags", [])
                    
                    # Визначення переможця на основі наявності номінації у деталях
                    is_winner = p.get("is_winner", False) or (pdetail.get("prize_track") is not None)
                    
                    con.execute("""
                        INSERT OR IGNORE INTO projects VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, current_timestamp)
                    """, [
                        p_id, h_id, p["title"], p["description"],
                        json.dumps(tech_tags),
                        pdetail.get("team_size", 1),
                        p.get("likes", 0),
                        pdetail.get("github_url"),
                        pdetail.get("demo_url"),
                        is_winner,
                        pdetail.get("prize_track"),
                        None,  # win_score
                        readme_length,
                        commit_count,
                        p_url  # Записуємо project_url
                    ])
                    
                    # Затримка між проектами
                    time.sleep(0.2)
                    
                con.commit()
                logger.info(f"Успішно імпортовано хакатон: {h.get('title')} ({len(projects)} проектів).")
                
            except Exception as e:
                # Безпечний відкат транзакції
                try:
                    con.execute("ROLLBACK")
                except Exception:
                    pass
                logger.error(f"Помилка під час збору хакатону {h.get('title')}: {e}. Переходимо до наступного.")
                
            # Пауза між хакатонами
            time.sleep(2)
            
    finally:
        con.close()
        logger.info("Процедуру повної оркестрації збору завершено.")

if __name__ == "__main__":
    # Робимо 1 сторінку для швидкої тестової перевірки (24 хакатони)
    run_full_ingestion(pages=1)
