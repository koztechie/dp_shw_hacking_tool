import sys
from pathlib import Path
import pickle
import pandas as pd
import numpy as np

# Гарантуємо правильні шляхи імпорту
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.ml.prepare_dataset import prepare_dataset
from src.logger import logger

from sklearn.ensemble import RandomForestClassifier, StackingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold
from sklearn.metrics import classification_report, roc_auc_score
from xgboost import XGBClassifier

def train_ensemble():
    logger.info("Початок підготовки даних для Ансамблю (Stacking)...")
    X_train, X_test, y_train, y_test = prepare_dataset()

    # Динамічно розраховуємо коефіцієнт дисбалансу
    neg_count = (y_train == 0).sum()
    pos_count = (y_train == 1).sum()
    imbalance_ratio = neg_count / pos_count if pos_count > 0 else 1.0

    # 1. Базові моделі (n_jobs=1 для захисту від перевантаження слабкого CPU)
    rf_base = RandomForestClassifier(
        n_estimators=150, 
        class_weight="balanced", 
        max_depth=8, 
        random_state=42, 
        n_jobs=1
    )
    
    xgb_base = XGBClassifier(
        n_estimators=150, 
        scale_pos_weight=imbalance_ratio, 
        max_depth=5, 
        learning_rate=0.08, 
        random_state=42, 
        n_jobs=1,
        eval_metric="logloss"
    )

    # 2. Мета-модель
    meta_model = LogisticRegression(class_weight="balanced", random_state=42)

    # 3. Ансамбль
    ensemble = StackingClassifier(
        estimators=[('rf', rf_base), ('xgb', xgb_base)],
        final_estimator=meta_model,
        cv=5,
        n_jobs=-1
    )

    logger.info("🚀 Тренування ансамблю моделей...")
    ensemble.fit(X_train, y_train)
    logger.info("Тренування завершено! Оцінюємо якість...")

    y_pred = ensemble.predict(X_test)
    y_prob = ensemble.predict_proba(X_test)[:, 1]

    print("\n=== РЕЗУЛЬТАТИ МЕТА-МОДЕЛІ (STACKING ENSEMBLE) ===")
    print(classification_report(y_test, y_pred, target_names=["Програв", "Переможець"]))
    
    ens_auc = roc_auc_score(y_test, y_prob)
    print(f"🌟 Ensemble ROC-AUC Score: {ens_auc:.4f}")
    
    # Зберігаємо модель ансамблю в її окремий файл
    models_dir = Path("data/models")
    with open(models_dir / "ensemble.pkl", "wb") as f:
        pickle.dump(ensemble, f)

    # АНТИКРИХКІСТЬ: Порівняння з поточним лідером у best_model.pkl
    best_model_path = models_dir / "best_model.pkl"
    current_best_auc = 0.0
    current_best_model = None

    if best_model_path.exists():
        try:
            with open(best_model_path, "rb") as f:
                current_best_model = pickle.load(f)
            # Тестуємо поточного лідера на поточній вибірці
            best_prob = current_best_model.predict_proba(X_test)[:, 1]
            current_best_auc = roc_auc_score(y_test, best_prob)
            print(f"\n📈 Порівняння: Поточний лідер в БД ROC-AUC = {current_best_auc:.4f} vs Новий Ансамбль ROC-AUC = {ens_auc:.4f}")
        except Exception as e:
            logger.warning(f"Не вдалося порівняти з поточним лідером: {e}")

    # Оновлюємо головну модель тільки якщо ансамбль ДІЙСНО переміг!
    if ens_auc >= current_best_auc or current_best_model is None:
        print("\n🏆 ПЕРЕМОЖЕЦЬ: Ансамбль моделей очолив лідерство!")
        print("  Файл best_model.pkl успішно оновлено Ансамблем.")
        with open(best_model_path, "wb") as f:
            pickle.dump(ensemble, f)
    else:
        print(f"\n🏆 ПЕРЕМОЖЕЦЬ: Поточний лідер ({current_best_auc:.4f}) зберіг першість!")
        print("  Файл best_model.pkl залишено без змін.")

    # Завжди оновлюємо список фіч
    with open(models_dir / "feature_names.pkl", "wb") as f:
        pickle.dump(list(X_train.columns), f)

if __name__ == "__main__":
    train_ensemble()
