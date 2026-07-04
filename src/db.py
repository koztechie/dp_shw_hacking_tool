import sys
from pathlib import Path
import duckdb

# Гарантуємо правильні шляхи імпорту
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import DB_PATH

def get_connection():
    """
    Повертає стандартне з'єднання з DuckDB у режимі читання/запису.
    КРИТИЧНО ДЛЯ АНТИКРИХКОСТІ: Ця функція має бути імпортована іншими модулями.
    """
    return duckdb.connect(DB_PATH)

def init_db():
    """
    Ініціалізує всі таблиці бази даних DuckDB.
    Повністю сумісний з розширеним набором ознак (23 фічі) та MLOps фідбеком.
    """
    con = duckdb.connect(DB_PATH)
    try:
        # 1. Таблиця хакатонів (включаючи Judges Info)
        con.execute("""
            CREATE TABLE IF NOT EXISTS hackathons (
                id VARCHAR PRIMARY KEY,
                url VARCHAR,
                title VARCHAR,
                organizer VARCHAR,
                start_date VARCHAR,
                end_date VARCHAR,
                prize_total VARCHAR,
                participant_count INTEGER,
                themes VARCHAR,          -- Зберігається як JSON-рядок
                sponsors VARCHAR,        -- Зберігається як JSON-рядок
                judging_criteria VARCHAR,
                judges_info VARCHAR,     -- Інформація про суддів
                scraped_at TIMESTAMP DEFAULT current_timestamp
            )
        """)

        # 2. Таблиця проектів (включаючи URL проекту)
        con.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                id VARCHAR PRIMARY KEY,
                hackathon_id VARCHAR,
                title VARCHAR,
                description VARCHAR,
                tech_tags VARCHAR,       -- Зберігається як JSON-рядок
                team_size INTEGER,
                likes INTEGER,
                github_url VARCHAR,
                demo_url VARCHAR,
                is_winner BOOLEAN DEFAULT FALSE,
                prize_track VARCHAR,
                win_score FLOAT,
                readme_length INTEGER,
                commit_count_48h INTEGER,
                project_url VARCHAR,     -- Посилання на проект
                scraped_at TIMESTAMP DEFAULT current_timestamp
            )
        """)

        # 3. Таблиця ознак (Features) - ПОВНИЙ 23-КОЛОНКОВИЙ НАБІР ДЛЯ ML
        con.execute("""
            CREATE TABLE IF NOT EXISTS features (
                project_id VARCHAR PRIMARY KEY,
                uses_sponsor_tech BOOLEAN,
                tech_count INTEGER,
                has_social_angle BOOLEAN,
                description_length INTEGER,
                novelty_score FLOAT,
                has_github BOOLEAN,
                readme_length INTEGER,
                commit_count_48h INTEGER,
                final_score FLOAT,
                sponsor_challenge_match BOOLEAN,
                has_video_demo BOOLEAN,
                competition_density FLOAT,
                prize_numeric INTEGER,
                semantic_pca_1 FLOAT,
                semantic_pca_2 FLOAT,
                semantic_pca_3 FLOAT,
                github_stars INTEGER DEFAULT 0,
                repo_size INTEGER DEFAULT 0,
                repo_issues INTEGER DEFAULT 0,
                days_before_deadline INTEGER DEFAULT 0,
                prize_per_team FLOAT DEFAULT 0.0,
                organizer_reputation INTEGER DEFAULT 0
            )
        """)

        # 4. Таблиця прогнозів ШІ
        con.execute("""
            CREATE TABLE IF NOT EXISTS predictions (
                id VARCHAR PRIMARY KEY,
                hackathon_url VARCHAR,
                generated_at TIMESTAMP DEFAULT current_timestamp,
                idea_1_title VARCHAR,
                idea_1_description VARCHAR,  -- Зберігається як JSON
                idea_1_score FLOAT,
                idea_2_title VARCHAR,
                idea_2_description VARCHAR,  -- Зберігається як JSON
                idea_2_score FLOAT,
                idea_3_title VARCHAR,
                idea_3_description VARCHAR,  -- Зберігається як JSON
                idea_3_score FLOAT,
                selected_idea INTEGER,
                techspec VARCHAR             -- Зберігається як JSON
            )
        """)

        # 5. Таблиця зворотного зв'язку (MLOps Feedback Loop)
        con.execute("""
            CREATE TABLE IF NOT EXISTS feedback (
                prediction_id VARCHAR,
                won BOOLEAN,
                actual_place INTEGER,
                created_at TIMESTAMP DEFAULT current_timestamp
            )
        """)

        print("Базу даних DuckDB успішно ініціалізовано.")
    finally:
        con.close()

if __name__ == "__main__":
    init_db()
