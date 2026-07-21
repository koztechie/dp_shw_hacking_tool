import hashlib
import sys
from pathlib import Path

import joblib
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

from src.logger import logger  # noqa: E402

MODEL_DIR = PROJECT_ROOT / "data" / "models"
MODEL_PATH = MODEL_DIR / "best_model.pkl"
SIGNATURE_PATH = MODEL_DIR / "best_model.sig"


def _verify_signature(file_path: Path, sig_path: Path) -> bool:
    """Перевіряє цілісність моделі через RSA підпис (або HMAC для локального використання)."""
    if not sig_path.exists():
        logger.warning("Відсутній файл підпису моделі. Запускаємо в режимі довіри (dev).")
        return True  # Для локального dev-оточення
    try:
        # Для простоти використовуємо HMAC-SHA256 з ключем з env
        import hmac, os
        secret = os.getenv("MODEL_SIGN_KEY", "dev-local-key").encode()
        expected = sig_path.read_bytes()
        computed = hmac.new(secret, file_path.read_bytes(), hashlib.sha256).digest()
        return hmac.compare_digest(expected, computed)
    except Exception as e:
        logger.error(f"Помилка верифікації підпису моделі: {e}")
        return False


def load_model():
    """Завантажує найкращу натреновану модель та список її ознак."""
    if not MODEL_PATH.exists():
        raise FileNotFoundError(
            "❌ Файли моделей не знайдені у data/models/. "
            "Будь ласка, запустіть тренування: python src/ml/train_ensemble.py"
        )
    
    if not _verify_signature(MODEL_PATH, SIGNATURE_PATH):
        raise RuntimeError("🔒 ПОМИЛКА: Підпис моделі не валідний! Можливо, файл було підмінено.")
    
    # joblib стійкіший до великих numpy-масивів, ніж pickle
    model = joblib.load(MODEL_PATH)
    
    features_path = MODEL_DIR / "feature_names.pkl"
    with open(features_path, "rb") as f:
        feature_names = joblib.load(f)
    
    return model, feature_names


def validate_features(features: dict, feature_names: list) -> dict:
    """
    Антикрихка валідація вхідних features перед прогнозуванням.
    """
    validated = {}
    missing_features = []
    type_errors = []

    for feat_name in feature_names:
        if feat_name not in features:
            missing_features.append(feat_name)
            validated[feat_name] = 0  # Заповнюємо нулем
        else:
            val = features[feat_name]

            # Перевірка типів
            if isinstance(val, bool):
                validated[feat_name] = int(val)
            elif isinstance(val, (int, float)):
                validated[feat_name] = val
            else:
                type_errors.append(feat_name)
                try:
                    validated[feat_name] = float(val)
                except (ValueError, TypeError):
                    validated[feat_name] = 0

    if missing_features:
        logger.warning(f"⚠️ Відсутні features (заповнено нулями): {missing_features}")

    if type_errors:
        logger.warning(f"⚠️ Неправильні типи features (конвертовано): {type_errors}")

    return validated


def predict_win_probability(features: dict) -> float:
    """Приймає словник ознак проекту, повертає ймовірність перемоги 0.0–1.0."""
    try:
        model, feature_names = load_model()

        # КРИТИЧНИЙ ФІКС: Валідація features
        validated_features = validate_features(features, feature_names)

        # Будуємо рядок значень у строгому порядку ознак моделі
        row = [validated_features[f] for f in feature_names]

        # АНТИКРИХКІСТЬ: Огортаємо в DataFrame з назвами стовпців
        row_df = pd.DataFrame([row], columns=feature_names)

        # Підтримка Soft Voting Ensemble (dict з rf та xgb)
        if isinstance(model, dict) and "rf" in model and "xgb" in model:
            rf_prob = model["rf"].predict_proba(row_df)[0][1]
            xgb_prob = model["xgb"].predict_proba(row_df)[0][1]
            weights = model.get("weights", (0.4, 0.6))
            prob = weights[0] * rf_prob + weights[1] * xgb_prob
        else:
            # Зворотна сумісність зі StackingClassifier та звичайними моделями
            prob = model.predict_proba(row_df)[0][1]

        # Sanity check
        if prob < 0 or prob > 1:
            logger.error(f"Model returned invalid probability: {prob}")
            return 0.0

        # Логування розподілу для виявлення дрейфу
        logger.debug(f"Prediction: {prob:.4f}")

        logger.info(f"Передбачено ймовірність перемоги для '{features.get('title', 'Проекту')}': {prob:.4f}")
        return float(prob)
    except Exception as e:
        logger.error(f"Помилка прогнозування: {e}")
        return 0.0
