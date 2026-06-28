import sys
from pathlib import Path
import json
from collections import Counter

# Гарантуємо правильні шляхи імпорту
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import duckdb
from config.settings import DB_PATH
from src.logger import logger

def get_organizer_patterns(organizer_name: str) -> dict:
    """
    Знаходить патерни успіху (що вигравало раніше) на хакатонах цього ж організатора.
    Захищено від порожніх запитів та блокування БД.
    """
    if not organizer_name or len(str(organizer_name).strip()) < 2:
        return {"found": False, "patterns": {}}

    organizer_clean = str(organizer_name).strip()
    logger.info(f"OSINT-аналіз: шукаємо патерни для '{organizer_clean}'...")

    try:
        con = duckdb.connect(DB_PATH, read_only=True)
        # Шукаємо переможців на інших хакатонах цього організатора
        results = con.execute("""
            SELECT p.tech_tags, p.description, p.prize_track
            FROM projects p
            JOIN hackathons h ON p.hackathon_id = h.id
            WHERE h.organizer ILIKE ?
            AND p.is_winner = TRUE
        """, [f"%{organizer_clean}%"]).fetchdf()
    except Exception as e:
        logger.error(f"Помилка БД під час OSINT: {e}")
        return {"found": False, "patterns": {}}
    finally:
        if 'con' in locals():
            con.close()

    if results.empty:
        logger.info(f"Патернів для '{organizer_clean}' не знайдено (немає попередніх переможців у базі).")
        return {"found": False, "patterns": {}}

    # 1. Топ-теги переможців (Безпечний парсинг)
    all_tags = []
    for tags_val in results["tech_tags"].dropna():
        if isinstance(tags_val, list):
            all_tags.extend(tags_val)
        elif isinstance(tags_val, str):
            try:
                parsed = json.loads(tags_val)
                if isinstance(parsed, list):
                    all_tags.extend(parsed)
            except json.JSONDecodeError:
                pass

    top_tags = dict(Counter(all_tags).most_common(10))

    # 2. Топ prize tracks
    tracks_series = results["prize_track"].dropna()
    tracks = tracks_series.value_counts().head(5).to_dict() if not tracks_series.empty else {}

    # 3. Приклади описів
    descriptions = [str(d) for d in results["description"].dropna().head(3).tolist() if d]

    return {
        "found": True,
        "previous_winners_count": len(results),
        "top_winning_tags": top_tags,
        "popular_tracks": tracks,
        "sample_descriptions": descriptions
    }

if __name__ == "__main__":
    # Тестуємо на організаторі Cal Hacks (який був у нашому прикладі Berkeley AI Hackathon)
    test_org = "Cal Hacks"
    print(f"🔄 Тестуємо OSINT для організатора: '{test_org}'")
    
    osint_data = get_organizer_patterns(test_org)
    
    print("\n📋 ОТРИМАНИЙ OSINT-ПРОФІЛЬ:")
    print(json.dumps(osint_data, indent=2, ensure_ascii=False))
