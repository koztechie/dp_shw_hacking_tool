import hashlib
import pickle
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.logger import logger  # noqa: E402


def safe_pickle_load(file_path: Path, checksums_path: Path = None) -> object:
    """Безпечна десеріалізація pickle з перевіркою SHA-256."""
    if checksums_path and checksums_path.exists():
        with open(file_path, "rb") as f:
            current_hash = hashlib.sha256(f.read()).hexdigest()
        with open(checksums_path) as f:
            saved_hashes = dict(line.strip().split(":", 1) for line in f if ":" in line)
        expected = saved_hashes.get(file_path.name)
        if expected and current_hash != expected:
            raise ValueError(f"🚨 Файл {file_path.name} скомпрометовано!")

    with open(file_path, "rb") as f:
        return pickle.load(f)


def load_model():
    """Завантажує найкращу натреновану модель та список її ознак."""
    models_dir = PROJECT_ROOT / "data" / "models"
    model_path = models_dir / "best_model.pkl"
    features_path = models_dir / "feature_names.pkl"
    checksums_path = models_dir / "checksums.txt"

    if not model_path.exists() or not features_path.exists():
        raise FileNotFoundError(
            "❌ Файли моделей не знайдені у data/models/. "
            "Будь ласка, запустіть тренування: python src/ml/train_ensemble.py"
        )

    model = safe_pickle_load(model_path, checksums_path)
    feature_names = safe_pickle_load(features_path, checksums_path)

    return model, feature_names


def predict_win_probability(features: dict) -> float:
    """Приймає словник ознак проекту, повертає ймовірність перемоги 0.0–1.0."""
    try:
        model, feature_names = load_model()

        row = []
        for f in feature_names:
            val = features.get(f, 0)
            if isinstance(val, bool):
                val = int(val)
            row.append(val)

        row_df = pd.DataFrame([row], columns=feature_names)

        # Підтримка Soft Voting Ensemble (dict з rf та xgb)
        if isinstance(model, dict) and "rf" in model and "xgb" in model:
            rf_prob = model["rf"].predict_proba(row_df)[0][1]
            xgb_prob = model["xgb"].predict_proba(row_df)[0][1]
            weights = model.get("weights", (0.4, 0.6))
            prob = weights[0] * rf_prob + weights[1] * xgb_prob
        else:
            # Зворотна сумісність зі StackingClassifier
            prob = model.predict_proba(row_df)[0][1]

        return float(prob)
    except Exception as e:
        logger.error(f"Помилка прогнозування: {e}")
        return 0.0
