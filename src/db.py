import sys
from pathlib import Path
import duckdb

# Гарантуємо правильні шляхи імпорту
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import DB_PATH

def get_connection():
    """
    Повертає з'єднання з DuckDB. 
    Автоматично створює папку даних, якщо її було видалено.
    """
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(DB_PATH)

def init_db():
    """
    Безпечно ініціалізує повну структуру бази даних.
    Використовує блок try...finally для запобігання витоку блокування файлу БД.
    """
    con = get_connection()
    try:
        # 1. Таблиця хакатонів (start_date та end_date тепер VARCHAR)
        con.execute("""
            CREATE TABLE IF NOT EXISTS hackathons (
                id VARCHAR PRIMARY KEY,
                url VARCHAR,
                title VARCHAR,
                organizer VARCHAR,
                start_date VARCHAR,     -- Змінено на VARCHAR для стійкості до форматів дат
                end_date VARCHAR,       -- Змінено на VARCHAR для стійкості до форматів дат
                prize_total VARCHAR,
                participant_count INTEGER,
                themes VARCHAR,  -- JSON array
                sponsors VARCHAR,  -- JSON array
                judging_criteria VARCHAR,  -- raw text
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
                tech_tags VARCHAR,  -- JSON array
                team_size INTEGER,
                likes INTEGER,
                github_url VARCHAR,
                demo_url VARCHAR,
                is_winner BOOLEAN DEFAULT FALSE,
                prize_track VARCHAR,
                win_score FLOAT,  -- розрахований нами
                readme_length INTEGER,       -- ДОДАНО для збереження GitHub метрик
                commit_count_48h INTEGER,     -- ДОДАНО для збереження GitHub метрик
                scraped_at TIMESTAMP DEFAULT current_timestamp
            )
        """)
        
        # 3. Таблиця ознак для ML
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
                final_score FLOAT
            )
        """)
        
        # 4. Таблиця прогнозів та генерацій ТЗ
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
                techspec VARCHAR  -- JSON повне ТЗ
            )
        """)
        print("Базу даних DuckDB успішно ініціалізовано.")
    except Exception as e:
        print(f"Помилка під час ініціалізації БД: {e}")
        raise e
    finally:
        con.close()

if __name__ == "__main__":
    init_db()
