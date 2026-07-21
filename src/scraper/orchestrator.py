import sys
from pathlib import Path
import json
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed

# Гарантуємо правильні шляхи

from src.logger import logger
from src.scraper.hackathon_list_scraper import fetch_ended_hackathons
from src.scraper.hackathon_detail_scraper import scrape_hackathon_detail
from src.scraper.projects_scraper import fetch_hackathon_projects, extract_subdomain
from src.scraper.project_detail_scraper import scrape_project_detail
from src.scraper.github_scraper import get_github_metrics
from src.db import get_connection, init_db

STOP_WORDS = ["student", "university", "high school", "internal", "closed"]

def _process_single_project(p: dict, h_id: str) -> dict:
    """Функція для паралельного виконання (Worker Task). Збирає деталі 1 проекту."""
    p_url = p.get("project_url", "")
    p_id = str(uuid.uuid5(uuid.NAMESPACE_URL, p_url if p_url else p.get("title", "") + h_id))
    
    pdetail = scrape_project_detail(p_url) if p_url else {}
    github_url = pdetail.get("github_url", "")
    github = get_github_metrics(github_url) if github_url else {}
    
    tech_tags = pdetail.get("tech_tags") or p.get("tech_tags", [])
    is_winner = p.get("is_winner", False) or (pdetail.get("prize_track") is not None)
    
    return {
        "id": p_id,
        "title": p.get("title", ""),
        "description": p.get("description", ""),
        "tech_tags": tech_tags,
        "team_size": pdetail.get("team_size", 1),
        "likes": p.get("likes", 0),
        "github_url": github_url,
        "demo_url": pdetail.get("demo_url"),
        "is_winner": is_winner,
        "prize_track": pdetail.get("prize_track"),
        "readme_length": github.get("readme_length", 0),
        "commit_count": github.get("commit_count_48h", 0),
        "url": p_url
    }

def run_full_ingestion(pages: int = 5):
    """
    Повний цикл збору даних з Devpost.
    Використовує Lightweight ThreadPool для паралельного I/O мережі,
    уникаючи важких Celery/Redis.
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
            
        if any(word in h_title.lower() for word in STOP_WORDS):
            logger.info(f"[{idx}/{len(hackathons_list)}] 🚫 Відфільтровано: {h_title}")
            continue
            
        h_id = str(uuid.uuid5(uuid.NAMESPACE_URL, h_url))
        
        con = get_connection()
        try:
            exists = con.execute("SELECT id FROM hackathons WHERE id = ?", [h_id]).fetchone()
        finally:
            con.close()
            
        if exists:
            logger.info(f"[{idx}/{len(hackathons_list)}] Пропущено (вже є в БД): {h_title}")
            continue
            
        logger.info(f"[{idx}/{len(hackathons_list)}] Збір даних: {h_title}...")
        
        try:
            detail = scrape_hackathon_detail(h_url)
            sponsors = detail.get("sponsors", [])
            if not sponsors:
                continue
            
            subdomain = extract_subdomain(h_url)
            projects = fetch_hackathon_projects(subdomain)
            logger.info(f"Знайдено проектів для обробки: {len(projects)}")
            # --- СТРИМІНГОВИЙ ЗАПИС ТА ПАРАЛЕЛЬНА ОБРОБКА БАТЧАМИ ---
            con = get_connection()
            try:
                con.execute("BEGIN")
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
                    detail.get("prize_total"), detail.get("participant_count", 0),
                    json.dumps(detail.get("themes", [])), json.dumps(sponsors),
                    detail.get("judging_criteria", "")
                ])
                
                from itertools import islice
                batch_size = 50
                project_iter = iter(projects)
                
                # max_workers=2 для AMD A4 (Lightweight Distributed Processing)
                with ThreadPoolExecutor(max_workers=2) as executor:
                    while True:
                        batch = list(islice(project_iter, batch_size))
                        if not batch:
                            break
                            
                        futures = [executor.submit(_process_single_project, p, h_id) for p in batch]
                        for future in as_completed(futures):
                            try:
                                pd = future.result()
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
                            except Exception as e:
                                logger.error(f"Помилка в worker thread або записі БД: {e}")
                                
                con.commit()
                logger.info(f"✅ Збережено в БД: {h_title} ({len(projects)} проектів)")
            except Exception as e:
                try: con.execute("ROLLBACK")
                except: pass
                logger.error(f"Помилка запису в БД: {e}")
            finally:
                con.close()
                
        except Exception as e:
            logger.error(f"Помилка збору хакатону: {e}")
            
        time.sleep(2)
        
    logger.info("Оркестрацію успішно завершено.")

if __name__ == "__main__":
    run_full_ingestion(pages=1)
