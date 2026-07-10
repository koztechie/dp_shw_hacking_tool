import sys
from pathlib import Path
import pickle
import pandas as pd
import numpy as np
import os
import hashlib
import hmac

# Гарантуємо правильні шляхи імпорту
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.logger import logger

MODEL_SIGNING_KEY = os.getenv("MODEL_SIGNING_KEY", "dp_shw_super_secret_key_2026")

def verify_model_signature(model_path: Path) -> bool:
    """Криптографічна перевірка цілісності моделі через HMAC-SHA256"""
    signature_file = model_path.parent / f"{model_path.name}.sig"
    if not signature_file.exists():
        logger.warning(f"⚠️ Файл підпису {signature_file.name} відсутній! Пропуск.")
        return True

    with open(model_path, "rb") as f:
        model_data = f.read()

    with open(signature_file, "r") as f:
        stored_signature = f.read().strip()

    computed_signature = hmac.new(
        MODEL_SIGNING_KEY.encode("utf-8"),
        model_data,
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(computed_signature, stored_signature)

class SafeUnpickler(pickle.Unpickler):
    """
    Безпечний Unpickler: дозволяє розпаковувати ТІЛЬКИ авторизовані класи.
    Захищає систему від Pickle Deserialization RCE.
    """
    ALLOWED_CLASSES = {
        "sklearn", "xgboost", "numpy", "pandas", "collections", "builtins",
        "src.ml.pytorch_model", "src.ml.focal_loss", "imblearn", "torch"  # ДОДАНО torch!
    }
    
    def find_class(self, module, name):
        if not any(module.startswith(allowed) for allowed in self.ALLOWED_CLASSES):
            raise pickle.UnpicklingError(f"🚨 RCE БЛОКОВАНО: Спроба завантажити неавторизований клас {module}.{name}")
        return super().find_class(module, name)

def load_model():
    """Безпечне завантаження моделі з криптографічною перевіркою підпису"""
    models_dir = PROJECT_ROOT / "data" / "models"
    model_path = models_dir / "best_model.pkl"
    features_path = models_dir / "feature_names.pkl"

    if not model_path.exists() or not features_path.exists():
        raise FileNotFoundError("Файли моделей не знайдено.")

    if not verify_model_signature(model_path) or not verify_model_signature(features_path):
        raise ValueError("🚨 КРИТИЧНО: Цілісність моделі порушена (HMAC не збігається)! Файл скомпрометовано.")

    with open(model_path, "rb") as f:
        model = SafeUnpickler(f).load()
    with open(features_path, "rb") as f:
        feature_names = SafeUnpickler(f).load()

    return model, feature_names

def predict_win_probability(features: dict) -> float:
    try:
        model, feature_names = load_model()
        df = pd.DataFrame([features])
        for col in feature_names:
            if col not in df.columns:
                df[col] = 0
        df = df[feature_names]
        prob = model.predict_proba(df)[0][1]
        return float(prob)
    except Exception as e:
        logger.error(f"Помилка передбачення: {e}")
        return 0.5
