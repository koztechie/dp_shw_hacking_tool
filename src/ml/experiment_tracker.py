import sys
import uuid
import json
import pickle
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import duckdb
from src.logger import logger
from config.settings import DB_PATH

try:
    import sentry_sdk
except ImportError:
    sentry_sdk = None

def log_experiment(model_name: str, params: dict, metrics: dict, model_obj) -> str:
    """
    Зберігає інформацію про запуск моделі (Model Registry & Experiment Tracking).
    """
    run_id = str(uuid.uuid4())
    
    # Створюємо директорію Model Registry
    registry_dir = PROJECT_ROOT / "data" / "models" / "registry"
    registry_dir.mkdir(parents=True, exist_ok=True)
    
    # Зберігаємо фізичний файл (артефакт) моделі з унікальним ID
    model_path = registry_dir / f"{model_name}_{run_id}.pkl"
    with open(model_path, "wb") as f:
        pickle.dump(model_obj, f)
        
    try:
        con = duckdb.connect(DB_PATH)
        con.execute("""
            INSERT INTO experiments (run_id, model_name, hyperparameters, metrics, model_path)
            VALUES (?, ?, ?, ?, ?)
        """, [
            run_id, 
            model_name, 
            json.dumps(params, ensure_ascii=False), 
            json.dumps(metrics, ensure_ascii=False), 
            str(model_path)
        ])
        logger.info(f"📊 Експеримент залоговано! Run ID: {run_id} | Metrics: {metrics}")
    except Exception as e:
        logger.error(f"Помилка запису експерименту в БД: {e}")
    finally:
        if 'con' in locals(): con.close()
        
    return run_id

def generate_weekly_report():
    """Automated Reporting: аналізує експерименти та відправляє звіт у Sentry."""
    try:
        con = duckdb.connect(DB_PATH, read_only=True)
        # Витягуємо експерименти за останні 7 днів
        df = con.execute("""
            SELECT run_id, model_name, metrics, timestamp 
            FROM experiments 
            WHERE timestamp >= current_date - INTERVAL 7 DAY
            ORDER BY timestamp DESC
        """).fetchdf()
    except Exception as e:
        logger.error(f"Помилка генерації звіту: {e}")
        return
    finally:
        if 'con' in locals(): con.close()
        
    if df.empty:
        logger.info("Немає нових експериментів для звіту.")
        return
        
    report = f"📈 Щотижневий звіт якості моделей (MLOps)\nПроведено експериментів: {len(df)}\n\n"
    for _, row in df.iterrows():
        report += f"[{row['timestamp']}] {row['model_name']} -> {row['metrics']}\n"
        
    logger.info(report)
    if sentry_sdk:
        sentry_sdk.capture_message(report, level="info")
        logger.info("Звіт успішно надіслано в Sentry.")

if __name__ == "__main__":
    generate_weekly_report()
