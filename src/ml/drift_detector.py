import sys
from pathlib import Path
import duckdb
import pandas as pd
from scipy.stats import ks_2samp

# Гарантуємо правильні шляхи імпорту
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import DB_PATH
from src.logger import logger

def detect_drift() -> bool:
    """
    Виявляє Data Drift за допомогою тесту Колмогорова-Смирнова.
    Антикрихкість: Безпечно обробляє тимчасові блокування бази даних.
    """
    try:
        con = duckdb.connect(DB_PATH, read_only=True)
        df = con.execute("""
            SELECT f.description_length, f.tech_count, f.novelty_score, f.prize_numeric, p.likes
            FROM features f
            JOIN projects p ON f.project_id = p.id
            ORDER BY p.scraped_at DESC
        """).fetchdf()
    except Exception as e:
        # АНТИКРИХКІСТЬ: Блокування під час запису є штатною ситуацією для DuckDB, 
        # тому використовуємо logger.info замість logger.error, щоб уникнути зайвого шуму в Sentry.
        logger.info(f"База тимчасово зайнята під час перевірки дрейфу (обробку пропущено): {e}")
        return False
    finally:
        if 'con' in locals(): con.close()

    if len(df) < 500:
        return False

    df = df.fillna(0)
    
    split_idx = int(len(df) * 0.8)
    ref_data = df.iloc[:split_idx]
    curr_data = df.iloc[split_idx:]

    drift_count = 0
    drifted_features = []

    for col in df.columns:
        stat, p_value = ks_2samp(ref_data[col], curr_data[col])
        if p_value < 0.05:
            drift_count += 1
            drifted_features.append(col)

    if drift_count >= 2:
        logger.warning(f"🚨 Виявлено Data Drift у фічах: {drifted_features}. Потрібне перенавчання!")
        return True

    logger.info("✅ Дані стабільні. Data Drift відсутній.")
    return False

if __name__ == "__main__":
    is_drifting = detect_drift()
    print(f"\nСтатус дрейфу: {'ВИЯВЛЕНО' if is_drifting else 'ВІДСУТНІЙ'}")
