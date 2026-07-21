import sys
from pathlib import Path
import uuid
import json
import hashlib


from src.logger import logger
from src.analyzer.hackathon_parser import parse_hackathon_from_url, parse_hackathon_from_html
from src.analyzer.rules_extractor import fetch_and_clean_rules, extract_hard_constraints_with_ai
from src.analyzer.organizer_osint import get_organizer_patterns
from src.analyzer.profile_analyzer import analyze_hackathon_profile
from src.analyzer.idea_generator import generate_winning_ideas
from src.analyzer.scorer import rank_ideas
from src.analyzer.cache import cache_key, get_cached, set_cache
from src.db import get_connection

def _run_analysis_pipeline(hackathon_data: dict, source_url: str) -> dict:
    """Внутрішнє ядро, яке обробляє дані як з URL, так і з локальних HTML файлів."""
    if hackathon_data.get("invite_only") or hackathon_data.get("students_only"):
        logger.warning("⚠️ Увага: Цей хакатон має жорсткі обмеження (Invite Only або Students Only)!")

    rules_url = hackathon_data.get("rules_url", "")
    hard_constraints = {}
    if rules_url and rules_url.startswith("http"):
        ck_rules = cache_key(rules_url + "constraints")
        hard_constraints = get_cached(ck_rules)
        if not hard_constraints:
            raw_rules = fetch_and_clean_rules(rules_url)
            hard_constraints = extract_hard_constraints_with_ai(raw_rules)
            set_cache(ck_rules, hard_constraints)

    organizer = hackathon_data.get("organizer", "")
    osint = get_organizer_patterns(organizer) if organizer else {"found": False, "patterns": {}}


    # Завантаження банера для Multi-Modal аналізу
    banner_url = hackathon_data.get("banner_url")
    banner_bytes = None
    if banner_url:
        from src.scraper.http_client import safe_get
        img_resp = safe_get(banner_url, timeout=5)
        if img_resp and len(img_resp.content) < 4 * 1024 * 1024:  # Ліміт 4 МБ
            banner_bytes = img_resp.content
            logger.info("📸 Банер успішно завантажено для AI Vision аналізу.")

    from src.analyzer.prompt_manager import prompt_manager

    # Кеш аналізу залежить від URL та промпту аналізатора
    prompt_profile = prompt_manager.get_prompt("profile_analyzer")
    ck_analysis = cache_key(source_url + "analysis" + str(prompt_profile))
    analysis = get_cached(ck_analysis)
    if not analysis:
        analysis = analyze_hackathon_profile(hackathon_data, osint, banner_bytes)

        set_cache(ck_analysis, analysis)

    # Кеш ідей залежить від URL та промптів генератора/критика
    prompt_brainstormer = prompt_manager.get_prompt("idea_brainstormer")
    prompt_critic = prompt_manager.get_prompt("idea_critic")
    ck_ideas = cache_key(source_url + "ideas" + str(prompt_brainstormer) + str(prompt_critic))
    ideas = get_cached(ck_ideas)
    if not ideas:
        ideas = generate_winning_ideas(hackathon_data, analysis, hard_constraints)
        set_cache(ck_ideas, ideas)

    ranked_ideas = rank_ideas(ideas, hackathon_data)

    while len(ranked_ideas) < 3:
        ranked_ideas.append({"title": "", "description": "", "win_probability": 0.0})

    prediction_id = str(uuid.uuid4())
    try:
        con = get_connection()
        con.execute("BEGIN")
        con.execute("""
            INSERT INTO predictions (id, hackathon_url, generated_at, 
                idea_1_title, idea_1_description, idea_1_score,
                idea_2_title, idea_2_description, idea_2_score,
                idea_3_title, idea_3_description, idea_3_score)
            VALUES (?, ?, current_timestamp, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            prediction_id, source_url,
            ranked_ideas[0].get("title", ""), json.dumps(ranked_ideas[0], ensure_ascii=False), ranked_ideas[0].get("win_probability", 0),
            ranked_ideas[1].get("title", ""), json.dumps(ranked_ideas[1], ensure_ascii=False), ranked_ideas[1].get("win_probability", 0),
            ranked_ideas[2].get("title", ""), json.dumps(ranked_ideas[2], ensure_ascii=False), ranked_ideas[2].get("win_probability", 0),
        ])
        con.commit()
        logger.info(f"✅ Результати аналізу успішно збережено в БД. Prediction ID: {prediction_id}")
    except Exception as e:
        if 'con' in locals(): con.execute("ROLLBACK")
        logger.error(f"Помилка збереження результатів у БД: {e}")
    finally:
        if 'con' in locals(): con.close()

    return {
        "prediction_id": prediction_id,
        "hackathon": hackathon_data,
        "constraints": hard_constraints,
        "analysis": analysis,
        "ideas": ranked_ideas[:3]
    }

def analyze_hackathon(url: str) -> dict:
    """Аналіз онлайн (з мережі)."""
    logger.info(f"🚀 Запуск AI-аналізу для URL: {url}")
    hackathon_data = parse_hackathon_from_url(url)
    if not hackathon_data:
        return {"error": "Failed to parse hackathon URL"}
    return _run_analysis_pipeline(hackathon_data, url)

def analyze_hackathon_offline(html_content: str) -> dict:
    """Аналіз офлайн (з HTML файлу)."""
    logger.info("🚀 Запуск AI-аналізу для вивантаженого HTML файлу")
    
    # КРИТИЧНИЙ ФІКС: Хешуємо контент для унікального ключа кешу
    content_hash = hashlib.sha256(html_content.encode('utf-8')).hexdigest()[:16]
    unique_base_url = f"offline_{content_hash}"
    
    hackathon_data = parse_hackathon_from_html(html_content, base_url=unique_base_url)
    if not hackathon_data:
        return {"error": "Failed to parse HTML content"}
    return _run_analysis_pipeline(hackathon_data, unique_base_url)
