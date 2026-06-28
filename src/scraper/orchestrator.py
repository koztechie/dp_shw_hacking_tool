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

# Стоп-слова для фільтрації закритих/університетських хакатонів
STOP_WORDS = ["student", "university", "high school", "internal", "closed"]

def run_full_ingestion(pages: int = 5):
    """
    Повний цикл збору даних з Devpost.
    Повністю захищений від зсуву стовпців у БД завдяки явному іменуванню полів.
    """
    logger.info("Запуск ініціалізації бази даних...")
    init_db()
    
    hackathons_list = fetch_ended_hackathons(pages=pages)
    logger.info(f"Отримано список із {len(hackathons_list)} хакатонів. Починаємо оркестрацію...")
    
    for idx, h in enumerate(hackathons_list, start=1):
        h_url = h.get("url", "")
        h_title = h.get("title", "")
        
        if not h_url:
            continue
            
        # Ранній фільтр назв
        if any(word in h_title.lower() for word in STOP_WORDS):
            logger.info(f"[{idx}/{len(hackathons_list)}] 🚫 Відфільтровано (Студентський/Закритий): {h_title}")
            continue
            
        h_id = str(uuid.uuid5(uuid.NAMESPACE_URL, h_url))
        
        # Перевірка на дублікат
        con = get_connection()
        try:
            exists = con.execute("SELECT id FROM hackathons WHERE id = ?", [h_id]).fetchone()
        finally:
            con.close()
            
        if exists:
            logger.info(f"[{idx}/{len(hackathons_list)}] Пропущено (вже є в БД): {h_title}")
            continue
            
        logger.info(f"[{idx}/{len(hackathons_list)}] Початок збору даних для: {h_title}...")
        
        # Скрапінг деталей та проектів (БД вільна)
        try:
            detail = scrape_hackathon_detail(h_url)
            
            # Фільтр хакатонів без спонсорів
            sponsors = detail.get("sponsors", [])
            if not sponsors:
                logger.info(f"🚫 Відфільтровано (Немає спонсорів): {h_title}.")
                continue
            
            subdomain = extract_subdomain(h_url)
            projects = fetch_hackathon_projects(subdomain)
            logger.info(f"Знайдено проектів для обробки: {len(projects)}")
            
            # Збираємо деталі проектів та GitHub метрики локально у список
            projects_data = []
            for p_idx, p in enumerate(projects, start=1):
                p_url = p.get("project_url", "")
                p_id = str(uuid.uuid5(uuid.NAMESPACE_URL, p_url if p_url else p["title"] + h_id))
                
                pdetail = scrape_project_detail(p_url) if p_url else {}
                github_url = pdetail.get("github_url", "")
                github = get_github_metrics(github_url) if github_url else {}
                
                tech_tags = pdetail.get("tech_tags") or p.get("tech_tags", [])
                is_winner = p.get("is_winner", False) or (pdetail.get("prize_track") is not None)
                
                projects_data.append({
                    "id": p_id,
                    "title": p["title"],
                    "description": p["description"],
                    "tech_tags": tech_tags,
                    "team_size": pdetail.get("team_size", 1),
                    "likes": p.get("likes", 0),
                    "github_url": pdetail.get("github_url"),
                    "demo_url": pdetail.get("demo_url"),
                    "is_winner": is_winner,
                    "prize_track": pdetail.get("prize_track"),
                    "readme_length": github.get("readme_length", 0),
                    "commit_count": github.get("commit_count_48h", 0),
                    "url": p_url
                })
                time.sleep(0.2)
                
            # ЗАПИС У БД (Відкриваємо з'єднання строго на частку секунди)
            con = get_connection()
            try:
                con.execute("BEGIN")
                
                # Записуємо хакатон (із явним іменуванням колонок)
                con.execute("""
                    INSERT INTO hackathons (
                        id, url, title, organizer, start_date, end_date,
                        prize_total, participant_count, themes, sponsors,
                        judging_criteria, scraped_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, current_timestamp)
                """, [
                    h_id, h_url, h_title, h.get("organization_name"),
                    h.get("submission_period_dates", "")[:10] or None,
                    h.get("submission_period_dates", "")[-10:] or None,
                    detail.get("prize_total"),
                    detail.get("participant_count", 0),
                    json.dumps(detail.get("themes", [])),
                    json.dumps(sponsors),
                    detail.get("judging_criteria", "")
                ])
                
                # Записуємо всі проекти пакетом (із явним іменуванням колонок)
                for pd in projects_data:
                    con.execute("""
                        INSERT OR IGNORE INTO projects (
                            id, hackathon_id, title, description, tech_tags,
                            team_size, likes, github_url, demo_url, is_winner,
                            prize_track, win_score, readme_length, commit_count_48h,
                            project_url, scraped_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, current_timestamp)
                    """, [
                        pd["id"], h_id, pd["title"], pd["description"],
                        json.dumps(pd["tech_tags"]), pd["team_size"], pd["likes"],
                        pd["github_url"], pd["demo_url"], pd["is_winner"],
                        pd["prize_track"], None, pd["readme_length"],
                        pd["commit_count"], pd["url"]
                    ])
                    
                con.commit()
                logger.info(f"✅ Успішно збережено в БД: {h_title} ({len(projects_data)} проектів)")
                
            except Exception as e:
                try: con.execute("ROLLBACK")
                except: pass
                logger.error(f"Помилка запису хакатону {h_title} в БД: {e}")
            finally:
                con.close()  # МИТТЄВО ЗАКРИВАЄМО БД
                
        except Exception as e:
            logger.error(f"Помилка збору хакатону {h_title}: {e}")
            
        time.sleep(2)
        
    logger.info("Процедуру повної оркестрації збору завершено.")

if __name__ == "__main__":
    # Локальний пробний запуск на 1 сторінці (перші 24 хакатони)
    run_full_ingestion(pages=1)
