import sys
import time
from pathlib import Path

import duckdb

# Гарантуємо правильні шляхи імпорту
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import DB_PATH  # noqa: E402
from src.logger import logger  # noqa: E402


def get_connection(retries: int = 5, delay: float = 1.0):
    """
    Повертає стандартне з'єднання з DuckDB у режимі читання/запису.
    АНТИКРИХКІСТЬ: Захист від паралельних блокувань іншими процесами (Retry Mechanism).
    """
    for attempt in range(1, retries + 1):
        try:
            # Намагаємося відкрити з'єднання
            return duckdb.connect(DB_PATH)
        except Exception as e:
            if attempt == retries:
                logger.error(f"❌ Фатальна помилка DuckDB: Не вдалося підключитися після {retries} спроб: {e}")
                raise e
            logger.warning(
                f"⚠️ База даних заблокована іншим процесом. Спроба {attempt}/{retries}. Очікування {delay}с..."
            )
            time.sleep(delay)
            # Експоненційне збільшення часу очікування
            delay *= 1.5


def init_db():
    """
    Ініціалізує всі таблиці бази даних DuckDB.
    Повністю сумісний з розширеним набором ознак (23 фічі) та MLOps фідбеком.
    """
    from src.utils import backup_database

    backup_database(DB_PATH)

    con = get_connection()
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
                themes VARCHAR,
                sponsors VARCHAR,
                judging_criteria VARCHAR,
                judges_info VARCHAR,
                scraped_at TIMESTAMP DEFAULT current_timestamp
            )
        """)

        # 2. Таблиця проектів
        con.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                id VARCHAR PRIMARY KEY,
                hackathon_id VARCHAR,
                title VARCHAR,
                description VARCHAR,
                tech_tags VARCHAR,
                team_size INTEGER,
                likes INTEGER,
                github_url VARCHAR,
                demo_url VARCHAR,
                is_winner BOOLEAN DEFAULT FALSE,
                prize_track VARCHAR,
                win_score FLOAT,
                readme_length INTEGER,
                commit_count_48h INTEGER,
                project_url VARCHAR,
                scraped_at TIMESTAMP DEFAULT current_timestamp
            )
        """)

        # 3. Таблиця ознак (Features)
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
                idea_1_description VARCHAR,
                idea_1_score FLOAT,
                idea_2_title VARCHAR,
                idea_2_description VARCHAR,
                idea_2_score FLOAT,
                idea_3_title VARCHAR,
                idea_3_description VARCHAR,
                idea_3_score FLOAT,
                selected_idea INTEGER,
                techspec VARCHAR
            )
        """)

        # 5. Таблиця зворотного зв'язку
        con.execute("""
            CREATE TABLE IF NOT EXISTS feedback (
                prediction_id VARCHAR,
                won BOOLEAN,
                actual_place INTEGER,
                created_at TIMESTAMP DEFAULT current_timestamp
            )
        """)

        # 6. Таблиця відстеження експериментів
        con.execute("""
            CREATE TABLE IF NOT EXISTS experiments (
                run_id VARCHAR PRIMARY KEY,
                timestamp TIMESTAMP DEFAULT current_timestamp,
                model_name VARCHAR,
                hyperparameters VARCHAR,
                metrics VARCHAR,
                model_path VARCHAR
            )
        """)
        # 7. Таблиця аудиту
        con.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY,
                timestamp TIMESTAMP DEFAULT current_timestamp,
                user_ip VARCHAR,
                endpoint VARCHAR,
                method VARCHAR,
                status_code INTEGER,
                details VARCHAR
            )
        """)

        # АНТИКРИХКІСТЬ: Індекси для швидких JOIN та WHERE запитів
        con.execute("CREATE INDEX IF NOT EXISTS idx_projects_hackathon_id ON projects(hackathon_id)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_projects_is_winner ON projects(is_winner)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_projects_scraped_at ON projects(scraped_at)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_features_project_id ON features(project_id)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_predictions_hackathon_url ON predictions(hackathon_url)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_feedback_prediction_id ON feedback(prediction_id)")

        logger.info("База даних DuckDB успішно ініціалізовано з індексами.")
    finally:
        con.close()


if __name__ == "__main__":
    init_db()
