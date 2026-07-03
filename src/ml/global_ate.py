import sys
from pathlib import Path
import pickle
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.ml.prepare_dataset import prepare_dataset

def calculate_global_ate():
    print("=== СТАТИСТИЧНИЙ АНАЛІЗ: Average Treatment Effect (ATE) ===")
    
    # Отримуємо дані
    X_train, X_test, y_train, y_test = prepare_dataset()

    model_path = PROJECT_ROOT / "data" / "models" / "best_model.pkl"
    if not model_path.exists():
        print("❌ Модель не знайдена. Спочатку натренуйте ансамбль.")
        return

    with open(model_path, "rb") as f:
        model = pickle.load(f)

    treatments = [
        ("has_video_demo", "Наявність відео-демо"),
        ("uses_sponsor_tech", "Використання технологій спонсора"),
        ("has_github", "Відкритий репозиторій GitHub"),
        ("has_social_angle", "Соціальна значущість (Social Good)"),
        ("sponsor_challenge_match", "Пряме попадання в номінацію")
    ]

    print("\nГлобальний вплив факторів на всі проекти (Causal Effect):")
    for feature, name in treatments:
        if feature not in X_test.columns:
            continue

        # Симулюємо паралельний всесвіт 1: Усі команди використали цю технологію/підхід
        X_treated = X_test.copy()
        X_treated[feature] = 1
        prob_treated = model.predict_proba(X_treated)[:, 1]

        # Симулюємо паралельний всесвіт 0: Жодна команда не використала
        X_control = X_test.copy()
        X_control[feature] = 0
        prob_control = model.predict_proba(X_control)[:, 1]

        # ATE = E[Y | do(T=1)] - E[Y | do(T=0)]
        ate = np.mean(prob_treated - prob_control)

        # Форматування виводу
        if ate > 0:
            print(f"📈 {name:<35}: +{ate*100:.2f}% до шансів перемоги")
        else:
            print(f"🔻 {name:<35}: {ate*100:.2f}% (негативний вплив)")

if __name__ == "__main__":
    calculate_global_ate()
