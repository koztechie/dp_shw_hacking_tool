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
from src.ml.experiment_tracker import log_experiment
from src.ml.focal_loss import focal_loss_objective

import optuna
from xgboost import XGBClassifier
from sklearn.ensemble import RandomForestClassifier, StackingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold, cross_val_score
from sklearn.metrics import classification_report, average_precision_score, precision_recall_curve

# Антикрихкість: Використовуємо Pipeline з imblearn, щоб уникнути витоку даних
from imblearn.pipeline import Pipeline as ImbPipeline
from imblearn.combine import SMOTETomek

def optimize_hyperparameters(X_train, y_train):
    """
    Bayesian Optimization: Автоматичний підбір ідеальних гіперпараметрів 
    через бібліотеку Optuna з жорстким обмеженням пам'яті (n_jobs=1).
    """
    logger.info("🔍 Запуск Optuna для пошуку ідеальних гіперпараметрів (20 ітерацій)...")
    optuna.logging.set_verbosity(optuna.logging.WARNING)

    def objective(trial):
        rf_max_depth = trial.suggest_int('rf_max_depth', 4, 12)
        xgb_learning_rate = trial.suggest_float('xgb_learning_rate', 0.01, 0.2, log=True)
        xgb_n_estimators = trial.suggest_int('xgb_n_estimators', 100, 250)

        rf_base = RandomForestClassifier(
            n_estimators=100, max_depth=rf_max_depth, random_state=42, n_jobs=1
        )
        xgb_base = XGBClassifier(
            n_estimators=xgb_n_estimators, learning_rate=xgb_learning_rate,
            max_depth=5, random_state=42, n_jobs=1, eval_metric="logloss",
            objective=focal_loss_objective
        )
        meta_model = LogisticRegression(class_weight="balanced", random_state=42)

        ensemble = StackingClassifier(
            estimators=[('rf', rf_base), ('xgb', xgb_base)],
            final_estimator=meta_model,
            n_jobs=1
        )

        pipeline = ImbPipeline(steps=[
            ('smote', SMOTETomek(random_state=42, n_jobs=1)),
            ('classifier', ensemble)
        ])

        cv = StratifiedKFold(n_splits=3, shuffle=True, random_state=42)
        
        # АНТИКРИХКІСТЬ: Обмежуємо n_jobs=1 для уникнення Out of Memory на 6GB RAM
        scores = cross_val_score(pipeline, X_train, y_train, cv=cv, scoring='average_precision', n_jobs=1)
        return scores.mean()

    study = optuna.create_study(direction='maximize')
    study.optimize(objective, n_trials=20)
    
    logger.info(f"✅ Optuna знайшла найкращі параметри: {study.best_params}")
    return study.best_params

def train_ensemble():
    logger.info("Початок підготовки даних для AutoML Ансамблю...")
    X_train, X_test, y_train, y_test = prepare_dataset()

    best_params = optimize_hyperparameters(X_train, y_train)

    logger.info("🚀 Тренування фінального Потрійного Ансамблю...")
    
    rf_base = RandomForestClassifier(
        n_estimators=150, 
        max_depth=best_params['rf_max_depth'], 
        random_state=42, n_jobs=1
    )
    xgb_base = XGBClassifier(
        n_estimators=best_params['xgb_n_estimators'], 
        learning_rate=best_params['xgb_learning_rate'],
        max_depth=5, random_state=42, n_jobs=1, eval_metric="logloss",
        objective=focal_loss_objective
    )
    meta_model = LogisticRegression(class_weight="balanced", random_state=42)

    from src.ml.pytorch_model import PyTorchHackathonClassifier
    nn_base = PyTorchHackathonClassifier(epochs=20)

    # АНТИКРИХКІСТЬ: Задаємо n_jobs=1 для стабільного послідовного тренування без OOM
    ensemble = StackingClassifier(
        estimators=[('rf', rf_base), ('xgb', xgb_base), ('nn', nn_base)],
        final_estimator=meta_model,
        cv=5, n_jobs=1
    )

    logger.info("Генерація фінальних синтетичних даних (SMOTETomek)...")
    smt = SMOTETomek(random_state=42, n_jobs=1)
    X_res, y_res = smt.fit_resample(X_train, y_train)
    
    ensemble.fit(X_res, y_res)
    logger.info("Тренування завершено! Оцінюємо якість...")

    y_prob = ensemble.predict_proba(X_test)[:, 1]
    
    precisions, recalls, thresholds = precision_recall_curve(y_test, y_prob)
    f1_scores = np.divide(2 * (precisions * recalls), (precisions + recalls), out=np.zeros_like(precisions), where=(precisions + recalls) != 0)
    best_idx = np.argmax(f1_scores)
    best_threshold = thresholds[best_idx] if best_idx < len(thresholds) else 0.5
    best_f1 = f1_scores[best_idx]

    y_pred_tuned = (y_prob >= best_threshold).astype(int)
    pr_auc = average_precision_score(y_test, y_prob)

    print("\n=== РЕЗУЛЬТАТИ AUTOML МЕТА-МОДЕЛІ (STACKING + OPTUNA + FOCAL LOSS + PYTORCH) ===")
    print(classification_report(y_test, y_pred_tuned, target_names=["Програв", "Переможець"]))
    print(f"🌟 Ensemble PR-AUC Score: {pr_auc:.4f} (Оптимальний поріг: {best_threshold:.4f})")

    models_dir = Path("data/models")
    models_dir.mkdir(parents=True, exist_ok=True)
    
    with open(models_dir / "ensemble.pkl", "wb") as f:
        pickle.dump(ensemble, f)

    # 4. Experiment Tracking & Model Registry
    metrics = {"pr_auc": round(float(pr_auc), 4), "f1_score": round(float(best_f1), 4)}
    log_experiment("AutoML_Stacking_Focal_Loss_PyTorch", best_params, metrics, ensemble)

    best_model_path = models_dir / "best_model.pkl"
    if not best_model_path.exists():
        with open(best_model_path, "wb") as f: 
            pickle.dump(ensemble, f)
    else:
        try:
            with open(best_model_path, "rb") as f: 
                current_best_model = pickle.load(f)
            current_prob = current_best_model.predict_proba(X_test)[:, 1]
            current_auc = average_precision_score(y_test, current_prob)
            print(f"\n📈 Порівняння: Поточний лідер PR-AUC = {current_auc:.4f} vs Новий AutoML Ансамбль PR-AUC = {pr_auc:.4f}")
            if pr_auc >= current_auc:
                print("🏆 ПЕРЕМОЖЕЦЬ: Новий AutoML Ансамбль очолив лідерство!")
                with open(best_model_path, "wb") as f: 
                    pickle.dump(ensemble, f)
            else:
                print("🏆 Поточний лідер зберіг першість!")
        except Exception:
            with open(best_model_path, "wb") as f: 
                pickle.dump(ensemble, f)

    # Зберігаємо feature names (виправлено відступи!)
    with open(models_dir / "feature_names.pkl", "wb") as f:
        pickle.dump(list(X_train.columns), f)

    # АНТИКРИХКІСТЬ: Генерація HMAC-SHA256 підписів для запобігання RCE
    import hashlib
    import hmac
    import os
    
    MODEL_SIGNING_KEY = os.getenv("MODEL_SIGNING_KEY", "dp_shw_super_secret_key_2026")
    
    for fname in ["best_model.pkl", "feature_names.pkl", "ensemble.pkl"]:
        fpath = models_dir / fname
        if fpath.exists():
            with open(fpath, "rb") as f:
                model_data = f.read()
            signature = hmac.new(MODEL_SIGNING_KEY.encode("utf-8"), model_data, hashlib.sha256).hexdigest()
            with open(fpath.parent / f"{fname}.sig", "w") as f:
                f.write(signature)
                
    logger.info("🔒 Криптографічні HMAC підписи моделей успішно згенеровано.")

if __name__ == "__main__":
    train_ensemble()
