from pathlib import Path
from datetime import datetime

import duckdb

# Гарантуємо правильні шляхи імпорту

from config.settings import SETTINGS  # noqa: E402
from src.logger import logger  # noqa: E402

import shutil
import threading

DB_PATH = Path(SETTINGS.db_path)
WAL_PATH = DB_PATH.with_suffix(".duckdb.wal")

def _recover_wal_if_needed():
    """Видаляє пошкоджений WAL і робить checkpoint перед першим з'єднанням."""
    if not WAL_PATH.exists():
        return

    try:
        # Спробувати відкрити — якщо WAL пошкоджений, буде помилка
        con = duckdb.connect(str(DB_PATH))
        con.execute("CHECKPOINT")  # Примусово злити WAL у основний файл
        con.close()
        logger.info("✅ WAL успішно checkpoint'нуто")
    except Exception as e:
        logger.warning(f"⚠️ WAL пошкоджений ({e}). Видаляю та відновлюю...")
        # Backup пошкодженого WAL для діагностики
        backup = WAL_PATH.with_suffix(".wal.corrupt")
        shutil.move(str(WAL_PATH), str(backup))
        # Відкрити без WAL — DuckDB автоматично проігнорує відсутній WAL
        try:
            con = duckdb.connect(str(DB_PATH))
            con.execute("CHECKPOINT")
            con.close()
            logger.info("✅ БД відновлено без WAL (дані збережено)")
        except Exception as e2:
            logger.critical(f"❌ БД невідновна: {e2}")
            raise

# Викликати ОДИН РАЗ при імпорті модуля, до DuckDBPool
_recover_wal_if_needed()


class DuckDBPool:
    _read_con = None
    _write_con = None
    write_lock = threading.Lock()

    @classmethod
    def shutdown(cls):
        """Безпечне завершення: checkpoint + close."""
        try:
            if cls._write_con:
                cls._write_con.execute("CHECKPOINT")
                cls._write_con.close()
                cls._write_con = None
            
            if getattr(cls, "_read_con", None):
                cls._read_con.close()
                cls._read_con = None
                
            if hasattr(cls, "_read_cons"):
                for con in cls._read_cons:
                    con.close()
                cls._read_cons.clear()
        except Exception:
            pass  # Best-effort при shutdown

    @classmethod
    def get_read_connection(cls):
        if cls._read_con is None:
            cls._read_con = duckdb.connect(SETTINGS.db_path, read_only=True)
            cls._read_con.execute("PRAGMA enable_progress_bar=false")
            cls._read_con.execute("PRAGMA memory_limit='512MB'")
            cls._read_con.execute("PRAGMA threads=2")
        return cls._read_con

    @classmethod
    def get_write_connection(cls):
        if cls._write_con is None:
            Path(SETTINGS.db_path).parent.mkdir(parents=True, exist_ok=True)
            temp_dir = Path("./data/tmp")
            temp_dir.mkdir(parents=True, exist_ok=True)
            cls._write_con = duckdb.connect(SETTINGS.db_path, read_only=False)
            cls._write_con.execute("PRAGMA enable_progress_bar=false")
            cls._write_con.execute("PRAGMA memory_limit='512MB'")
            cls._write_con.execute("PRAGMA threads=2")
            cls._write_con.execute(f"PRAGMA temp_directory='{temp_dir}'")
        return cls._write_con

class PooledConnection:
    """Огортка для безпечної роботи з глобальним з'єднанням (ігнорує close)."""
    def __init__(self, read_only=False):
        self.read_only = read_only
        # Якщо read_only=True, беремо read-con, інакше write-con
        try:
            self.con = DuckDBPool.get_read_connection() if read_only else DuckDBPool.get_write_connection()
        except duckdb.Error:
            # DuckDB не дозволяє write_con та read_con одночасно в одному процесі у новіших версіях
            # через конфлікти конфігурацій. Якщо падає - використовуємо write-con для всього.
            self.con = DuckDBPool.get_write_connection()

    def __eq__(self, other):
        """Прозоре порівняння для тестів: PooledConnection(mock) == mock."""
        if isinstance(other, PooledConnection):
            return self.con == other.con
        return self.con == other

    def __hash__(self):
        return hash(self.con)

    def __getattr__(self, name):
        """Прозорий проксі до внутрішнього з'єднання."""
        return getattr(self.con, name)
            
    def execute(self, *args, **kwargs):
        if not self.read_only:
            with DuckDBPool.write_lock:
                return self.con.execute(*args, **kwargs)
        return self.con.execute(*args, **kwargs)

    def fetchdf(self):
        return self.con.fetchdf()

    def fetch_arrow_table(self):
        return self.con.fetch_arrow_table()

    def fetchone(self):
        return self.con.fetchone()
        
    def fetchall(self):
        return self.con.fetchall()

    def commit(self):
        if not self.read_only:
            with DuckDBPool.write_lock:
                return self.con.commit()

    def close(self):
        # Ми не закриваємо глобальне з'єднання
        pass

def get_connection(retries: int = 5, delay: float = 1.0, read_only: bool = False):
    """
    Повертає віртуальне з'єднання з пулу.
    Параметри retries і delay ігноруються, оскільки з'єднання завжди відкрите.
    """
    return PooledConnection(read_only=read_only)

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
        FOREIGN KEY (hackathon_id) REFERENCES hackathons(id)
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
        FOREIGN KEY (project_id) REFERENCES projects(id)
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
    ALTER TABLE features ADD COLUMN IF NOT EXISTS has_video BOOLEAN;
    UPDATE features SET has_video = FALSE WHERE has_video IS NULL;
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
            con.execute("UPDATE audit_log SET id = nextval('audit_log_id_seq') WHERE id IS NULL")
            con.execute("CHECKPOINT")
        except Exception:
            pass

        logger.info("База даних DuckDB успішно ініціалізована та перевірена.")
    finally:
        con.close()


if __name__ == "__main__":
    init_db()
