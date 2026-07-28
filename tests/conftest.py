import pytest
import tempfile
import shutil
from pathlib import Path
import duckdb
import pickle
import os
from unittest.mock import patch

@pytest.fixture(scope="session")
def test_data_dir():
    """АНТИКРИХКІСТЬ: Тимчасова директорія для тестових даних."""
    temp_dir = Path(tempfile.mkdtemp(prefix="dp_shw_test_"))
    yield temp_dir
    # Cleanup після всіх тестів
    if temp_dir.exists():
        shutil.rmtree(temp_dir)

@pytest.fixture(scope="session")
def test_db(test_data_dir):
    """АНТИКРИХКІСТЬ: Ізольована тестова БД."""
    db_path = test_data_dir / "test.duckdb"
    con = duckdb.connect(str(db_path))
    
    # Створюємо тестову схему
    con.execute("""
        CREATE TABLE IF NOT EXISTS hackathons (
            id VARCHAR PRIMARY KEY,
            title VARCHAR,
            url VARCHAR,
            start_date TIMESTAMP,
            end_date TIMESTAMP,
            prize_total VARCHAR,
            scraped_at TIMESTAMP DEFAULT current_timestamp
        )
    """)
    
    con.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id VARCHAR PRIMARY KEY,
            hackathon_id VARCHAR,
            title VARCHAR,
            description TEXT,
            is_winner BOOLEAN DEFAULT FALSE,
            likes INTEGER DEFAULT 0,
            scraped_at TIMESTAMP DEFAULT current_timestamp
        )
    """)
    
    con.execute("""
        CREATE TABLE IF NOT EXISTS features (
            project_id VARCHAR PRIMARY KEY,
            description_length INTEGER,
            tech_count INTEGER,
            uses_sponsor_tech BOOLEAN,
            has_video_demo BOOLEAN,
            has_github BOOLEAN
        )
    """)
    
    # Додано для сумісності з API health check та інтеграційними тестами
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

    con.execute("""
        CREATE SEQUENCE IF NOT EXISTS audit_log_id_seq START 1;
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY DEFAULT nextval('audit_log_id_seq'),
            timestamp TIMESTAMP DEFAULT current_timestamp,
            user_ip VARCHAR,
            endpoint VARCHAR,
            method VARCHAR,
            status_code INTEGER,
            details VARCHAR
        )
    """)
    
    con.close()
    return db_path

@pytest.fixture
def db_connection(test_db):
    """АНТИКРИХКІСТЬ: Тимчасове з'єднання з БД для кожного тесту."""
    con = duckdb.connect(str(test_db))
    yield con
    con.close()

@pytest.fixture
def sample_hackathon(db_connection):
    """Тестовий хакатон."""
    hackathon_id = "test_hackathon_001"
    db_connection.execute("""
        INSERT INTO hackathons (id, title, url, start_date, end_date, prize_total)
        VALUES (?, ?, ?, ?, ?, ?)
    """, [
        hackathon_id,
        "Test Hackathon 2024",
        "https://devpost.com/test-hackathon",
        "2024-01-01 00:00:00",
        "2024-01-15 23:59:59",
        "$10,000"
    ])
    return hackathon_id

@pytest.fixture
def sample_project(db_connection, sample_hackathon):
    """Тестовий проект."""
    project_id = "test_project_001"
    db_connection.execute("""
        INSERT INTO projects (id, hackathon_id, title, description, is_winner, likes)
        VALUES (?, ?, ?, ?, ?, ?)
    """, [
        project_id,
        sample_hackathon,
        "Test Project",
        "This is a test project description for unit testing.",
        False,
        42
    ])
    return project_id

@pytest.fixture
def sample_features(db_connection, sample_project):
    """Тестові features."""
    db_connection.execute("""
        INSERT INTO features (project_id, description_length, tech_count, uses_sponsor_tech, has_video_demo, has_github)
        VALUES (?, ?, ?, ?, ?, ?)
    """, [
        sample_project,
        500,
        5,
        True,
        True,
        True
    ])
    return sample_project

@pytest.fixture
def mock_ml_model(test_data_dir):
    """АНТИКРИХКІСТЬ: Мок ML моделі для тестів."""
    from sklearn.ensemble import RandomForestClassifier
    import numpy as np
    
    # Створюємо просту модель
    model = RandomForestClassifier(n_estimators=10, random_state=42)
    X = np.random.rand(100, 5)
    y = np.random.randint(0, 2, 100)
    model.fit(X, y)
    
    # Зберігаємо в тестову директорію (шлях 'data/models' для сумісності з health check)
    models_dir = test_data_dir / "data" / "models"
    models_dir.mkdir(parents=True, exist_ok=True)
    
    model_path = models_dir / "best_model.pkl"
    features_path = models_dir / "feature_names.pkl"
    
    with open(model_path, "wb") as f:
        pickle.dump(model, f)
    
    with open(features_path, "wb") as f:
        pickle.dump(["feat1", "feat2", "feat3", "feat4", "feat5"], f)
    
    return model_path, features_path

@pytest.fixture
def mock_api_response():
    """АНТИКРИХКІСТЬ: Мок відповіді від AI API."""
    return {
        "ideas": [
            {
                "title": "Test Idea",
                "tagline": "A test idea for unit testing",
                "problem": "Test problem",
                "solution": "Test solution",
                "tech_stack": ["Python", "FastAPI"],
                "why_wins": "Because it's a test"
            }
        ]
    }

@pytest.fixture(autouse=True)
def mock_environment():
    """АНТИКРИХКІСТЬ: Мок змінних оточення для всіх тестів."""
    with patch.dict(os.environ, {
        "MIMO_API_KEY": "test_key_12345",
        "OPENROUTER_API_KEY": "test_or_key_12345",
        "SENTRY_DSN": "",
        "ENV": "testing"
    }):
        yield

@pytest.fixture(autouse=True)
def patch_db_settings(test_db):
    """АНТИКРИХКІСТЬ: Забезпечує, щоб усі тести використовували тестову БД та очищає пул з'єднань."""
    from config.settings import SETTINGS
    from src.db import DuckDBPool
    
    DuckDBPool.shutdown()
    
    original_path = SETTINGS.db_path
    SETTINGS.db_path = test_db
    
    yield
    
    DuckDBPool.shutdown()
    SETTINGS.db_path = original_path
