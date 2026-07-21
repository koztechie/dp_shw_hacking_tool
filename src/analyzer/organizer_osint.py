import sys
from pathlib import Path
import json
from collections import Counter
import duckdb


from config.settings import DB_PATH
from src.logger import logger

def get_organizer_patterns(organizer_name: str) -> dict:
    """Знаходить патерни ПЕРЕМОЖЦІВ та ПРОГРАВШИХ від цього організатора."""
    if not organizer_name or len(str(organizer_name).strip()) < 2:
        return {"found": False, "patterns": {}}

    organizer_clean = str(organizer_name).strip()
    logger.info(f"OSINT-аналіз для '{organizer_clean}'...")

    try:
        con = duckdb.connect(DB_PATH, read_only=True)
        # Переможці
        winners = con.execute("""
            SELECT p.tech_tags, p.prize_track FROM projects p
            JOIN hackathons h ON p.hackathon_id = h.id
            WHERE h.organizer ILIKE ? AND p.is_winner = TRUE
        """, [f"%{organizer_clean}%"]).fetchdf()
        
        # Ті, хто програв (Анти-патерни)
        losers = con.execute("""
            SELECT p.tech_tags FROM projects p
            JOIN hackathons h ON p.hackathon_id = h.id
            WHERE h.organizer ILIKE ? AND p.is_winner = FALSE
        """, [f"%{organizer_clean}%"]).fetchdf()
    except Exception as e:
        logger.error(f"Помилка БД під час OSINT: {e}")
        return {"found": False, "patterns": {}}
    finally:
        if 'con' in locals(): con.close()

    if winners.empty:
        return {"found": False, "patterns": {}}

    def extract_top_tags(df_series, limit=10):
        tags = []
        for tags_val in df_series.dropna():
            if isinstance(tags_val, str):
                try: tags.extend(json.loads(tags_val))
                except: pass
            elif isinstance(tags_val, list):
                tags.extend(tags_val)
        return dict(Counter(tags).most_common(limit))

    return {
        "found": True,
        "previous_winners_count": len(winners),
        "top_winning_tags": extract_top_tags(winners["tech_tags"]),
        "top_losing_tags": extract_top_tags(losers["tech_tags"]), # НОВА ФІЧА: Анти-патерни
        "popular_tracks": winners["prize_track"].dropna().value_counts().head(5).to_dict()
    }

if __name__ == "__main__":
    print(json.dumps(get_organizer_patterns("Cal Hacks"), indent=2, ensure_ascii=False))
