import sys
from pathlib import Path
import json

# Гарантуємо правильні шляхи імпорту
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.ml.predictor import predict_win_probability
from src.logger import logger

def _safe_len(val) -> int:
    """Безпечно обчислює довжину об'єкта, уникаючи TypeError для None або чисел."""
    if not val:
        return 0
    if isinstance(val, (list, str, dict)):
        return len(val)
    return 0

def score_idea(idea: dict, hackathon_data: dict) -> float:
    """
    Гібридна оцінка ідеї: 
    60% - прогнозування ML-моделі на основі технічних параметрів.
    40% - семантичний аналіз (повнота пітчу, наявність killer feature).
    """
    # 1. Підготовка кількісних ознак для ML-моделі
    features = {
        "title": idea.get("title", "Unknown Idea"),
        "uses_sponsor_tech": _safe_len(idea.get("sponsor_tech_used")) > 0,
        "tech_count": _safe_len(idea.get("tech_stack")),
        "has_social_angle": any(
            kw in str(idea.get("problem", "")).lower()
            for kw in ["health", "education", "sustainab", "accessib", "poverty", "eco"]
        ),
        "description_length": _safe_len(idea.get("solution")),
        "has_github": False,     # Ідея ще не реалізована, репозиторію немає
        "readme_length": 0,      # Немає репозиторію
        "commit_count_48h": 0,   # Немає розробки
        "novelty_score": 0.85,   # AI генерує унікальні ідеї, тому ставимо високий baseline
        "likes": 0,
        "team_size": 1,
        "sponsor_challenge_match": bool(idea.get("target_track")) # Заповнення важливої ML-фічі
    }

    # Отримуємо прогноз від нашого натренованого Random Forest
    ml_score = predict_win_probability(features)

    # 2. Семантичний бонус (Оцінка якості пітчингу)
    semantic_bonus = 0.0
    if idea.get("killer_feature"):
        semantic_bonus += 0.05
    if idea.get("target_track"):
        semantic_bonus += 0.05
    if _safe_len(idea.get("why_wins")) > 100:
        semantic_bonus += 0.05

    # Гібридний розрахунок (ML має більшу вагу)
    final_score = (ml_score * 0.6) + ((ml_score + semantic_bonus) * 0.4)
    
    # Обрізаємо значення, щоб воно не перевищило 99%
    final_score = min(final_score, 0.99)
    
    logger.info(f"Оцінка ідеї '{features['title']}': ML_prob={ml_score:.3f}, Semantic_bonus={semantic_bonus:.2f} -> Final={final_score:.3f}")
    
    return final_score

def rank_ideas(ideas: list[dict], hackathon_data: dict) -> list[dict]:
    """Ранжує згенеровані ідеї за їхньою фінальною ймовірністю перемоги."""
    for idea in ideas:
        idea["win_probability"] = score_idea(idea, hackathon_data)
        
    # Сортування за спаданням ймовірності
    return sorted(ideas, key=lambda x: x["win_probability"], reverse=True)

if __name__ == "__main__":
    print("=== ТЕСТУВАННЯ ГІБРИДНОГО СКОРЕРУ (Етап 35) ===")
    
    # Мок-дані для тесту
    mock_hackathon = {"title": "Test Hack"}
    
    mock_ideas = [
        {
            "title": "Слабка Ідея (Клон)",
            "problem": "People forget things.",
            "solution": "A simple to-do list app.",
            "tech_stack": ["HTML", "CSS"],
            "sponsor_tech_used": [],
            "target_track": "",
            "killer_feature": "",
            "why_wins": "Because it is simple."
        },
        {
            "title": "Сильна Ідея (Інновація)",
            "problem": "Health clinics lack accessible sustainable data storage.",
            "solution": "We use decentralized nodes to store patient records securely...",
            "tech_stack": ["React", "Python", "Google Cloud", "IPFS"],
            "sponsor_tech_used": ["Google Cloud"],
            "target_track": "Best use of Google Cloud",
            "killer_feature": "Zero-knowledge proof verification for patients",
            "why_wins": "This directly aligns with the sponsor's goal of expanding healthcare infrastructure using their Cloud APIs. It solves a real-world problem and has a working MVP."
        }
    ]
    
    ranked = rank_ideas(mock_ideas, mock_hackathon)
    
    print("\n🏆 РАНЖУВАННЯ ІДЕЙ:")
    for i, idea in enumerate(ranked, 1):
        print(f"{i}. {idea['title']} - Ймовірність: {idea['win_probability']*100:.2f}%")
