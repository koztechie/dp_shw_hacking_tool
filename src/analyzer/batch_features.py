import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.decomposition import PCA

# Гарантуємо правильні шляхи імпорту

from src.analyzer.feature_extractor import extract_features  # noqa: E402
from src.db import get_connection  # noqa: E402
from src.logger import logger  # noqa: E402
from src.ml.embedder import EmbedderSingleton  # noqa: E402
from src.utils.memory_guard import memory_guard  # noqa: E402


def safe_nan_to_none(df):
    """Безпечно конвертує всі варіанти NaN у None для сумісності зі SQLite/DuckDB"""
    return df.where(pd.notna(df), None)

@memory_guard.memory_aware(task_name="Batch Feature Extraction")
def run_batch_feature_extraction(incremental: bool = True):
    con = get_connection()
    try:
        if incremental:
            # Шукаємо лише ті хакатони, де є проекти без ознак (features)
            hackathons_df = con.execute("""
                SELECT DISTINCT h.* 
                FROM hackathons h
                JOIN projects p ON h.id = p.hackathon_id
                LEFT JOIN features f ON p.id = f.project_id
                WHERE f.project_id IS NULL
            """).fetchdf()
        else:
            # Повний перерахунок
            hackathons_df = con.execute("SELECT * FROM hackathons").fetchdf()
            
        hackathons_df = safe_nan_to_none(hackathons_df)
        org_reputation = hackathons_df["organizer"].value_counts().to_dict()

        logger.info("Завантаження Sentence-BERT (MiniLM) через синглтон...")
        embedder = EmbedderSingleton.get_model()

        logger.info(f"Починаємо генерацію Deep Learning ознак для {len(hackathons_df)} хакатонів...")

        for _, h in hackathons_df.iterrows():
            h_dict = h.to_dict()

            projects_df = con.execute("SELECT * FROM projects WHERE hackathon_id = ?", [h_dict["id"]]).fetchdf()

            if projects_df.empty:
                continue

            projects_df = safe_nan_to_none(projects_df)
            descriptions = [str(d) if d else "empty project" for d in projects_df["description"].tolist()]

            # Розрахунок ембеддингів та PCA
            semantic_features = [[0.0, 0.0, 0.0] for _ in range(len(descriptions))]
            novelty_scores = [0.5] * len(descriptions)

            if len(descriptions) > 3:
                try:
                    embeddings = embedder.encode(descriptions, show_progress_bar=False)

                    from sklearn.metrics.pairwise import cosine_similarity

                    sim_matrix = cosine_similarity(embeddings)
                    avg_sim = (sim_matrix.sum(axis=1) - 1) / (len(descriptions) - 1)
                    novelty_scores = [round(float(score), 4) for score in (1.0 - avg_sim)]

                    pca = PCA(n_components=3, random_state=42)
                    semantic_features = pca.fit_transform(embeddings).tolist()
                except Exception as e:
                    logger.error(f"Помилка Embeddings: {e}")

            try:
                con.execute("BEGIN")
                total_projects = len(projects_df)
                org_rep = org_reputation.get(h_dict.get("organizer"), 1)

                for i, (_, p) in enumerate(projects_df.iterrows()):
                    p_dict = p.to_dict()
                    f = extract_features(p_dict, h_dict, total_projects, org_rep)

                    con.execute(
                        """
                        INSERT OR REPLACE INTO features (
                            project_id, uses_sponsor_tech, tech_count, has_social_angle,
                            description_length, novelty_score, has_github, readme_length,
                            commit_count_48h, final_score, sponsor_challenge_match,
                            has_video_demo, competition_density, prize_numeric,
                            semantic_pca_1, semantic_pca_2, semantic_pca_3, github_stars,
                            repo_size, repo_issues, days_before_deadline, prize_per_team, organizer_reputation
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                        [
                            p_dict["id"],
                            f["uses_sponsor_tech"],
                            f["tech_count"],
                            f["has_social_angle"],
                            f["description_length"],
                            novelty_scores[i],
                            f["has_github"],
                            f["readme_length"],
                            f["commit_count_48h"],
                            None,
                            f["sponsor_challenge_match"],
                            f["has_video_demo"],
                            f["competition_density"],
                            f["prize_numeric"],
                            float(semantic_features[i][0]),
                            float(semantic_features[i][1]),
                            float(semantic_features[i][2]),
                            f["github_stars"],
                            f["repo_size"],
                            f["repo_issues"],
                            f["days_before_deadline"],
                            f["prize_per_team"],
                            f["organizer_reputation"],
                        ],
                    )
                con.commit()
                logger.info(f"✅ Ознаки згенеровано для хакатону: {h_dict.get('title')} ({total_projects} проектів)")
            except Exception as e:
                con.execute("ROLLBACK")
                logger.error(f"❌ Помилка обробки хакатону {h_dict.get('title')}: {e}")

        EmbedderSingleton.cleanup()
        logger.info("Генерацію розширених Deep Learning ознак завершено.")
    except Exception as e:
        logger.error(f"Помилка batch_features: {e}")
    finally:
        con.close()


if __name__ == "__main__":
    run_batch_feature_extraction()
