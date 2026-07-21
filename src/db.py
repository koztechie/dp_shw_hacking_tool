import sys
import time
from pathlib import Path
from datetime import datetime

import duckdb

# Гарантуємо правильні шляхи імпорту

from config.settings import SETTINGS  # noqa: E402
from src.logger import logger  # noqa: E402


def get_connection(retries: int = 5, delay: float = 1.0):
    """
    Повертає стандартне з'єднання з DuckDB у режимі читання/запису.
    АНТИКРИХКІСТЬ: Захист від паралельних блокувань іншими процесами (Retry Mechanism).
    """
    Path(SETTINGS.db_path).parent.mkdir(parents=True, exist_ok=True)
    temp_dir = Path("./data/tmp")
    temp_dir.mkdir(parents=True, exist_ok=True)
    
    for attempt in range(1, retries + 1):
        try:
            # Намагаємося відкрити з'єднання
            con = duckdb.connect(SETTINGS.db_path)
            # Вмикаємо стійкість до відмов та обмежуємо ресурси (під AMD A4)
            con.execute("PRAGMA enable_progress_bar=false")
            con.execute("PRAGMA memory_limit='1GB'")  # Обмеження для 6GB RAM системи
            con.execute("PRAGMA threads=2")  # AMD A4 зазвичай 2 ядра, не перевантажуємо
            con.execute(f"PRAGMA temp_directory='{temp_dir}'")  # Зберігаємо spill-over дані на диску локально
            return con
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

def backup_db():
    """Створює timestamped backup."""
    backup_dir = Path(SETTINGS.db_path).parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    # Export requires an empty directory or specific file, DuckDB EXPORT DATABASE creates a folder
    # with the schema and parquet files inside.
    backup_path = backup_dir / f"dp_shw_backup_{timestamp}"
    backup_path.mkdir(exist_ok=True)
    con = get_connection()
    try:
        con.execute(f"EXPORT DATABASE '{backup_path}' (FORMAT PARQUET)")
        logger.info(f"Бекап успішно створено у директорії: {backup_path}")
    except Exception as e:
        logger.error(f"Помилка створення бекапу: {e}")
    finally:
        con.close()


MIGRATIONS = [
    # v0: Initial schema
    """
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
    );
    CREATE TABLE IF NOT EXISTS projects (
        id VARCHAR PRIMARY KEY,
        hackathon_id VARCHAR NOT NULL,
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
        scraped_at TIMESTAMP DEFAULT current_timestamp,
        FOREIGN KEY (hackathon_id) REFERENCES hackathons(id) ON DELETE CASCADE
    );
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
        organizer_reputation INTEGER DEFAULT 0,
        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
    );
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
    );
    CREATE TABLE IF NOT EXISTS feedback (
        prediction_id VARCHAR,
        won BOOLEAN,
        actual_place INTEGER,
        created_at TIMESTAMP DEFAULT current_timestamp
    );
    CREATE TABLE IF NOT EXISTS experiments (
        run_id VARCHAR PRIMARY KEY,
        timestamp TIMESTAMP DEFAULT current_timestamp,
        model_name VARCHAR,
        hyperparameters VARCHAR,
        metrics VARCHAR,
        model_path VARCHAR
    );
    CREATE SEQUENCE IF NOT EXISTS audit_log_id_seq START 1;
    CREATE TABLE IF NOT EXISTS audit_log (
        id INTEGER PRIMARY KEY DEFAULT nextval('audit_log_id_seq'),
        timestamp TIMESTAMP DEFAULT current_timestamp,
        user_ip VARCHAR,
        endpoint VARCHAR,
        method VARCHAR,
        status_code INTEGER,
        details VARCHAR
    );
    """,
    # v1: Add indexes and has_video (as suggested)
    """
    ALTER TABLE features ADD COLUMN IF NOT EXISTS has_video BOOLEAN DEFAULT FALSE;
    CREATE INDEX IF NOT EXISTS idx_projects_hackathon_id ON projects(hackathon_id);
    CREATE INDEX IF NOT EXISTS idx_projects_is_winner ON projects(is_winner);
    CREATE INDEX IF NOT EXISTS idx_projects_scraped_at ON projects(scraped_at);
    CREATE INDEX IF NOT EXISTS idx_features_project_id ON features(project_id);
    CREATE INDEX IF NOT EXISTS idx_predictions_hackathon_url ON predictions(hackathon_url);
    CREATE INDEX IF NOT EXISTS idx_feedback_prediction_id ON feedback(prediction_id);
    """
]

def init_db():
    """
    Ініціалізує всі таблиці бази даних DuckDB та застосовує міграції.
    """
    from src.utils import backup_database

    backup_database(SETTINGS.db_path)

    con = get_connection()
    try:
        con.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY)")
        
        # Отримуємо поточну версію (якщо таблиця порожня, то -1, щоб застосувати v0)
        current_res = con.execute("SELECT MAX(version) FROM schema_version").fetchone()[0]
        current = current_res if current_res is not None else -1
        
        for i, migration in enumerate(MIGRATIONS):
            if i > current:
                logger.info(f"Застосування міграції v{i}...")
                con.execute(migration)
                con.execute("INSERT INTO schema_version VALUES (?)", [i])
                con.commit()
                
        # Міграція для існуючої таблиці, що була створена без DEFAULT
        try:
            con.execute("ALTER TABLE audit_log ALTER id SET DEFAULT nextval('audit_log_id_seq')")
        except Exception:
            pass

        logger.info("База даних DuckDB успішно ініціалізована та перевірена.")
    finally:
        con.close()


if __name__ == "__main__":
    init_db()
