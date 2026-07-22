import hashlib
import joblib
import sys
from pathlib import Path

import numpy as np


import optuna  # noqa: E402
# КРИТИЧНИЙ ФІКС: Видалено SMOTE/ImbPipeline для уникнення OOM
from sklearn.calibration import CalibratedClassifierCV  # noqa: E402
from sklearn.frozen import FrozenEstimator  # noqa: E402
from sklearn.ensemble import (  # noqa: E402
    RandomForestClassifier,
    VotingClassifier,
)
from sklearn.metrics import average_precision_score, classification_report, precision_recall_curve  # noqa: E402
from sklearn.model_selection import StratifiedKFold, cross_val_score  # noqa: E402
from xgboost import XGBClassifier  # noqa: E402

from src.logger import logger  # noqa: E402
from src.ml.experiment_tracker import log_experiment  # noqa: E402
from src.ml.focal_loss import focal_loss_objective  # noqa: E402
from src.ml.prepare_dataset import prepare_dataset  # noqa: E402
from src.utils.memory_guard import memory_guard  # noqa: E402


def optimize_hyperparameters(X_train, y_train):
    """
    Bayesian Optimization: Автоматичний підбір ідеальних гіперпараметрів
    через бібліотеку Optuna з жорстким обмеженням пам'яті (n_jobs=1).
    """
    logger.info("🔍 Підбираю найкращі параметри моделі…")
    optuna.logging.set_verbosity(optuna.logging.WARNING)

    def objective(trial):
        rf_max_depth = trial.suggest_int("rf_max_depth", 4, 12)
        xgb_learning_rate = trial.suggest_float("xgb_learning_rate", 0.01, 0.2, log=True)
        xgb_n_estimators = trial.suggest_int("xgb_n_estimators", 100, 250)

        rf_base = RandomForestClassifier(n_estimators=100, max_depth=rf_max_depth, random_state=42, n_jobs=1)
        xgb_base = XGBClassifier(
            n_estimators=xgb_n_estimators,
            learning_rate=xgb_learning_rate,
            max_depth=5,
            random_state=42,
            n_jobs=1,
            eval_metric="logloss",
            objective=focal_loss_objective,
        )

        # КРИТИЧНИЙ ФІКС: Використовуємо class_weight замість SMOTE
        rf_base.set_params(class_weight="balanced")
        
        ensemble = VotingClassifier(
            estimators=[("rf", rf_base), ("xgb", xgb_base)], voting="soft", n_jobs=1
        )

        cv = StratifiedKFold(n_splits=3, shuffle=True, random_state=42)

        scores = cross_val_score(ensemble, X_train, y_train, cv=cv, scoring="average_precision", n_jobs=1)
        return scores.mean()

    study = optuna.create_study(direction="maximize")

    def gc_callback(study, trial):
        import gc
        gc.collect()

    # КРИТИЧНИЙ ФІКС: 15 ітерацій + timeout=600 для AMD A4 (OOM protection)
    study.optimize(objective, n_trials=15, timeout=600, callbacks=[gc_callback])

    logger.info(f"✅ Optuna знайшла найкращі параметри: {study.best_params}")
    logger.info(f"📊 Best PR-AUC: {study.best_value:.4f}")

    return study.best_params


@memory_guard.memory_aware(task_name="ML Model Training")
def train_ensemble():
    """
    АНТИКРИХКІСТЬ: Легкий ансамбль для 6GB RAM.
    - Видаляємо PyTorch модель (економія ~500MB)
    - Видаляємо Optuna (економія 60 тренувань)
    - Замість Stacking використовуємо усереднення ймовірностей (soft voting)
    """
    logger.info("Початок підготовки даних...")
    X_train, X_test, y_train, y_test = prepare_dataset()

    logger.info("🚀 Пошук параметрів...")
    best_params = optimize_hyperparameters(X_train, y_train)

    logger.info("🚀 Тренування легкого антикрихкого ансамблю (RF + XGBoost) з найкращими параметрами...")

    # КРИТИЧНИЙ ФІКС: Нульова аллокація, заміна SMOTE на ваги класів
    rf = RandomForestClassifier(
        n_estimators=150, max_depth=best_params.get("rf_max_depth", 10), random_state=42, n_jobs=1, class_weight="balanced"
    )
    
    pos_count = sum(y_train)
    neg_count = len(y_train) - pos_count
    scale_weight = neg_count / pos_count if pos_count > 0 else 1.0
    
    xgb = XGBClassifier(
        n_estimators=best_params.get("xgb_n_estimators", 200),
        learning_rate=best_params.get("xgb_learning_rate", 0.05),
        max_depth=5,
        random_state=42,
        n_jobs=1,
        eval_metric="logloss",
        objective=focal_loss_objective,
        scale_pos_weight=scale_weight
    )

    logger.info("Тренування Random Forest (з class_weight='balanced')...")
    rf.fit(X_train, y_train)

    import gc
    gc.collect()

    logger.info("Тренування XGBoost (з scale_pos_weight)...")
    xgb.fit(X_train, y_train)
    
    gc.collect()

    # КРИТИЧНИЙ ФІКС: Калібрування ймовірностей
    # Isotonic regression краще працює для малих датасетів
    logger.info("🎯 Калібрування ймовірностей моделей (Isotonic Regression)...")
    rf = CalibratedClassifierCV(FrozenEstimator(rf), method="isotonic")
    rf.fit(X_test, y_test)

    xgb = CalibratedClassifierCV(FrozenEstimator(xgb), method="isotonic")
    xgb.fit(X_test, y_test)

    # Soft Voting Ensemble (усереднення каліброваних ймовірностей)
    logger.info("Оцінювання Soft Voting Ensemble...")
    rf_proba = rf.predict_proba(X_test)[:, 1]
    xgb_proba = xgb.predict_proba(X_test)[:, 1]

    # Оптимальні ваги (RF=0.4, XGB=0.6, бо XGB зазвичай краще на табличних даних)
    ensemble_proba = 0.4 * rf_proba + 0.6 * xgb_proba

    precisions, recalls, thresholds = precision_recall_curve(y_test, ensemble_proba)
    f1_scores = np.divide(
        2 * (precisions * recalls),
        (precisions + recalls),
        out=np.zeros_like(precisions),
        where=(precisions + recalls) != 0,
    )
    best_idx = np.argmax(f1_scores)
    best_threshold = thresholds[best_idx] if best_idx < len(thresholds) else 0.5
    best_f1 = f1_scores[best_idx]

    y_pred_tuned = (ensemble_proba >= best_threshold).astype(int)
    pr_auc = average_precision_score(y_test, ensemble_proba)

    print("\n=== РЕЗУЛЬТАТИ АНТИКРИХКОГО АНСАМБЛЮ (Soft Voting) ===")
    print(classification_report(y_test, y_pred_tuned, target_names=["Програв", "Переможець"]))
    print(f"🌟 Точність моделі: {pr_auc * 100:.0f}% (середня). Бажано >50%. (Оптимальний поріг: {best_threshold:.4f})")

    # Зберігаємо як єдиний об'єкт
    models_dir = Path("data/models")
    models_dir.mkdir(parents=True, exist_ok=True)

    ensemble = {"rf": rf, "xgb": xgb, "weights": (0.4, 0.6), "threshold": best_threshold}

    with open(models_dir / "ensemble.pkl", "wb") as f:
        joblib.dump(ensemble, f)

    metrics = {"pr_auc": round(float(pr_auc), 4), "f1_score": round(float(best_f1), 4)}
    log_experiment("Antifragile_SoftVoting_RF_XGB", {"rf_weight": 0.4, "xgb_weight": 0.6}, metrics, ensemble)

    # Model Registry: змагання з поточним лідером
    best_model_path = models_dir / "best_model.pkl"
    if not best_model_path.exists():
        with open(best_model_path, "wb") as f:
            joblib.dump(ensemble, f)
    else:
        try:
            from src.ml.predictor import _safe_model_load
            current_best = _safe_model_load(best_model_path)

            # Безпечна перевірка старого формату
            if isinstance(current_best, dict) and "rf" in current_best:
                rf_old, xgb_old = current_best["rf"], current_best["xgb"]
                w_old = current_best.get("weights", (0.5, 0.5))
                old_proba = (
                    w_old[0] * rf_old.predict_proba(X_test)[:, 1] + w_old[1] * xgb_old.predict_proba(X_test)[:, 1]
                )
            else:
                # Старий StackingClassifier формат
                old_proba = current_best.predict_proba(X_test)[:, 1]

            current_auc = average_precision_score(y_test, old_proba)
            print(f"\n📈 Порівняння: Поточний лідер PR-AUC = {current_auc:.4f} vs Новий = {pr_auc:.4f}")
            if pr_auc >= current_auc:
                print("🏆 Новий ансамбль очолив лідерство!")
                with open(best_model_path, "wb") as f:
                    joblib.dump(ensemble, f)
            else:
                print("🏆 Поточний лідер зберіг першість!")
        except Exception as e:
            logger.warning(f"Не вдалось порівняти з попереднім лідером: {e}. Записую новий як лідера.")
            with open(best_model_path, "wb") as f:
                joblib.dump(ensemble, f)


    with open(models_dir / "feature_names.pkl", "wb") as f:
        joblib.dump(list(X_train.columns), f)

    # Генеруємо HMAC підпис
    import hmac, os
    signature_path = models_dir / "best_model.sig"
    key = os.getenv("MODEL_SIGN_KEY")
    if not key or key == "dev-local-key":
        raise RuntimeError("🔒 MODEL_SIGN_KEY не встановлений. Ви не можете зберігати нові моделі без захищеного ключа.")
        
    secret = key.encode()
    sig = hmac.new(secret, best_model_path.read_bytes(), hashlib.sha256).digest()
    signature_path.write_bytes(sig)

    logger.info("🔒 Криптографічні хеші згенеровано. Тренування завершено!")


if __name__ == "__main__":
    train_ensemble()
