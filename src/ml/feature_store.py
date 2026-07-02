import sys
from pathlib import Path
from datetime import datetime
import duckdb
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import DB_PATH
from src.logger import logger
try:
    import sentry_sdk
except ImportError:
    sentry_sdk = None

STORE_DIR = PROJECT_ROOT / "data" / "feature_store"
STORE_DIR.mkdir(parents=True, exist_ok=True)

class LightweightFeatureStore:
    """
    Антикрихка альтернатива Feast/Tecton.
    Забезпечує Feature Versioning (через Parquet) та Data Quality Monitoring.
    """
    def __init__(self):
        self.db_path = DB_PATH

    def snapshot_features(self) -> str:
        """Створює незмінний Parquet-зліпок поточного стану фіч (Feature Versioning)."""
        version_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_path = STORE_DIR / f"features_v_{version_id}.parquet"
        
        try:
            con = duckdb.connect(self.db_path, read_only=True)
            # Експортуємо джоін фіч та цільової змінної у надшвидкий формат Parquet
            query = f"""
                COPY (
                    SELECT f.*, p.is_winner 
                    FROM features f 
                    JOIN projects p ON f.project_id = p.id
                ) TO '{file_path}' (FORMAT PARQUET);
            """
            con.execute(query)
            logger.info(f"📦 Feature Snapshot створено: {file_path.name}")
            return str(file_path)
        except Exception as e:
            logger.error(f"Помилка створення Feature Snapshot: {e}")
            return ""
        finally:
            if 'con' in locals(): con.close()

    def get_training_data(self) -> pd.DataFrame:
        """Отримує фічі для навчання та автоматично перевіряє їх на деградацію."""
        try:
            con = duckdb.connect(self.db_path, read_only=True)
            df = con.execute("""
                SELECT
                    f.uses_sponsor_tech, f.tech_count, f.has_social_angle,
                    f.description_length, f.has_github, f.readme_length,
                    f.commit_count_48h, f.novelty_score, f.sponsor_challenge_match,
                    f.has_video_demo, f.competition_density, f.prize_numeric,
                    f.semantic_pca_1, f.semantic_pca_2, f.semantic_pca_3, f.github_stars,
                    p.likes, p.team_size, p.is_winner
                FROM features f
                JOIN projects p ON f.project_id = p.id
                WHERE p.description IS NOT NULL AND length(p.description) > 10
                ORDER BY p.scraped_at DESC
            """).fetchdf()
            
            self._monitor_data_quality(df)
            return df
        finally:
            if 'con' in locals(): con.close()

    def _monitor_data_quality(self, df: pd.DataFrame):
        """Feature Monitoring: перевіряє аномалії (Data Drift або збої скраперів)."""
        alerts = []
        
        # Перевірка 1: Чи не зламався скрапер GitHub?
        if df['has_github'].mean() < 0.05:
            alerts.append("Data Quality Alert: Понад 95% проектів не мають GitHub. Можливо змінилася верстка Devpost!")
            
        # Перевірка 2: Чи заповнюються семантичні фічі?
        if df['semantic_pca_1'].var() == 0:
            alerts.append("Data Quality Alert: Нульова дисперсія в semantic_pca_1 (LSA не працює)!")
            
        # Перевірка 3: Чи не зламався скрапер спонсорів?
        if df['uses_sponsor_tech'].mean() == 0.0:
            alerts.append("Data Quality Alert: Жоден проект не використовує технології спонсорів. Перевірте backfill_sponsors!")

        for alert in alerts:
            logger.warning(alert)
            if sentry_sdk:
                sentry_sdk.capture_message(alert, level="warning")

if __name__ == "__main__":
    print("=== ТЕСТУВАННЯ FEATURE STORE (Етап 11) ===")
    fs = LightweightFeatureStore()
    
    snapshot_path = fs.snapshot_features()
    print(f"✅ Зліпок створено за адресою: {snapshot_path}")
    
    df = fs.get_training_data()
    print(f"✅ Успішно зчитано {len(df)} записів.")
    print("✅ Моніторинг якості даних виконано.")
