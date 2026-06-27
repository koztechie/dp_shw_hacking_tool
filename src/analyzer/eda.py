import sys
from pathlib import Path
import duckdb
import pandas as pd

# Гарантуємо правильні шляхи імпорту
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import DB_PATH

def run_eda():
    print("🔍 Запуск розвідувального аналізу даних (EDA)...")
    try:
        # Безпечне підключення без блокування БД
        con = duckdb.connect(DB_PATH, read_only=True)
        
        # Об'єднуємо таблиці
        df = con.execute("""
            SELECT p.is_winner, p.likes, p.team_size, f.* EXCLUDE(project_id)
            FROM projects p
            JOIN features f ON p.id = f.project_id
        """).fetchdf()
        
    except Exception as e:
        print(f"❌ Помилка підключення або зчитування БД: {e}")
        return
    finally:
        if 'con' in locals():
            con.close()

    if df.empty:
        print("⚠️ База даних порожня. Немає даних для аналізу.")
        return

    # АНТИКРИХКІСТЬ: Заповнюємо порожні значення перед конвертацією
    df = df.fillna(0)
    df["is_winner_int"] = df["is_winner"].astype(int)

    # Повний список ознак для аналізу
    features_to_analyze = [
        "tech_count", "has_social_angle", "uses_sponsor_tech", "sponsor_challenge_match",
        "description_length", "has_github", "readme_length", "commit_count_48h", 
        "novelty_score", "likes", "team_size"
    ]

    print("\n=== СЕРЕДНІ ЗНАЧЕННЯ: ПЕРЕМОЖЦІ (1) vs РЕШТА (0) ===")
    # Виводимо транспоновану таблицю для кращої читабельності у терміналі
    means = df.groupby("is_winner_int")[features_to_analyze].mean().round(3).T
    print(means)

    print("\n=== КОРЕЛЯЦІЯ З ПЕРЕМОГОЮ (Pearson) ===")
    # Рахуємо кореляцію фіч з цільовою змінною
    corr = df[features_to_analyze + ["is_winner_int"]].corr()["is_winner_int"]
    
    # Відкидаємо саму себе (is_winner_int) і сортуємо
    corr = corr.drop("is_winner_int").sort_values(ascending=False)
    
    for feature, value in corr.items():
        # Форматуємо вивід: позитивна кореляція зеленим/плюсом, негативна червоним/мінусом
        sign = "+" if value > 0 else ""
        print(f"{feature:<25}: {sign}{value:.4f}")

if __name__ == "__main__":
    run_eda()
