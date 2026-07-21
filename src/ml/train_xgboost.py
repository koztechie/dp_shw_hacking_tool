import sys
from pathlib import Path
import joblib
import pandas as pd
import numpy as np
from collections import Counter
import json
from datetime import datetime

# Гарантуємо правильні шляхи
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

from src.ml.prepare_dataset import prepare_dataset_full
from src.logger import logger
from src.ml.experiment_tracker import log_experiment
from config.settings import SETTINGS

from xgboost import XGBClassifier
from sklearn.metrics import classification_report, average_precision_score, precision_recall_curve
from sklearn.model_selection import StratifiedKFold, cross_val_score
from imblearn.combine import SMOTETomek
from imblearn.pipeline import Pipeline as ImbPipeline

def train_xgboost():
    logger.info("Початок підготовки даних для XGBoost (Full Dataset для CV)...")
    X, y = prepare_dataset_full()

    logger.info(f"Оригінальний баланс класів (Full): {Counter(y)}")

    # 1. МОДЕЛЬ ТА SMOTE
    smt = SMOTETomek(random_state=42, n_jobs=1)
    xgb_model = XGBClassifier(
        n_estimators=100,  # Зменшено для AMD A4
        max_depth=5,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        n_jobs=SETTINGS.cpu_cores,
        eval_metric="aucpr"
    )

    pipeline = ImbPipeline([('smote', smt), ('xgb', xgb_model)])

    logger.info("Проведення крос-валідації (Stratified 5-Fold) з SMOTE... Це може зайняти ~30-60 секунд.")
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    cv_scores = cross_val_score(pipeline, X, y, cv=skf, scoring='average_precision')
    
    logger.info(f"CV PR-AUC: {cv_scores.mean():.4f} (+/- {cv_scores.std()*2:.4f})")

    # 2. ТРЕНУВАННЯ ФІНАЛЬНОЇ МОДЕЛІ XGBOOST
    logger.info("Тренування фінальної моделі XGBoost на всіх даних...")
    try:
        X_res, y_res = smt.fit_resample(X, y)
        logger.info(f"Новий баланс класів після SMOTETomek: {Counter(y_res)}")
    except Exception as e:
        logger.error(f"SMOTETomek не вдався: {e}. Використовуємо оригінальні дані.")
        X_res, y_res = X, y

    xgb_model.fit(X_res, y_res)
    logger.info("Тренування завершено.")

    # 3. THRESHOLD TUNING ТА ОЦІНКА НА TRAIN (ТАК ЯК TEST БІЛЬШЕ НЕМАЄ)
    # Зверніть увагу: ми використовуємо прогнози на X_res лише для знаходження найкращого порогу (для production)
    y_prob = xgb_model.predict_proba(X_res)[:, 1]
    precisions, recalls, thresholds = precision_recall_curve(y_res, y_prob)
    
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

    pr_auc = cv_scores.mean()  # Використовуємо CV PR-AUC як головну оцінку
    print(f"🌟 Очікувана точність моделі (CV PR-AUC): {pr_auc * 100:.0f}% (середня). Бажано >50%.")
    
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
    run_id = log_experiment("XGBoost_SMOTETomek", params, metrics, xgb_model)
    
    print(f"Базовий Win Rate у вибірці: {y.mean():.4f}")

    # Зберігаємо модель
    models_dir = PROJECT_ROOT / "data" / "models"
    models_dir.mkdir(parents=True, exist_ok=True)
    model_path = models_dir / "xgboost.pkl"
    # Зберігаємо історію
    metrics_file = models_dir / "metrics_history.jsonl"
    
    # Визначаємо Champion
    champion_pr_auc = 0.0
    if metrics_file.exists():
        try:
            with open(metrics_file, "r", encoding="utf-8") as f:
                lines = f.readlines()
                if lines:
                    last_metric = json.loads(lines[-1])
                    champion_pr_auc = last_metric.get("cv_pr_auc", 0.0)
        except Exception as e:
            logger.error(f"Не вдалося зчитати історію метрик: {e}")

    # Запис нових метрик у JSONL
    history_metrics = {
        "timestamp": datetime.now().isoformat(),
        "model": "xgboost_smotetomek",
        "cv_pr_auc": float(pr_auc),
        "f1_score": float(best_f1),
        "data_samples": int(len(y))
    }
    with open(metrics_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(history_metrics) + "\n")

    # A/B Testing: Champion vs Challenger
    MIN_IMPROVEMENT = 0.02
    best_model_path = models_dir / "best_model.pkl"
    signature_path = models_dir / "best_model.sig"
    
    if not best_model_path.exists() or float(pr_auc) > champion_pr_auc + MIN_IMPROVEMENT:
        logger.info(f"🏆 CHALLENGER ПЕРЕМІГ! Новий PR-AUC {pr_auc:.4f} б'є старий {champion_pr_auc:.4f}. Оновлюємо best_model...")
        joblib.dump(xgb_model, best_model_path)
        
        # Генеруємо HMAC підпис
        import hmac, hashlib, os
        secret = os.getenv("MODEL_SIGN_KEY", "dev-local-key").encode()
        sig = hmac.new(secret, best_model_path.read_bytes(), hashlib.sha256).digest()
        signature_path.write_bytes(sig)
        
        feature_names_path = models_dir / "feature_names.pkl"
        joblib.dump(list(X.columns), feature_names_path)
        
        logger.info("✅ Найдосконалішу модель успішно збережено як Champion.")
    else:
        logger.info(f"🛡️ CHAMPION ЗАХИСТИВ ТИТУЛ! Новий PR-AUC {pr_auc:.4f} не набагато кращий за {champion_pr_auc:.4f}.")
        logger.info("Нову модель збережено лише як xgboost.pkl. Продакшен продовжує використовувати стару модель.")

if __name__ == "__main__":
    train_xgboost()
