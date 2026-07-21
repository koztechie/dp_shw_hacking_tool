import sys
from pathlib import Path

import numpy as np


from src.ml.predictor import load_model  # noqa: E402
from src.ml.prepare_dataset import prepare_dataset  # noqa: E402


def calculate_global_ate():
    print("=== СТАТИСТИЧНИЙ АНАЛІЗ: Average Treatment Effect (ATE) ===")

    # Отримуємо дані
    X_train, X_test, y_train, y_test = prepare_dataset()

    try:
        model, _ = load_model()
    except Exception as e:
        print(f"❌ Модель не знайдена або скомпрометована: {e}")
        return

    treatments = [
        ("has_video_demo", "Наявність відео-демо"),
        ("uses_sponsor_tech", "Використання технологій спонсора"),
        ("has_github", "Відкритий репозиторій GitHub"),
        ("has_social_angle", "Соціальна значущість (Social Good)"),
        ("sponsor_challenge_match", "Пряме попадання в номінацію"),
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
            print(f"📈 {name:<35}: +{ate * 100:.2f}% до шансів перемоги")
        else:
            print(f"🔻 {name:<35}: {ate * 100:.2f}% (негативний вплив)")


if __name__ == "__main__":
    calculate_global_ate()
