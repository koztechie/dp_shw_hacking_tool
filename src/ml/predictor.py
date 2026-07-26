import hmac
import os
import gc
import hashlib

import threading
from pathlib import Path

import joblib
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

from src.logger import logger  # noqa: E402

MODEL_DIR = PROJECT_ROOT / "data" / "models"
MODEL_PATH = MODEL_DIR / "best_model.pkl"
SIGNATURE_PATH = MODEL_DIR / "best_model.sig"


_model_cache = None
_model_lock = threading.Lock()
_model_mtime = 0.0

def _get_signing_key() -> bytes:
    # import os
    key = os.getenv("MODEL_SIGN_KEY")
    if not key or key == "dev-local-key":
        raise RuntimeError(
            "🔒 MODEL_SIGN_KEY не встановлений або використовується "
            "дефолтне значення. Встановіть унікальний ключ: "
            "export MODEL_SIGN_KEY=$(openssl rand -hex 32)"
        )
    return key.encode()

def _verify_signature(file_path: Path, sig_path: Path) -> bool:
    # import hmac
    if not sig_path.exists():
        return False

    secret = _get_signing_key()
    expected = sig_path.read_bytes()
    computed = hmac.new(secret, file_path.read_bytes(), hashlib.sha256).digest()
    return hmac.compare_digest(expected, computed)

def _safe_model_load(path: Path) -> dict:
    MAX_MODEL_SIZE = 200 * 1024 * 1024

    if path.stat().st_size > MAX_MODEL_SIZE:
        raise RuntimeError(
            f"🔒 Модель завелика ({path.stat().st_size // (1024*1024)} MB). "
            f"Максимум: {MAX_MODEL_SIZE // (1024*1024)} MB."
        )

    if not _verify_signature(path, path.with_suffix(".sig")):
        raise RuntimeError("🔒 Підпис моделі не валідний! Файл можливо підмінено.")

    return joblib.load(path)

def load_model(force_reload=False):
    global _model_cache, _model_mtime

    if not MODEL_PATH.exists():
        raise FileNotFoundError("ML-модель не знайдена. Запустіть тренування.")

    current_mtime = MODEL_PATH.stat().st_mtime

    with _model_lock:
        if _model_cache is not None and current_mtime == _model_mtime and not force_reload:
            return _model_cache["model"], _model_cache["feature_names"]

        if _model_cache is not None:
            _model_cache = None
            gc.collect()

        model = _safe_model_load(MODEL_PATH)
        features_path = MODEL_DIR / "feature_names.pkl"
        feature_names = _safe_model_load(features_path)

        _model_cache = {"model": model, "feature_names": feature_names}
        _model_mtime = current_mtime
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
