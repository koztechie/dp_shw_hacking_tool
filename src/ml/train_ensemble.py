import hashlib
import pickle
import sys
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from imblearn.combine import SMOTETomek  # noqa: E402
from sklearn.ensemble import RandomForestClassifier  # noqa: E402
from sklearn.metrics import average_precision_score, classification_report, precision_recall_curve  # noqa: E402
from xgboost import XGBClassifier  # noqa: E402

from src.logger import logger  # noqa: E402
from src.ml.experiment_tracker import log_experiment  # noqa: E402
from src.ml.focal_loss import focal_loss_objective  # noqa: E402
from src.ml.predictor import safe_pickle_load  # noqa: E402
from src.ml.prepare_dataset import prepare_dataset  # noqa: E402


def train_ensemble():
    """
    АНТИКРИХКІСТЬ: Легкий ансамбль для 6GB RAM.
    - Видаляємо PyTorch модель (економія ~500MB)
    - Видаляємо Optuna (економія 60 тренувань)
    - Замість Stacking використовуємо усереднення ймовірностей (soft voting)
    """
    logger.info("Початок підготовки даних...")
    X_train, X_test, y_train, y_test = prepare_dataset()

    logger.info("🚀 Тренування легкого антикрихкого ансамблю (RF + XGBoost)...")

    rf = RandomForestClassifier(n_estimators=150, max_depth=10, random_state=42, n_jobs=1)
    xgb = XGBClassifier(
        n_estimators=200,
        learning_rate=0.05,
        max_depth=5,
        random_state=42,
        n_jobs=1,
        eval_metric="logloss",
        objective=focal_loss_objective,
    )

    logger.info("Генерація синтетичних даних (SMOTETomek)...")
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

    # Soft Voting Ensemble (усереднення ймовірностей)
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
    print(f"🌟 Ensemble PR-AUC: {pr_auc:.4f} (Оптимальний поріг: {best_threshold:.4f})")

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
