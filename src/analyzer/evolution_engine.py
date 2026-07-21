import sys
from pathlib import Path
import json
import os
import sentry_sdk

# Гарантуємо правильні шляхи імпорту

import duckdb
from src.logger import logger
from src.analyzer.ai_client import generate_json_with_failover
from config.settings import DB_PATH
from scipy import stats

def detect_data_drift() -> dict:
    """
    Виконує статистичний тест Колмогорова-Смирнова (KS-test) 
    для виявлення дрейфу даних (Data Drift) на основі 'novelty_score'.
    """
    con = duckdb.connect(DB_PATH, read_only=True)
    try:
        # Порівнюємо розподіл novelty_score останніх 50 проектів vs перших 50
        recent = con.execute("SELECT novelty_score FROM features ORDER BY project_id DESC LIMIT 50").fetchdf()
        baseline = con.execute("SELECT novelty_score FROM features ORDER BY project_id ASC LIMIT 50").fetchdf()
        
        if recent.empty or baseline.empty or len(recent) < 10 or len(baseline) < 10:
            return {"drift_detected": False, "reason": "Not enough data"}
            
        ks_stat, p_value = stats.ks_2samp(baseline['novelty_score'].dropna(), recent['novelty_score'].dropna())
        
        return {
            "drift_detected": bool(p_value < 0.05),
            "ks_statistic": float(ks_stat),
            "p_value": float(p_value),
            "recommendation": "Retrain model" if p_value < 0.05 else "No action"
        }
    except Exception as e:
        logger.error(f"Помилка KS-test для Data Drift: {e}")
        return {"drift_detected": False, "error": str(e)}
    finally:
        con.close()

def analyze_system_performance() -> dict:
    """
    Аналізує розбіжність між прогнозами моделі та реальними результатами хакатонів.
    Генерує готовий промпт для VS Code Antigravity CLI для покращення коду.
    """
    con = duckdb.connect(DB_PATH, read_only=True)
    
    # Зчитуємо історію зворотного зв'язку та прогнозів
    try:
        feedback_data = con.execute("""
            SELECT 
                f.won as actual_won,
                f.actual_place,
                p.idea_1_score,
                p.selected_idea,
                p.hackathon_url
            FROM feedback f
            JOIN predictions p ON f.prediction_id = p.id
            ORDER BY f.created_at DESC
            LIMIT 10
        """).fetchdf()
    except Exception as e:
        logger.error(f"Помилка зчитування таблиці фідбеку: {e}")
        feedback_data = None
    finally:
        con.close()

    # Режим валідації наявних даних
    if feedback_data is None or feedback_data.empty:
        logger.info("ℹ️ Зворотний зв'язок ще не накопичено. Запуск проактивного режиму еволюції системи...")
        prompt = """
        You are an elite MLOps engineer. We have just launched our Hacking Tool and don't have user feedback yet.
        Proactively suggest one highly advanced feature to add to our 'src/analyzer/feature_extractor.py' to improve prediction accuracy (e.g. checking for video presence or design quality).
        
        Return the result STRICTLY as a JSON object matching this schema:
        {
          "diagnostic_summary": "Proactive recommendation: The model lacks a proxy for video presence or design quality.",
          "recommended_action": "Add a feature 'has_video' to feature_extractor.py and update the DB schema.",
          "antigravity_cli_prompt": "Update src/analyzer/feature_extractor.py to extract 'has_video' from demo_url (True if youtube/vimeo/loom is present). Also update src/db.py and batch_features.py to support this new boolean feature."
        }
        """
    else:
        history = feedback_data.to_dict("records")
        logger.info(f"Аналізуємо {len(history)} записів зворотного зв'язку...")
        
        prompt = f"""
        You are an elite MLOps engineer and AI architect.
        Analyze the mismatch between our model's predictions (predicted win probability) and the actual outcomes.
        
        PERFORMANCE HISTORY:
        {json.dumps(history, indent=2, ensure_ascii=False)}
        
        Identify why the model's predictions are drifting from reality and generate a precise prompt for the VS Code Antigravity CLI to rewrite or tune our features/hyperparameters.
        
        Return the result STRICTLY as a JSON object matching this schema:
        {{
          "diagnostic_summary": "Detailed explanation of the predictive drift.",
          "recommended_action": "Specific change in code (e.g. tune hyperparameters or add new feature)",
          "antigravity_cli_prompt": "A ready-to-copy prompt for VS Code Antigravity CLI to implement the change"
        }}
        """

    result = generate_json_with_failover(prompt)
    return result

def trigger_auto_evolution_check():
    """
    Автоматично викликає аналіз точності моделі.
    У разі наявності рекомендацій - надсилає готовий промпт у Sentry (і на пошту).
    """
    logger.info("🧠 Запуск автоматичної перевірки точності моделі та Data Drift...")
    
    drift_report = detect_data_drift()
    if drift_report.get("drift_detected"):
        logger.warning(f"🚨 DATA DRIFT ВИЯВЛЕНО! KS-статистика: {drift_report.get('ks_statistic')}, p_value: {drift_report.get('p_value')}")
    else:
        logger.info(f"📊 Дані стабільні (Data Drift не виявлено). Деталі: {drift_report}")

    report = analyze_system_performance()
    
    if report and report.get("antigravity_cli_prompt"):
        # Формуємо красивий лист-сповіщення для Sentry
        message = f"""
🧠 [DP_SHW Self-Evolution Engine] Знайдено шлях підвищення точності!

ДІАГНОСТИКА: {report.get('diagnostic_summary')}
РЕКОМЕНДОВАНА ДІЯ: {report.get('recommended_action')}

👉 СКОПІЮЙТЕ ЦЕЙ ПРОМПТ В ANTIGRAVITY CLI ДЛЯ ОНОВЛЕННЯ КОДУ:
{report.get('antigravity_cli_prompt')}
"""
        try:
            # Надсилаємо як Warning-інцидент, щоб Sentry миттєво відправив лист на ProtonMail
            sentry_sdk.capture_message(message, level="warning")
            logger.info("📡 Надіслано звіт про еволюцію моделі в Sentry!")
        except Exception as e:
            logger.error(f"Не вдалося відправити звіт у Sentry: {e}")

if __name__ == "__main__":
    # Тест відправки повідомлення
    trigger_auto_evolution_check()
