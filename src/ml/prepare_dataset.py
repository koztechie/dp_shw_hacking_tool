import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.logger import logger  # noqa: E402
from src.ml.feature_store import LightweightFeatureStore  # noqa: E402


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

    # КРИТИЧНИЙ ФІКС: Явне сортування за часом перед split
    # Feature Store вже сортує за scraped_at DESC, але гарантуємо це тут
    if "scraped_at" in df.columns:
        df = df.sort_values("scraped_at", ascending=True).reset_index(drop=True)
        df = df.drop("scraped_at", axis=1)  # Видаляємо після сортування
    else:
        logger.warning("⚠️ Колонка scraped_at відсутня! Temporal Validation неможлива.")
        # Fallback на випадкове розбиття
        from sklearn.model_selection import train_test_split

        X = df.drop("is_winner", axis=1)
        y = df["is_winner"]
        return train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)

    df = df.fillna(0)

    bool_cols = [
        "uses_sponsor_tech",
        "has_social_angle",
        "has_github",
        "sponsor_challenge_match",
        "has_video_demo",
        "is_winner",
    ]
    for col in bool_cols:
        if col in df.columns:
            df[col] = df[col].astype(int)

    X = df.drop("is_winner", axis=1)
    y = df["is_winner"]

    # КРИТИЧНИЙ ФІКС: TimeSeriesSplit замість train_test_split
    # Це гарантує, що модель ніколи не побачить майбутні дані
    from sklearn.model_selection import TimeSeriesSplit

    tscv = TimeSeriesSplit(n_splits=5)

    # Використовуємо останній fold для тестування
    train_idx, test_idx = None, None
    for train_index, test_index in tscv.split(X):
        train_idx, test_idx = train_index, test_index

    X_train = X.iloc[train_idx]
    X_test = X.iloc[test_idx]
    y_train = y.iloc[train_idx]
    y_test = y.iloc[test_idx]

    print("=== ПІДГОТОВКА ДАТАСЕТУ (TimeSeriesSplit) ===")
    print(f"Тренування на МИНУЛОМУ: {len(X_train)} проектів")
    print(f"Тестування на МАЙБУТНЬОМУ: {len(X_test)} проектів")
    print(f"Win rate train: {y_train.mean() * 100:.2f}% | Win rate test: {y_test.mean() * 100:.2f}%")

    # Перевірка на look-ahead bias
    if y_test.mean() > y_train.mean() * 1.5:
        logger.warning(
            f"🚨 Підозра на look-ahead bias! Win rate test ({y_test.mean() * 100:.2f}%) "
            f"значно вищий за train ({y_train.mean() * 100:.2f}%)"
        )

    return X_train, X_test, y_train, y_test


if __name__ == "__main__":
    prepare_dataset()
