import sys
from pathlib import Path
import json

# Гарантуємо правильні шляхи імпорту
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.logger import logger
from src.analyzer.techspec_generator import generate_techspec
from src.analyzer.cache import cache_key, get_cached, set_cache
from src.db import get_connection

def generate_and_save_techspec(prediction_id: str, idea_index: int, hackathon_url: str) -> dict:
    """
    Отримує обрану ідею з бази, генерує для неї детальне ТЗ та зберігає результат.
    """
    logger.info(f"Запуск генерації ТЗ для передбачення {prediction_id} (Ідея #{idea_index})")
    
    if idea_index not in [1, 2, 3]:
        return {"error": "Invalid idea_index. Must be 1, 2, or 3."}

    try:
        con = get_connection()
        
        # АНТИКРИХКІСТЬ: Явний запит конкретної колонки замість небезпечного індексування масиву
        query = f"SELECT idea_{idea_index}_description FROM predictions WHERE id = ?"
        row = con.execute(query, [prediction_id]).fetchone()

        if not row or not row[0]:
            logger.error(f"Опис ідеї #{idea_index} або передбачення не знайдено в БД.")
            return {"error": "Prediction or idea not found"}

        idea_json = row[0]
        try:
            idea = json.loads(idea_json)
        except json.JSONDecodeError:
            idea = {}

        hackathon_data = {"url": hackathon_url}

        # Кешування ТЗ
        ck = cache_key(f"{prediction_id}_{idea_index}_techspec")
        techspec = get_cached(ck)
        
        if not techspec:
            logger.info("Кеш не знайдено. Звернення до AI-генератора ТЗ...")
            # Ми передаємо hard_constraints=None, оскільки сама ідея вже була згенерована з урахуванням обмежень
            techspec = generate_techspec(idea, hackathon_data, hard_constraints=None)
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
    print("=== ТЕСТУВАННЯ ПАЙПЛАЙНУ ТЗ (Етап 39) ===")
    try:
        con = get_connection()
        # Автоматично беремо останнє успішне передбачення з Етапу 38
        last_pred = con.execute("SELECT id, hackathon_url FROM predictions ORDER BY generated_at DESC LIMIT 1").fetchone()
        con.close()
        
        if last_pred:
            pred_id, h_url = last_pred
            print(f"🔄 Знайдено останнє передбачення: {pred_id}")
            print(f"🔗 Хакатон: {h_url}")
            print("⏳ Генеруємо ТЗ для Ідеї #1 (це займе близько 10-15 секунд)...")
            
            result = generate_and_save_techspec(pred_id, 1, h_url)
            
            print("\n📋 ОТРИМАНЕ ТЗ (Короткий огляд архітектури та стеку):")
            # Виводимо лише частину JSON, щоб не перевантажувати термінал
            summary = {k: v for k, v in result.items() if k in ['project_name', 'architecture', 'tech_stack']}
            print(json.dumps(summary, indent=2, ensure_ascii=False))
        else:
            print("❌ В базі ще немає передбачень.")
            print("Будь ласка, спочатку запустіть: python src/analyzer/pipeline.py")
    except Exception as e:
        print(f"Помилка тестування: {e}")
