import hmac
import hashlib
import os
from pathlib import Path

import joblib
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import StratifiedKFold, cross_val_score

from config.settings import SETTINGS
from src.logger import logger
from src.ml.prepare_dataset import prepare_dataset_full

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

def train():
    logger.info("Початок підготовки даних (Full Dataset для CV)...")
    X, y = prepare_dataset_full()

    # Створюємо модель із вагою класів, пропорційною дисбалансу
    model = RandomForestClassifier(
        n_estimators=100,  # Зменшуємо для швидшості на слабкому залізі
        class_weight="balanced",  # Корекція дисбалансу 3.7%
        max_depth=8,  # Менша глибина = менше RAM
        random_state=42,
        n_jobs=SETTINGS.cpu_cores  # Контрольовано!
    )

    logger.info("Проведення крос-валідації (Stratified 5-Fold)...")
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    cv_scores = cross_val_score(model, X, y, cv=skf, scoring='roc_auc')
    
    logger.info(f"CV ROC-AUC: {cv_scores.mean():.4f} (+/- {cv_scores.std()*2:.4f})")
    
    logger.info("Тренування фінальної моделі Random Forest на всіх даних... (зачекайте кілька секунд)")
    model.fit(X, y)
    logger.info("Тренування завершено.")

    # Обчислюємо важливість ознак
    print("\n=== ВАЖЛИВІСТЬ ОЗНАК (Feature Importance) ===")
    feature_importance = pd.Series(
        model.feature_importances_,
        index=X.columns
    ).sort_values(ascending=False)
    
    for feature, val in feature_importance.items():
        print(f"  {feature:<25}: {val:.4f}")

    # Безпечно створюємо папку для моделей
    models_dir = PROJECT_ROOT / "data" / "models"
    models_dir.mkdir(parents=True, exist_ok=True)

    # Зберігаємо модель
    model_path = models_dir / "random_forest.pkl"
    joblib.dump(model, model_path)
        
    # Створюємо копію як найкращу модель за замовчуванням
    best_model_path = models_dir / "best_model.pkl"
    joblib.dump(model, best_model_path)

    # Зберігаємо назви ознак для використання в майбутньому пайплайні
    feature_names_path = models_dir / "feature_names.pkl"
    joblib.dump(list(X.columns), feature_names_path)

    # Генеруємо HMAC підпис
    # import hmac, hashlib, os
    signature_path = models_dir / "best_model.sig"
    secret = os.getenv("MODEL_SIGN_KEY", "dev-local-key").encode()
    sig = hmac.new(secret, best_model_path.read_bytes(), hashlib.sha256).digest()
    signature_path.write_bytes(sig)

    logger.info(f"Модель успішно збережено у {model_path}")
    return model

if __name__ == "__main__":
    train()
