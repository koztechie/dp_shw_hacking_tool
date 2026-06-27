import sys
from pathlib import Path
import pandas as pd
import numpy as np

# Гарантуємо правильні шляхи імпорту
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.analyzer.feature_extractor import extract_features, compute_novelty_scores
from src.db import get_connection
from src.logger import logger

def run_batch_feature_extraction():
    con = get_connection()
    
    try:
        # Зчитуємо хакатони та безпечно перетворюємо Pandas NaN на None
        hackathons_df = con.execute("SELECT * FROM hackathons").fetchdf()
        hackathons_df = hackathons_df.replace({np.nan: None})
        
        logger.info(f"Починаємо генерацію ознак для {len(hackathons_df)} хакатонів...")

        for _, h in hackathons_df.iterrows():
            h_dict = h.to_dict()
            h_id = h_dict.get("id")
            
            projects_df = con.execute(
                "SELECT * FROM projects WHERE hackathon_id = ?", [h_id]
            ).fetchdf()

            if projects_df.empty:
                continue

            # Захист від NaN у текстових полях
            projects_df = projects_df.replace({np.nan: None})
            
            # Підготовка описів для TF-IDF (Novelty Score)
            descriptions = [str(d) if d else "" for d in projects_df["description"].tolist()]
            novelty_scores = compute_novelty_scores(descriptions)

            try:
                con.execute("BEGIN")
                
                for i, (_, p) in enumerate(projects_df.iterrows()):
                    p_dict = p.to_dict()
                    
                    # Витягуємо ознаки за допомогою нашого стійкого екстрактора
                    features = extract_features(p_dict, h_dict)
                    
                    # Формуємо безпечний запит із явним вказанням стовпців
                    con.execute("""
                        INSERT OR REPLACE INTO features (
                            project_id, uses_sponsor_tech, tech_count, has_social_angle,
                            description_length, novelty_score, has_github, readme_length,
                            commit_count_48h, final_score, sponsor_challenge_match
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, [
                        p_dict["id"],
                        features.get("uses_sponsor_tech", False),
                        features.get("tech_count", 0),
                        features.get("has_social_angle", False),
                        features.get("description_length", 0),
                        novelty_scores[i],
                        features.get("has_github", False),
                        features.get("readme_length", 0),
                        features.get("commit_count_48h", 0),
                        None,  # final_score (буде розраховано моделлю)
                        features.get("sponsor_challenge_match", False)
                    ])

                con.commit()
                logger.info(f"✅ Ознаки збережено для хакатону: {h_dict.get('title')} ({len(projects_df)} проектів)")
                
            except Exception as e:
                con.execute("ROLLBACK")
                logger.error(f"❌ Помилка обробки хакатону {h_dict.get('title')}: {e}")

    except Exception as e:
        logger.error(f"Критична помилка пакетної генерації: {e}")
    finally:
        con.close()
        logger.info("Процедуру генерації ознак завершено.")

if __name__ == "__main__":
    run_batch_feature_extraction()
