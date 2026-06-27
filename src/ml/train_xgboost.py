import sys
from pathlib import Path
import pickle
import pandas as pd
import numpy as np
from xgboost import XGBClassifier
from sklearn.metrics import classification_report, roc_auc_score

# Гарантуємо правильні шляхи імпорту
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.ml.prepare_dataset import prepare_dataset
from src.logger import logger

def train_xgboost():
    logger.info("Початок підготовки даних для XGBoost...")
    X_train, X_test, y_train, y_test = prepare_dataset()

    # Динамічно розраховуємо точний коефіцієнт дисбалансу класів
    neg_count = (y_train == 0).sum()
    pos_count = (y_train == 1).sum()
    imbalance_ratio = neg_count / pos_count if pos_count > 0 else 1.0
    
    logger.info(f"Обчислено коефіцієнт дисбалансу класів (Neg/Pos): {imbalance_ratio:.2f}")

    # Створюємо модель градієнтного бустингу
    model = XGBClassifier(
        n_estimators=200,
        scale_pos_weight=imbalance_ratio,  # Динамічне фокусування
        max_depth=6,
        learning_rate=0.1,
        random_state=42,
        n_jobs=-1,  # Всі ядра процесора AMD A4
        eval_metric="logloss"
    )

    logger.info("Тренування моделі XGBoost...")
    model.fit(X_train, y_train)
    logger.info("Тренування XGBoost завершено. Оцінюємо якість...")

    # Прогнози
    y_pred = model.predict(X_test)
    y_prob = model.predict_proba(X_test)[:, 1]

    print("\n=== РЕЗУЛЬТАТИ МОДЕЛІ XGBOOST ===")
    print(classification_report(y_test, y_pred, target_names=["Програв", "Переможець"]))
    
    xgb_auc = roc_auc_score(y_test, y_prob)
    print(f"XGBoost ROC-AUC Score: {xgb_auc:.4f}")

    # Важливість ознак
    print("\n=== ВАЖЛИВІСТЬ ОЗНАК (XGBoost Feature Importance) ===")
    feature_importance = pd.Series(
        model.feature_importances_,
        index=X_train.columns
    ).sort_values(ascending=False)
    
    for feature, val in feature_importance.items():
        print(f"  {feature:<25}: {val:.4f}")

    # Зберігаємо модель XGBoost
    models_dir = Path("data/models")
    with open(models_dir / "xgboost.pkl", "wb") as f:
        pickle.dump(model, f)

    # ПОРІВНЯННЯ З RANDOM FOREST
    rf_path = models_dir / "random_forest.pkl"
    rf_auc = 0.0
    
    if rf_path.exists():
        try:
            with open(rf_path, "rb") as f:
                rf_model = pickle.load(f)
            rf_prob = rf_model.predict_proba(X_test)[:, 1]
            rf_auc = roc_auc_score(y_test, rf_prob)
            print(f"\n📈 Порівняння: Random Forest ROC-AUC = {rf_auc:.4f} vs XGBoost ROC-AUC = {xgb_auc:.4f}")
        except Exception as e:
            logger.warning(f"Не вдалося порівняти з Random Forest: {e}")
    else:
        logger.info("Попередній бекап Random Forest не знайдено.")

    # Автоматично обираємо та зберігаємо найкращу модель
    best_model_path = models_dir / "best_model.pkl"
    if xgb_auc >= rf_auc:
        print("\n🏆 ПЕРЕМОЖЕЦЬ: XGBoost показав вищу (або рівну) точність!")
        print("  Файл best_model.pkl оновлено моделлю XGBoost.")
        with open(best_model_path, "wb") as f:
            pickle.dump(model, f)
    else:
        print("\n🏆 ПЕРЕМОЖЕЦЬ: Random Forest зберіг лідерство!")
        print("  Файл best_model.pkl залишено з моделлю Random Forest.")
        if rf_path.exists():
            # На випадок якщо ми перезаписали його раніше
            with open(rf_path, "rb") as f:
                rf_model = pickle.load(f)
            with open(best_model_path, "wb") as f:
                pickle.dump(rf_model, f)

if __name__ == "__main__":
    train_xgboost()
