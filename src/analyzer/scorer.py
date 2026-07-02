import sys
from pathlib import Path
import json
import re

# Гарантуємо правильні шляхи імпорту
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.ml.predictor import predict_win_probability
from src.analyzer.causal_inference import get_counterfactual_advice
from src.analyzer.xai_explainer import explain_prediction
from src.analyzer.ai_client import generate_json_with_failover
from src.logger import logger

def _safe_len(val) -> int:
    if not val: return 0
    if isinstance(val, (list, str, dict)): return len(val)
    return 0

def _simulate_judge(idea: dict, hackathon_data: dict) -> dict:
    """
    Agentic Simulation: ШІ імітує реальне журі хакатону на основі їхнього профілю та критеріїв.
    """
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
    """Гібридна оцінка: Ансамбль ML + AI-симуляція суддів + Адаптивні ваги."""
    
    logger.info(f"⚖️ Початок оцінювання ідеї: '{idea.get('title')}'")
    
    # 1. Підготовка кількісних ознак (18 штук для нашого Ансамблю)
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
        "semantic_pca_1": 0.0, "semantic_pca_2": 0.0, "semantic_pca_3": 0.0, "github_stars": 0
    }

    # 2. Холодний розрахунок (ML Score) та визначення впевненості (Confidence)
    ml_score = predict_win_probability(features)
    # Математичний довірчий інтервал (аналог Monte Carlo uncertainty)
    confidence = abs(ml_score - 0.5) * 2  

    # 3. Емпатичний розрахунок (Agentic Judge Simulation)
    judge_eval = _simulate_judge(idea, hackathon_data)
    judge_score = float(judge_eval.get("judge_score", 0.65))
    logger.info(f"   🧑‍⚖️ Вердикт судді: {judge_score:.2f} ({judge_eval.get('critique')})")

    # 4. Adaptive Weights (Динамічне зважування на основі теми)
    themes = str(hackathon_data.get("themes", [])).lower()
    tech_heavy = any(t in themes for t in ["ai", "machine learning", "blockchain", "cloud", "api", "hardware"])
    soft_heavy = any(t in themes for t in ["social", "education", "design", "music", "art"])
    
    if tech_heavy and not soft_heavy:
        ml_weight, judge_weight = 0.7, 0.3
        logger.info("   ⚙️ Застосовано технічні ваги (ML: 70%, Журі: 30%)")
    elif soft_heavy and not tech_heavy:
        ml_weight, judge_weight = 0.4, 0.6
        logger.info("   🎨 Застосовано гуманітарні ваги (ML: 40%, Журі: 60%)")
    else:
        ml_weight, judge_weight = 0.6, 0.4
        logger.info("   ⚖️ Застосовано збалансовані ваги (ML: 60%, Журі: 40%)")

    # Якщо ML не впевнений у результаті (близько 50%), віддаємо більше влади живому судді
    if confidence < 0.3:
        ml_weight -= 0.15
        judge_weight += 0.15

    final_score = (ml_score * ml_weight) + (judge_score * judge_weight)
    final_score = min(final_score, 0.99)
    
    logger.info(f"   📊 ФІНАЛ: ML={ml_score:.3f} | Judge={judge_score:.3f} | Впевненість={confidence*100:.1f}% -> Підсумок={final_score:.3f}")
    
        # 5. Causal Inference (Counterfactual Analysis)
    idea["causal_advice"] = get_counterfactual_advice(features, ml_score)
    
        # 6. Explainable AI (XAI)
    idea["xai_explanation"] = explain_prediction(features, ml_score)
    
    return final_score

def rank_ideas(ideas: list[dict], hackathon_data: dict) -> list[dict]:
    """Оцінює та ранжує список ідей."""
    logger.info(f"Починаємо динамічний скоринг для {len(ideas)} ідей...")
    for idea in ideas:
        idea["win_probability"] = score_idea(idea, hackathon_data)
    return sorted(ideas, key=lambda x: x["win_probability"], reverse=True)

if __name__ == "__main__":
    print("=== ТЕСТУВАННЯ АДАПТИВНОГО СКОРИНГУ ТА AI-ЖУРІ ===")
    mock_hackathon = {
        "title": "Social Impact Web3 Hack",
        "themes": ["Social Good", "Blockchain"],
        "judges_info": "Vitalik Buterin, NGO Directors",
        "judging_criteria": "Must solve a real social problem using transparent ledgers."
    }
    mock_idea = {
        "title": "Transparent Charity Ledger",
        "tagline": "Track your donations on the blockchain.",
        "solution": "A smart contract system for NGOs.",
        "tech_stack": ["Solidity", "React"],
        "target_track": "Best Social Good Hack"
    }
    score = score_idea(mock_idea, mock_hackathon)
    print(f"\n🔮 Фінальна ймовірність перемоги: {score*100:.2f}%")
