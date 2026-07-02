import sys
from pathlib import Path
import duckdb
import pandas as pd
from sklearn.model_selection import train_test_split

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import DB_PATH
from src.ml.feature_store import LightweightFeatureStore
from src.logger import logger

def prepare_dataset():
    logger.info("Зчитування даних для Temporal Validation (Out-of-Time Split)...")
    try:
        store = LightweightFeatureStore()
        # 1. Автоматично робимо Parquet-зліпок перед кожним перенавчанням (Feature Versioning)
        store.snapshot_features()
        # 2. Отримуємо дані з перевіркою Data Quality (Feature Monitoring)
        df = store.get_training_data()
    except Exception as e:
        logger.error(f"Помилка Feature Store: {e}")
        raise e

    if df.empty:
        raise ValueError("Датасет порожній!")

    df = df.fillna(0)
    
    bool_cols = ["uses_sponsor_tech", "has_social_angle", "has_github", "sponsor_challenge_match", "has_video_demo", "is_winner"]
    for col in bool_cols:
        if col in df.columns:
            df[col] = df[col].astype(int)

    X = df.drop("is_winner", axis=1)
    y = df["is_winner"]

    # TEMPORAL VALIDATION: shuffle=False гарантує, що модель не зазиратиме в майбутнє
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, shuffle=False
    )

    print("=== ПІДГОТОВКА ДАТАСЕТУ (Temporal Validation) ===")
    print(f"Тренування на МИНУЛОМУ: {len(X_train)} проектів")
    print(f"Тестування на МАЙБУТНЬОМУ:  {len(X_test)} проектів")
    print(f"Win rate train: {y_train.mean()*100:.2f}% | Win rate test:  {y_test.mean()*100:.2f}%")

    return X_train, X_test, y_train, y_test

if __name__ == "__main__":
    prepare_dataset()
