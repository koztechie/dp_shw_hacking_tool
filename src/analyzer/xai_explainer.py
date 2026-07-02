import sys
from pathlib import Path
import copy

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.ml.predictor import predict_win_probability

def explain_prediction(features: dict, base_ml_score: float) -> dict:
    """
    Explainable AI (Feature Ablation): 
    Миттєво обчислює реальний внесок кожної ознаки у фінальний прогноз.
    Працює за принципом "Наскільки впаде бал, якщо прибрати цю ознаку?"
    """
    contributions = []
    
    # 1. Оцінюємо позитивні фактори (що тягне бал вгору)
    positive_checks = [
        ("has_video_demo", 0, "Наявність відео-демо"),
        ("uses_sponsor_tech", 0, "Технології спонсора"),
        ("sponsor_challenge_match", 0, "Попадання в цільовий трек"),
        ("has_social_angle", 0, "Соціальна значущість"),
        ("has_github", 0, "Відкритий репозиторій")
    ]
    
    for feat_key, ablated_val, feat_name in positive_checks:
        if features.get(feat_key):  # Якщо фіча присутня
            cf_features = copy.deepcopy(features)
            cf_features[feat_key] = ablated_val
            ablated_score = predict_win_probability(cf_features)
            impact = base_ml_score - ablated_score
            
            if impact > 0.01:
                contributions.append({
                    "name": feat_name,
                    "impact": impact,
                    "type": "positive",
                    "text": f"✅ {feat_name}: +{impact*100:.1f}% до шансів"
                })

    # Спеціальна перевірка для унікальності
    if features.get("novelty_score", 0) > 0.7:
        cf_features = copy.deepcopy(features)
        cf_features["novelty_score"] = 0.5  # Знижуємо до середнього "клона"
        ablated_score = predict_win_probability(cf_features)
        impact = base_ml_score - ablated_score
        if impact > 0.01:
            contributions.append({
                "name": "Висока унікальність ідеї",
                "impact": impact, "type": "positive",
                "text": f"✅ Висока унікальність: +{impact*100:.1f}% до шансів"
            })

    # Сортуємо за найбільшим впливом
    contributions.sort(key=lambda x: x["impact"], reverse=True)
    
    positives = [c["text"] for c in contributions if c["type"] == "positive"][:3]
    
    # Якщо немає сильних сторін, формуємо негативний фідбек
    negatives = []
    if base_ml_score < 0.2:
        negatives.append("❌ Відсутні ключові драйвери перемоги (спонсори, відео, унікальність).")

    return {
        "positive": positives,
        "negative": negatives
    }

if __name__ == "__main__":
    print("=== ТЕСТУВАННЯ XAI (EXPLAINABLE AI) ===")
    mock_feat = {
        "uses_sponsor_tech": 1, "has_video_demo": 1, "has_github": 1,
        "novelty_score": 0.85, "likes": 42, "team_size": 1, "sponsor_challenge_match": 1,
        "tech_count": 4, "description_length": 1500, "has_social_angle": 1,
        "competition_density": 2.0, "prize_numeric": 5000,
        "semantic_pca_1": 0.0, "semantic_pca_2": 0.0, "semantic_pca_3": 0.0, "github_stars": 15
    }
    base = predict_win_probability(mock_feat)
    explanation = explain_prediction(mock_feat, base)
    
    print(f"\nБазовий ML Score: {base*100:.2f}%")
    print("ЧОМУ ТАКИЙ БАЛ?")
    for p in explanation["positive"]: print(p)
    for n in explanation["negative"]: print(n)
