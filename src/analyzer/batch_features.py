import sys
from pathlib import Path
import pandas as pd
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.decomposition import TruncatedSVD

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.analyzer.feature_extractor import extract_features, compute_novelty_scores
from src.db import get_connection
from src.logger import logger

def run_batch_feature_extraction():
    con = get_connection()
    try:
        hackathons_df = con.execute("SELECT * FROM hackathons").fetchdf().replace({np.nan: None})
        logger.info(f"Починаємо генерацію розширених ознак для {len(hackathons_df)} хакатонів...")

        for _, h in hackathons_df.iterrows():
            h_dict = h.to_dict()
            projects_df = con.execute("SELECT * FROM projects WHERE hackathon_id = ?", [h_dict["id"]]).fetchdf()

            if projects_df.empty:
                continue

            projects_df = projects_df.replace({np.nan: None})
            descriptions = [str(d) if d else "" for d in projects_df["description"].tolist()]
            
            novelty_scores = compute_novelty_scores(descriptions)

            # --- АНТИКРИХКІ ЕМБЕДДИНГИ (LSA замість BERT) ---
            semantic_features = [[0.0, 0.0, 0.0] for _ in range(len(descriptions))]
            if len(descriptions) > 3:
                try:
                    vec = TfidfVectorizer(max_features=300, stop_words="english")
                    tfidf_matrix = vec.fit_transform(descriptions)
                    # Стискаємо текст у 3 числові координати
                    svd = TruncatedSVD(n_components=3, random_state=42)
                    semantic_features = svd.fit_transform(tfidf_matrix).tolist()
                except Exception:
                    pass

            try:
                con.execute("BEGIN")
                total_projects = len(projects_df)
                
                for i, (_, p) in enumerate(projects_df.iterrows()):
                    p_dict = p.to_dict()
                    f = extract_features(p_dict, h_dict, total_projects)
                    
                    con.execute("""
                        INSERT OR REPLACE INTO features (
                            project_id, uses_sponsor_tech, tech_count, has_social_angle,
                            description_length, novelty_score, has_github, readme_length,
                            commit_count_48h, final_score, sponsor_challenge_match,
                            has_video_demo, competition_density, prize_numeric,
                            semantic_pca_1, semantic_pca_2, semantic_pca_3, github_stars
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, [
                        p_dict["id"], f["uses_sponsor_tech"], f["tech_count"], f["has_social_angle"],
                        f["description_length"], novelty_scores[i], f["has_github"], f["readme_length"],
                        f["commit_count_48h"], None, f["sponsor_challenge_match"],
                        f["has_video_demo"], f["competition_density"], f["prize_numeric"],
                        float(semantic_features[i][0]), float(semantic_features[i][1]), float(semantic_features[i][2]),
                        f["github_stars"]
                    ])
                con.commit()
            except Exception as e:
                con.execute("ROLLBACK")
                logger.error(f"❌ Помилка обробки хакатону: {e}")

    finally:
        con.close()
        logger.info("Генерацію розширених ознак завершено.")

if __name__ == "__main__":
    run_batch_feature_extraction()
