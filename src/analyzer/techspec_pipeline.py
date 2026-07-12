import sys
from pathlib import Path
import json
import duckdb

# Гарантуємо правильні шляхи імпорту
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.analyzer.techspec_generator import generate_techspec
from src.analyzer.cache import cache_key, get_cached, set_cache
from src.scraper.realtime_news import get_realtime_sponsor_news
from src.db import get_connection
from src.logger import logger

def generate_and_save_techspec(prediction_id: str, idea_index: int, hackathon_url: str) -> dict:
    """
    Генерує ТЗ для обраної ідеї і безпечно зберігає в БД.
    Антикрихкість: використовує LEFT JOIN для підтримки нових хакатонів,
    які ще не були завантажені фоновим оркестратором.
    """
    logger.info(f"Запуск генерації ТЗ для передбачення {prediction_id} (Ідея #{idea_index})")
    
    if idea_index not in [1, 2, 3]:
        return {"error": "Invalid idea_index. Must be 1, 2, or 3."}

    try:
        con = get_connection()
        
        # АНТИКРИХКІСТЬ: Заміна JOIN на LEFT JOIN, щоб не втрачати ідею,
        # якщо хакатону ще немає в таблиці hackathons!
        query = """
            SELECT p.idea_1_description, h.sponsors 
            FROM predictions p 
            LEFT JOIN hackathons h ON p.hackathon_url = h.url 
            WHERE p.id = ?
        """
        # Динамічно коригуємо назву стовпця ідеї
        query = query.replace("p.idea_1_description", f"p.idea_{idea_index}_description")
        row = con.execute(query, [prediction_id]).fetchone()

        if not row or not row[0]:
            logger.error(f"Опис ідеї #{idea_index} або передбачення не знайдено в БД.")
            return {"error": "Prediction or idea not found"}

        idea_json = row[0]
        sponsors_raw = row[1]  # Буде None для нових хакатонів

        try:
            idea = json.loads(idea_json)
        except json.JSONDecodeError:
            idea = {}

        # АНТИКРИХКІСТЬ: Якщо хакатону немає у нашій базі (новий запуск з UI),
        # ми витягуємо спонсорів прямо зі згенерованого ШІ-списку sponsor_tech_used!
        sponsors_list = []
        if sponsors_raw:
            try:
                sponsors_list = json.loads(sponsors_raw)
            except Exception:
                pass
        
        if not sponsors_list:
            sponsors_list = idea.get("sponsor_tech_used", [])

        # Real-Time Data Ingestion: отримуємо найсвіжіші новини спонсорів з Hacker News
        realtime_news = get_realtime_sponsor_news(sponsors_list)

        # Кешування ТЗ (залежить від промпту)
        from src.analyzer.prompt_manager import prompt_manager
        prompt_techspec = prompt_manager.get_prompt("techspec_generator")
        ck = cache_key(f"{prediction_id}_{idea_index}_techspec" + str(prompt_techspec))
        techspec = get_cached(ck)
        
        if not techspec:
            logger.info("Кеш не знайдено. Звернення до AI-генератора ТЗ...")
            hackathon_data = {"url": hackathon_url}
            # Передаємо реальні JIT-новини в генератор
            techspec = generate_techspec(
                idea, 
                hackathon_data, 
                hard_constraints=None, 
                realtime_news=realtime_news
            )
            set_cache(ck, techspec)
        else:
            logger.info("ТЗ успішно завантажено з кешу.")

        # Оновлення БД
        con.execute(
            "UPDATE predictions SET selected_idea = ?, techspec = ? WHERE id = ?",
            [idea_index, json.dumps(techspec, ensure_ascii=False), prediction_id]
        )
        con.commit()
        logger.info("ТЗ успішно збережено в базі даних.")
        
        return techspec
        
    except Exception as e:
        logger.error(f"Помилка в пайплайні ТЗ: {e}")
        return {"error": str(e)}
    finally:
        if 'con' in locals():
            con.close()

if __name__ == "__main__":
    print("=== ТЕСТУВАННЯ ПАЙПЛАЙНУ ТЗ З НОВИНАМИ ===")
    try:
        con = get_connection()
        # Автоматично беремо останнє успішне передбачення
        last_pred = con.execute("SELECT id, hackathon_url FROM predictions ORDER BY generated_at DESC LIMIT 1").fetchone()
        con.close()
        
        if last_pred:
            pred_id, h_url = last_pred
            print(f"🔄 Знайдено останнє передбачення: {pred_id}. Генеруємо ТЗ для Ідеї #1...")
            result = generate_and_save_techspec(pred_id, 1, h_url)
            print("\n📋 ОТРИМАНЕ ТЗ (Короткий огляд):")
            print(json.dumps({k: v for k, v in result.items() if k in ['project_name', 'tech_stack']}, indent=2, ensure_ascii=False))
        else:
            print("❌ В базі немає передбачень. Спочатку запустіть src/analyzer/pipeline.py")
    except Exception as e:
        print(f"Помилка тестування: {e}")
