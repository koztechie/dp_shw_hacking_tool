import sys
from pathlib import Path
import duckdb
import pandas as pd
from sklearn.model_selection import train_test_split

# Гарантуємо правильні шляхи імпорту
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import DB_PATH
from src.logger import logger

def prepare_dataset():
    logger.info("Зчитування даних для тренувального датасету...")
    try:
        con = duckdb.connect(DB_PATH, read_only=True)
        df = con.execute("""
            SELECT
                f.uses_sponsor_tech, 
                f.tech_count, 
                f.has_social_angle,
                f.description_length, 
                f.has_github, 
                f.readme_length,
                f.commit_count_48h, 
                f.novelty_score,
                f.sponsor_challenge_match, -- ДОДАНО: Критична ознака
                p.likes, 
                p.team_size, 
                p.is_winner
            FROM features f
            JOIN projects p ON f.project_id = p.id
            WHERE p.description IS NOT NULL AND length(p.description) > 10
        """).fetchdf()
    except Exception as e:
        logger.error(f"Помилка зчитування БД: {e}")
        raise e
    finally:
        if 'con' in locals():
            con.close()

    if df.empty:
        raise ValueError("Датасет порожній! Перевірте базу даних.")

    # 1. Заповнення пропусків
    df = df.fillna(0)
    
    # 2. Конвертуємо всі булеві стовпці в int (0/1) для абсолютної стабільності sklearn
    bool_cols = [
        "uses_sponsor_tech", "has_social_angle", "has_github", 
        "sponsor_challenge_match", "is_winner"
    ]
    for col in bool_cols:
        if col in df.columns:
            df[col] = df[col].astype(int)

    X = df.drop("is_winner", axis=1)
    y = df["is_winner"]

    # 3. Антикрихкий захист: чи достатньо даних для стратифікації
    if len(y.unique()) < 2:
        raise ValueError(f"У датасеті знайдено лише один клас (is_winner={y.unique()[0]}). "
                         "Для тренування потрібні і переможці, і ті, хто програв.")

    # 4. Розбиття датасету з урахуванням пропорцій класів
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    print("=== ПІДГОТОВКА ДАТАСЕТУ (Етап 27) ===")
    print(f"Кількість ознак (Features): {X_train.shape[1]}")
    print(f"Train samples: {len(X_train)}")
    print(f"Test samples:  {len(X_test)}")
    print(f"Win rate train: {y_train.mean()*100:.2f}%")
    print(f"Win rate test:  {y_test.mean()*100:.2f}%")

    return X_train, X_test, y_train, y_test

if __name__ == "__main__":
    prepare_dataset()
