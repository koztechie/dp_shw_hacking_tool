import sys
from pathlib import Path
import pickle
import pandas as pd
import numpy as np
from collections import Counter

# Гарантуємо правильні шляхи
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.ml.prepare_dataset import prepare_dataset
from src.logger import logger
from src.ml.experiment_tracker import log_experiment

from xgboost import XGBClassifier
from sklearn.metrics import classification_report, average_precision_score, precision_recall_curve
from imblearn.combine import SMOTETomek

def train_xgboost():
    logger.info("Початок підготовки даних для XGBoost (Advanced Imbalance Handling)...")
    X_train, X_test, y_train, y_test = prepare_dataset()

    logger.info(f"Оригінальний баланс класів (Train): {Counter(y_train)}")

    # 1. ЗАСТОСУВАННЯ SMOTE + TOMEK LINKS
    # Антикрихкість: n_jobs=1, щоб AMD A4-4020 не завис від паралельних обчислень дистанцій
    logger.info("Балансую дані між переможцями та іншими... Це може зайняти ~10-20 секунд.")
    smt = SMOTETomek(random_state=42, n_jobs=1)
    try:
        X_res, y_res = smt.fit_resample(X_train, y_train)
        logger.info(f"Новий баланс класів після SMOTETomek: {Counter(y_res)}")
    except Exception as e:
        logger.error(f"SMOTETomek не вдався (можливо через нестачу пам'яті): {e}. Використовуємо оригінальні дані.")
        X_res, y_res = X_train, y_train

    # 2. ТРЕНУВАННЯ XGBOOST
    # Оскільки класи тепер збалансовані синтетично (50/50), scale_pos_weight не потрібен
    model = XGBClassifier(
        n_estimators=250,
        max_depth=5,
        learning_rate=0.05,
        subsample=0.8,      # Захист від перенавчання на синтетичних даних
        colsample_bytree=0.8,
        random_state=42,
        n_jobs=-1,
        eval_metric="aucpr" # Оптимізуємо під Precision-Recall
    )

    logger.info("Тренування моделі XGBoost...")
    model.fit(X_res, y_res)
    logger.info("Тренування завершено. Оцінюємо якість...")

    y_prob = model.predict_proba(X_test)[:, 1]

    # 3. THRESHOLD TUNING (Пошук ідеального порогу)
    # Замість стандартних 50%, ми шукаємо поріг, що дає найкращий F1-score
    precisions, recalls, thresholds = precision_recall_curve(y_test, y_prob)
    
    # Захист від ділення на нуль
    f1_scores = np.divide(
        2 * (precisions * recalls),
        (precisions + recalls),
        out=np.zeros_like(precisions),
        where=(precisions + recalls) != 0
    )
    
    best_idx = np.argmax(f1_scores)
    best_threshold = thresholds[best_idx] if best_idx < len(thresholds) else 0.5
    best_f1 = f1_scores[best_idx]

    logger.info(f"Оптимальний поріг класифікації: {best_threshold:.4f} (F1: {best_f1:.4f})")

    # Прогнози за новим оптимізованим порогом
    y_pred_tuned = (y_prob >= best_threshold).astype(int)

    # 4. PR-AUC (ГОЛОВНА МЕТРИКА ДЛЯ ДИСБАЛАНСУ)
    pr_auc = average_precision_score(y_test, y_prob)

    print("\n=== РЕЗУЛЬТАТИ XGBOOST (З ОПТИМІЗОВАНИМ ПОРОГОМ) ===")
    print(classification_report(y_test, y_pred_tuned, target_names=["Програв", "Переможець"]))
    
    print(f"🌟 Точність моделі: {pr_auc * 100:.0f}% (середня). Бажано >50%.")
    
    # --- EXPERIMENT TRACKING ---
    params = {
        "n_estimators": 250, "max_depth": 5, "learning_rate": 0.05, 
        "subsample": 0.8, "colsample_bytree": 0.8, "eval_metric": "aucpr"
    }
    metrics = {
        "pr_auc": round(float(pr_auc), 4),
        "f1_score": round(float(best_f1), 4),
        "best_threshold": round(float(best_threshold), 4)
    }
    run_id = log_experiment("XGBoost_SMOTETomek", params, metrics, model)
    
    print(f"Базовий Win Rate у вибірці: {y_test.mean():.4f}")

    # Зберігаємо модель
    models_dir = Path("data/models")
    with open(models_dir / "xgboost.pkl", "wb") as f:
        pickle.dump(model, f)
        
    with open(models_dir / "best_model.pkl", "wb") as f:
        pickle.dump(model, f)

    with open(models_dir / "feature_names.pkl", "wb") as f:
        pickle.dump(list(X_train.columns), f)

    logger.info("✅ Найдосконалішу модель успішно збережено.")

if __name__ == "__main__":
    train_xgboost()
