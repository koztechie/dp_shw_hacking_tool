import sys
from pathlib import Path
import json
import re
import numpy as np

# Гарантуємо правильні шляхи імпорту
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.ml.predictor import predict_win_probability
from src.analyzer.ai_client import generate_json_with_failover
from src.analyzer.causal_inference import get_counterfactual_advice
from src.analyzer.xai_explainer import explain_prediction
from src.logger import logger

# АНТИКРИХКІСТЬ: Менеджер життєвого циклу моделі (Memory Leak Protection)
class EmbedderManager:
    _embedder = None

    @classmethod
    def get_embedder(cls):
        if cls._embedder is None:
            logger.info("Завантаження Sentence-BERT для інференсу (Lazy Load)...")
            from sentence_transformers import SentenceTransformer
            cls._embedder = SentenceTransformer('all-MiniLM-L6-v2')
        return cls._embedder

    @classmethod
    def cleanup(cls):
        """Викликати після кожного інференсу для тотальної економії RAM"""
        if cls._embedder is not None:
            del cls._embedder
            cls._embedder = None
            import gc
            gc.collect()
            logger.info("🧹 Sentence-BERT видалено з пам'яті (RAM звільнено).")

def get_embedder():
    return EmbedderManager.get_embedder()

def _safe_len(val) -> int:
    if not val: return 0
    if isinstance(val, (list, str, dict)): return len(val)
    return 0

def _simulate_judge(idea: dict, hackathon_data: dict) -> dict:
    judges = hackathon_data.get("judges_info", "Industry Experts")
    criteria = hackathon_data.get("judging_criteria", "Innovation, Technical Complexity, Impact")
    
    prompt = f"""
    You are the official judging panel for the "{hackathon_data.get('title')}" hackathon.
    Judging Criteria: {criteria}
    Judges Background: {judges}
    
    Critically evaluate this project submission:
    Title: {idea.get('title')}
    Pitch: {idea.get('tagline')}
    Solution: {idea.get('solution')}
    Tech Stack: {', '.join(idea.get('tech_stack', []))}
    
    Return EXACTLY a JSON object with your evaluation:
    {{
      "judge_score": <float between 0.00 and 1.00>,
      "critique": "1 sentence explaining why it will win or lose based strictly on the criteria"
    }}
    """
    
    result = generate_json_with_failover(prompt)
    if "fallback" in result or "error" in result:
        return {"judge_score": 0.65, "critique": "Offline fallback score applied."}
    return result

def score_idea(idea: dict, hackathon_data: dict) -> float:
    logger.info(f"⚖️ Початок оцінювання ідеї: '{idea.get('title')}'")
    
    prize_str = str(hackathon_data.get("prize_total", "0"))
    prize_digits = re.sub(r"\D", "", prize_str)
    prize_numeric = int(prize_digits) if prize_digits else 0
    participants = int(hackathon_data.get("participant_count") or 100)
    competition_density = round(participants / 40, 2)

    features = {
        "title": idea.get("title", "Unknown Idea"),
        "uses_sponsor_tech": _safe_len(idea.get("sponsor_tech_used")) > 0,
        "tech_count": _safe_len(idea.get("tech_stack")),
        "has_social_angle": any(kw in str(idea.get("problem", "")).lower() for kw in ["health", "education", "sustainab", "accessib", "poverty", "eco"]),
        "description_length": _safe_len(idea.get("solution")),
        "has_github": False, "readme_length": 0, "commit_count_48h": 0, "novelty_score": 0.85, "likes": 0, "team_size": 1,
        "sponsor_challenge_match": bool(idea.get("target_track")), "has_video_demo": True,
        "competition_density": competition_density, "prize_numeric": prize_numeric,
        "semantic_pca_1": float(idea.get("semantic_pca_1", 0.0)),
        "semantic_pca_2": float(idea.get("semantic_pca_2", 0.0)),
        "semantic_pca_3": float(idea.get("semantic_pca_3", 0.0)),
        "github_stars": 0
    }

    ml_score = predict_win_probability(features)
    confidence = abs(ml_score - 0.5) * 2  

    judge_eval = _simulate_judge(idea, hackathon_data)
    judge_score = float(judge_eval.get("judge_score", 0.65))
    logger.info(f"   🧑‍⚖️ Вердикт судді: {judge_score:.2f} ({judge_eval.get('critique')})")

    themes = str(hackathon_data.get("themes", [])).lower()
    tech_heavy = any(t in themes for t in ["ai", "machine learning", "blockchain", "cloud", "api", "hardware"])
    soft_heavy = any(t in themes for t in ["social", "education", "design", "music", "art"])
    
    if tech_heavy and not soft_heavy:
        ml_weight, judge_weight = 0.7, 0.3
    elif soft_heavy and not tech_heavy:
        ml_weight, judge_weight = 0.4, 0.6
    else:
        ml_weight, judge_weight = 0.6, 0.4

    if confidence < 0.3:
        ml_weight -= 0.15
        judge_weight += 0.15

    final_score = (ml_score * ml_weight) + (judge_score * judge_weight)
    final_score = min(final_score, 0.99)
    
    logger.info(f"   📊 ФІНАЛ: ML={ml_score:.3f} | Judge={judge_score:.3f} | Впевненість={confidence*100:.1f}% -> Підсумок={final_score:.3f}")
    
    idea["causal_advice"] = get_counterfactual_advice(features, ml_score)
    idea["xai_explanation"] = explain_prediction(features, ml_score)
    
    return final_score

def rank_ideas(ideas: list[dict], hackathon_data: dict) -> list[dict]:
    logger.info(f"Починаємо динамічний скоринг для {len(ideas)} ідей...")
    
    # АНТИКРИХКІСТЬ: Гарантоване звільнення пам'яті через try/finally
    try:
        if ideas:
            try:
                from sklearn.decomposition import PCA
                embedder = get_embedder()
                descriptions = [str(i.get("solution", i.get("title", ""))) for i in ideas]
                embeddings = embedder.encode(descriptions, show_progress_bar=False)
                
                n_comp = min(3, len(ideas))
                if n_comp > 0:
                    pca = PCA(n_components=n_comp, random_state=42)
                    transformed = pca.fit_transform(embeddings)
                    if n_comp < 3:
                        transformed = np.pad(transformed, ((0, 0), (0, 3 - n_comp)), 'constant')
                    semantic_features = transformed.tolist()
                else:
                    semantic_features = [[0.0, 0.0, 0.0] for _ in ideas]
                    
                for idx, idea in enumerate(ideas):
                    idea["semantic_pca_1"] = semantic_features[idx][0]
                    idea["semantic_pca_2"] = semantic_features[idx][1]
                    idea["semantic_pca_3"] = semantic_features[idx][2]
            except Exception as e:
                logger.error(f"Помилка розрахунку семантичних PCA на інференсі: {e}")

        for idea in ideas:
            idea["win_probability"] = score_idea(idea, hackathon_data)
            
        return sorted(ideas, key=lambda x: x["win_probability"], reverse=True)
    finally:
        # Після оцінки всіх ідей повністю вичищаємо Sentence-BERT з RAM
        EmbedderManager.cleanup()

if __name__ == "__main__":
    print("=== ТЕСТУВАННЯ МЕНЕДЖЕРА ПАМ'ЯТІ (Memory Leak Fix) ===")
    mock_hackathon = {"title": "AI Summit"}
    mock_ideas = [
        {"title": "Idea 1", "solution": "A complex neural network for healthcare."},
        {"title": "Idea 2", "solution": "A simple todo list app."}
    ]
    ranked = rank_ideas(mock_ideas, mock_hackathon)
    for i in ranked:
        print(f"{i['title']} - PCA1: {i.get('semantic_pca_1', 0):.4f}")
