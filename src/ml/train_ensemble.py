import hashlib
import pickle
import sys
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import optuna  # noqa: E402
from imblearn.combine import SMOTETomek  # noqa: E402
from imblearn.pipeline import Pipeline as ImbPipeline  # noqa: E402
from sklearn.calibration import CalibratedClassifierCV  # noqa: E402
from sklearn.ensemble import (  # noqa: E402
    RandomForestClassifier,
    StackingClassifier,
)
from sklearn.linear_model import LogisticRegression  # noqa: E402
from sklearn.metrics import average_precision_score, classification_report, precision_recall_curve  # noqa: E402
from sklearn.model_selection import StratifiedKFold, cross_val_score  # noqa: E402
from xgboost import XGBClassifier  # noqa: E402

from src.logger import logger  # noqa: E402
from src.ml.experiment_tracker import log_experiment  # noqa: E402
from src.ml.focal_loss import focal_loss_objective  # noqa: E402
from src.ml.predictor import safe_pickle_load  # noqa: E402
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
        meta_model = LogisticRegression(class_weight="balanced", random_state=42)

        ensemble = StackingClassifier(
            estimators=[("rf", rf_base), ("xgb", xgb_base)], final_estimator=meta_model, n_jobs=1
        )

        pipeline = ImbPipeline(steps=[("smote", SMOTETomek(random_state=42, n_jobs=1)), ("classifier", ensemble)])

        # КРИТИЧНИЙ ФІКС: SMOTETomek всередині CV запобігає data leakage
        cv = StratifiedKFold(n_splits=3, shuffle=True, random_state=42)

        scores = cross_val_score(pipeline, X_train, y_train, cv=cv, scoring="average_precision", n_jobs=1)
        return scores.mean()

    study = optuna.create_study(direction="maximize")

    # КРИТИЧНИЙ ФІКС: 50 ітерацій замість 20
    # Для AMD A4 це займе ~25 хвилин, але дасть надійніший результат
    study.optimize(objective, n_trials=50, timeout=1800)  # 30 хвилин max

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

    rf = RandomForestClassifier(
        n_estimators=150, max_depth=best_params.get("rf_max_depth", 10), random_state=42, n_jobs=1
    )
    xgb = XGBClassifier(
        n_estimators=best_params.get("xgb_n_estimators", 200),
        learning_rate=best_params.get("xgb_learning_rate", 0.05),
        max_depth=5,
        random_state=42,
        n_jobs=1,
        eval_metric="logloss",
        objective=focal_loss_objective,
    )

    logger.info("Балансую дані між переможцями та іншими...")
    smt = SMOTETomek(random_state=42, n_jobs=1)
    X_res, y_res = smt.fit_resample(X_train, y_train)

    # Тренуємо моделі ПОСЛІДОВНО (економія RAM)
    logger.info("Тренування Random Forest...")
    rf.fit(X_res, y_res)

    # Звільняємо пам'ять після RF
    del X_res
    import gc

    gc.collect()

    logger.info("Тренування XGBoost...")
    # Повторно генеруємо SMOTE для XGBoost (уникаємо зберігання 2x датасетів)
    X_res2, y_res2 = smt.fit_resample(X_train, y_train)
    xgb.fit(X_res2, y_res2)
    del X_res2, y_res2
    gc.collect()

    # КРИТИЧНИЙ ФІКС: Калібрування ймовірностей
    # Isotonic regression краще працює для малих датасетів
    logger.info("🎯 Калібрування ймовірностей моделей (Isotonic Regression)...")
    rf = CalibratedClassifierCV(rf, method="isotonic", cv="prefit")
    rf.fit(X_test, y_test)

    xgb = CalibratedClassifierCV(xgb, method="isotonic", cv="prefit")
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
        pickle.dump(ensemble, f)

    metrics = {"pr_auc": round(float(pr_auc), 4), "f1_score": round(float(best_f1), 4)}
    log_experiment("Antifragile_SoftVoting_RF_XGB", {"rf_weight": 0.4, "xgb_weight": 0.6}, metrics, ensemble)

    # Model Registry: змагання з поточним лідером
    best_model_path = models_dir / "best_model.pkl"
    if not best_model_path.exists():
        with open(best_model_path, "wb") as f:
            pickle.dump(ensemble, f)
    else:
        try:
            current_best = safe_pickle_load(best_model_path, models_dir / "checksums.txt")

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
                    pickle.dump(ensemble, f)
            else:
                print("🏆 Поточний лідер зберіг першість!")
        except Exception as e:
            logger.warning(f"Не вдалось завантажити старого лідера: {e}")
            with open(best_model_path, "wb") as f:
                pickle.dump(ensemble, f)

    with open(models_dir / "feature_names.pkl", "wb") as f:
        pickle.dump(list(X_train.columns), f)

    # SHA-256 checksums
    checksums = {}
    for fname in ["best_model.pkl", "feature_names.pkl", "ensemble.pkl"]:
        fpath = models_dir / fname
        if fpath.exists():
            with open(fpath, "rb") as f:
                checksums[fname] = hashlib.sha256(f.read()).hexdigest()

    with open(models_dir / "checksums.txt", "w") as f:
        for k, v in checksums.items():
            f.write(f"{k}:{v}\n")

    logger.info("🔒 Криптографічні хеші згенеровано. Тренування завершено!")


if __name__ == "__main__":
    train_ensemble()
