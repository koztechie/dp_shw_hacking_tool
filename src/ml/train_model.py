import sys
from pathlib import Path
import pickle
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, roc_auc_score

# Гарантуємо правильні шляхи імпорту
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.ml.prepare_dataset import prepare_dataset
from src.logger import logger

def train():
    logger.info("Початок підготовки даних...")
    X_train, X_test, y_train, y_test = prepare_dataset()

    # Створюємо модель із вагою класів, пропорційною дисбалансу
    model = RandomForestClassifier(
        n_estimators=200,
        class_weight="balanced",  # Корекція дисбалансу 3.7%
        max_depth=10,
        random_state=42,
        n_jobs=-1  # Використовуємо всі доступні ядра процесора AMD A4
    )

    logger.info("Тренування моделі Random Forest... (зачекайте кілька секунд)")
    model.fit(X_train, y_train)
    logger.info("Тренування завершено. Оцінюємо якість...")

    # Прогнозуємо класи та ймовірності
    y_pred = model.predict(X_test)
    y_prob = model.predict_proba(X_test)[:, 1]

    print("\n=== РЕЗУЛЬТАТИ МОДЕЛІ RANDOM FOREST ===")
    print(classification_report(y_test, y_pred, target_names=["Програв", "Переможець"]))
    
    auc_score = roc_auc_score(y_test, y_prob)
    print(f"ROC-AUC Score: {auc_score:.4f}")

    # Обчислюємо важливість ознак
    print("\n=== ВАЖЛИВІСТЬ ОЗНАК (Feature Importance) ===")
    feature_importance = pd.Series(
        model.feature_importances_,
        index=X_train.columns
    ).sort_values(ascending=False)
    
    for feature, val in feature_importance.items():
        print(f"  {feature:<25}: {val:.4f}")

    # Безпечно створюємо папку для моделей
    models_dir = Path("data/models")
    models_dir.mkdir(parents=True, exist_ok=True)

    # Зберігаємо модель
    model_path = models_dir / "random_forest.pkl"
    with open(model_path, "wb") as f:
        pickle.dump(model, f)
        
    # Створюємо копію як найкращу модель за замовчуванням
    best_model_path = models_path = models_dir / "best_model.pkl"
    with open(best_model_path, "wb") as f:
        pickle.dump(model, f)

    # Зберігаємо назви ознак для використання в майбутньому пайплайні
    feature_names_path = models_dir = Path("data/models/feature_names.pkl")
    with open(feature_names_path, "wb") as f:
        pickle.dump(list(X_train.columns), f)

    logger.info(f"Модель успішно збережено у {model_path}")
    return model

if __name__ == "__main__":
    train()
