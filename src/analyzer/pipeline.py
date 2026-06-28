import sys
from pathlib import Path
import uuid
import json

# Гарантуємо правильні шляхи імпорту
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.logger import logger
from src.analyzer.hackathon_parser import parse_hackathon_from_url
from src.analyzer.rules_extractor import fetch_and_clean_rules, extract_hard_constraints_with_ai
from src.analyzer.organizer_osint import get_organizer_patterns
from src.analyzer.gemini_analyzer import analyze_hackathon_with_gemini
from src.analyzer.idea_generator import generate_winning_ideas
from src.analyzer.scorer import rank_ideas
from src.analyzer.cache import cache_key, get_cached, set_cache
from src.db import get_connection

def analyze_hackathon(url: str) -> dict:
    """Повний pipeline: URL → Правила → Стратегія → 3 ранжовані ідеї → Збереження в БД."""
    logger.info(f"🚀 Запуск повного AI-аналізу для хакатону: {url}")

    # Крок 1: Парсинг основної сторінки
    hackathon_data = parse_hackathon_from_url(url)
    if not hackathon_data:
        logger.error("Не вдалося розпарсити хакатон.")
        return {"error": "Failed to parse hackathon URL"}

    if hackathon_data.get("invite_only") or hackathon_data.get("students_only"):
        logger.warning("⚠️ Увага: Цей хакатон має жорсткі обмеження (Invite Only або Students Only)!")

    # Крок 1.5: Аналіз правил (Hard Constraints) з кешем
    rules_url = hackathon_data.get("rules_url", "")
    hard_constraints = {}
    if rules_url:
        ck_rules = cache_key(rules_url + "constraints")
        hard_constraints = get_cached(ck_rules)
        if not hard_constraints:
            raw_rules = fetch_and_clean_rules(rules_url)
            hard_constraints = extract_hard_constraints_with_ai(raw_rules)
            set_cache(ck_rules, hard_constraints)

    # Крок 2: OSINT аналіз організатора
    organizer = hackathon_data.get("organizer", "")
    osint = get_organizer_patterns(organizer) if organizer else {"found": False, "patterns": {}}

    # Крок 3: Стратегічний AI-аналіз (з кешем)
    ck_analysis = cache_key(url + "analysis")
    analysis = get_cached(ck_analysis)
    if not analysis:
        analysis = analyze_hackathon_with_gemini(hackathon_data, osint)
        set_cache(ck_analysis, analysis)

    # Крок 4: Генерація ідей з дотриманням жорстких правил (з кешем)
    ck_ideas = cache_key(url + "ideas")
    ideas = get_cached(ck_ideas)
    if not ideas:
        ideas = generate_winning_ideas(hackathon_data, analysis, hard_constraints)
        set_cache(ck_ideas, ideas)

    # Крок 5: Гібридний Scoring і ранжування ідей
    ranked_ideas = rank_ideas(ideas, hackathon_data)

    # Антикрихкість: Безпечне доповнення списку ідей до 3 (якщо ШІ згенерував менше)
    while len(ranked_ideas) < 3:
        ranked_ideas.append({"title": "", "description": "", "win_probability": 0.0})

    # Крок 6: Безпечне збереження в DuckDB
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
            prediction_id, url,
            ranked_ideas[0].get("title", ""), json.dumps(ranked_ideas[0], ensure_ascii=False), ranked_ideas[0].get("win_probability", 0),
            ranked_ideas[1].get("title", ""), json.dumps(ranked_ideas[1], ensure_ascii=False), ranked_ideas[1].get("win_probability", 0),
            ranked_ideas[2].get("title", ""), json.dumps(ranked_ideas[2], ensure_ascii=False), ranked_ideas[2].get("win_probability", 0),
        ])
        con.commit()
        logger.info(f"✅ Результати аналізу успішно збережено в БД. Prediction ID: {prediction_id}")
    except Exception as e:
        if 'con' in locals():
            con.execute("ROLLBACK")
        logger.error(f"Помилка збереження результатів у БД: {e}")
    finally:
        if 'con' in locals():
            con.close()

    return {
        "prediction_id": prediction_id,
        "hackathon": hackathon_data,
        "constraints": hard_constraints,
        "analysis": analysis,
        "ideas": ranked_ideas[:3]
    }

if __name__ == "__main__":
    test_url = "https://haignyc1.devpost.com/"
    print("=== ТЕСТУВАННЯ ПОВНОГО PIPELINE (Етап 38) ===")
    
    result = analyze_hackathon(test_url)
    
    print(f"\n🔑 Prediction ID: {result.get('prediction_id')}")
    print("💡 Згенеровані та відранжовані ідеї:")
    for i, idea in enumerate(result.get("ideas", []), 1):
        title = idea.get('title')
        if title:
            prob = idea.get('win_probability', 0) * 100
            print(f"  {i}. {title} (Шанс перемоги: {prob:.2f}%)")
