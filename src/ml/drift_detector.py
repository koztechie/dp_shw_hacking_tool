import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from scipy.stats import chi2_contingency, ks_2samp

# Гарантуємо правильні шляхи імпорту
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import DB_PATH  # noqa: E402
from src.logger import logger  # noqa: E402


def calculate_psi(expected: pd.DataFrame, actual: pd.DataFrame, buckets: int = 10) -> float:
    """
    Population Stability Index для оцінки загального дрейфу.
    """

    def psi_for_column(expected_col, actual_col):
        breakpoints = np.quantile(expected_col, np.linspace(0, 1, buckets + 1))
        breakpoints[0] = -np.inf
        breakpoints[-1] = np.inf

        expected_counts = np.histogram(expected_col, bins=breakpoints)[0]
        actual_counts = np.histogram(actual_col, bins=breakpoints)[0]

        # Уникаємо ділення на нуль
        expected_pct = (expected_counts + 1e-6) / (len(expected_col) + 1e-6 * buckets)
        actual_pct = (actual_counts + 1e-6) / (len(actual_col) + 1e-6 * buckets)

        psi = np.sum((actual_pct - expected_pct) * np.log(actual_pct / expected_pct))
        return psi

    psi_total = 0.0
    for col in expected.columns:
        if col in actual.columns:
            psi_total += psi_for_column(expected[col].values, actual[col].values)

    if len(expected.columns) == 0:
        return 0.0

    return psi_total / len(expected.columns)


def trigger_retraining():
    """
    Автоматичний запуск перетренування моделі при виявленні drift.
    Оновлює last_train_count.txt щоб уникнути нескінченного циклу перетренування.
    """
    logger.info("🔄 Запуск автоматичного перетренування моделі...")
    try:
        from src.ml.train_ensemble import train_ensemble
        import time as _time
        import duckdb as _duckdb

        train_ensemble()

        # АНТИКРИХКІСТЬ: Оновлюємо лічильник та таймстамп щоб retrain-check не зациклювався
        try:
            con = _duckdb.connect(DB_PATH, read_only=True)
            current_count = con.execute("SELECT COUNT(*) FROM hackathons").fetchone()[0]
            con.close()
            count_file = PROJECT_ROOT / "data" / "models" / "last_train_count.txt"
            count_file.parent.mkdir(parents=True, exist_ok=True)
            count_file.write_text(str(current_count), encoding="utf-8")

            time_file = PROJECT_ROOT / "data" / "models" / "last_train_time.txt"
            time_file.write_text(str(_time.time()), encoding="utf-8")
        except Exception as count_err:
            logger.warning(f"Не вдалось оновити last_train_count.txt: {count_err}")

        logger.info("✅ Модель успішно перетренована!")
    except Exception as e:
        logger.error(f"Помилка автоматичного перетренування: {e}")


def detect_drift() -> bool:
    """
    Виявляє Data Drift за допомогою:
    - KS-test для числових ознак
    - Chi-squared test для категоріальних ознак
    - Population Stability Index (PSI) для загальної стабільності
    """
    try:
        con = duckdb.connect(DB_PATH, read_only=True)
        df = con.execute("""
            SELECT f.description_length, f.tech_count, f.novelty_score, f.prize_numeric,
                   f.uses_sponsor_tech, f.has_video_demo, f.has_github, p.likes, p.scraped_at
            FROM features f
            JOIN projects p ON f.project_id = p.id
            ORDER BY p.scraped_at DESC
        """).fetchdf()
    except Exception as e:
        # АНТИКРИХКІСТЬ: Блокування під час запису є штатною ситуацією для DuckDB
        logger.info(f"База тимчасово зайнята під час перевірки дрейфу (обробку пропущено): {e}")
        return False
    finally:
        if "con" in locals():
            con.close()

    if len(df) < 500:
        return False

    df = df.fillna(0)

    # Розділяємо на числові та категоріальні ознаки
    numeric_features = ["description_length", "tech_count", "novelty_score", "prize_numeric", "likes"]
    categorical_features = ["uses_sponsor_tech", "has_video_demo", "has_github"]

    split_idx = int(len(df) * 0.8)
    ref_data = df.iloc[:split_idx]
    curr_data = df.iloc[split_idx:]

    drift_count = 0
    drifted_features = []

    # KS-test для числових ознак
    for col in numeric_features:
        if col in df.columns:
            stat, p_value = ks_2samp(ref_data[col], curr_data[col])
            if p_value < 0.05:
                drift_count += 1
                drifted_features.append(f"{col} (KS p={p_value:.3f})")

    # Chi-squared test для категоріальних ознак
    for col in categorical_features:
        if col in df.columns:
            # Створюємо contingency table
            contingency = pd.crosstab(
                pd.concat([ref_data[col], curr_data[col]]),
                pd.Series(["ref"] * len(ref_data) + ["curr"] * len(curr_data)),
            )

            if contingency.shape[0] > 1 and contingency.shape[1] > 1:
                chi2, p_value, _, _ = chi2_contingency(contingency)
                if p_value < 0.05:
                    drift_count += 1
                    drifted_features.append(f"{col} (Chi2 p={p_value:.3f})")

    # Population Stability Index (PSI)
    psi_score = calculate_psi(ref_data[numeric_features], curr_data[numeric_features])

    # КРИТИЧНИЙ ФІКС: Більш суворий поріг
    # Drift виявлено, якщо:
    # 1. Більше 30% ознак дрейфують, АБО
    # 2. PSI > 0.2 (значний дрейф)
    drift_threshold = max(3, int(len(numeric_features + categorical_features) * 0.3))

    if drift_count >= drift_threshold or psi_score > 0.2:
        logger.info(
            f"📊 Виявлено дрейф: {drift_count} ознак змінились, PSI={psi_score:.3f}. "
            f"Дрейфуючі: {drifted_features}"
        )
        return True

    logger.info(f"✅ Дані стабільні. Drift count: {drift_count}, PSI={psi_score:.3f}")
    return False


if __name__ == "__main__":
    is_drifting = detect_drift()
    print(f"\nСтатус дрейфу: {'ВИЯВЛЕНО' if is_drifting else 'ВІДСУТНІЙ'}")
