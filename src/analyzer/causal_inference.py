import sys
from pathlib import Path
import copy


from src.ml.predictor import predict_win_probability

def get_counterfactual_advice(features: dict, base_ml_score: float) -> list:
    """
    Counterfactual Analysis: оцінює вплив конкретних рішень на результат (Causal Effect).
    Використовує математично стійкий ВІДНОСНИЙ приріст для збалансування шкал.
    """
    advice = []
    
    base_ml_score = max(base_ml_score, 0.01)  # Захист від математичного вибуху

    treatments = [
        ("uses_sponsor_tech", "використання технології спонсора"),
        ("has_video_demo", "відео-презентації (YouTube/Loom)"),
        ("has_github", "відкритого репозиторію GitHub")
    ]

    for feat_key, feat_name in treatments:
        current_val = features.get(feat_key, 0)
        
        if not current_val:
            cf_features = copy.deepcopy(features)
            cf_features[feat_key] = 1
            
            cf_score = predict_win_probability(cf_features)
            
            delta_abs = cf_score - base_ml_score
            # Обчислюємо відносний приріст шансів
            delta_rel = delta_abs / base_ml_score
            
            # Якщо рішення дає понад 10% ВІДНОСНОГО приросту, фіксуємо інсайт
            if delta_rel > 0.10:
                advice.append(
                    f"📈 Causal Insight: Додавання {feat_name} підвищить відносний шанс перемоги на "
                    f"+{delta_rel * 100:.1f}% (абсолютний приріст: +{delta_abs * 100:.2f}%)"
                )
                
    return advice

if __name__ == "__main__":
    print("=== ТЕСТУВАННЯ CAUSAL INFERENCE ===")
    mock_feat = {
        "uses_sponsor_tech": 0, "has_video_demo": 0, "has_github": 0,
        "novelty_score": 0.8, "likes": 0, "team_size": 1, "sponsor_challenge_match": 0
    }
    base = predict_win_probability(mock_feat)
    print(f"Базовий ML Score: {base*100:.2f}%")
    
    advices = get_counterfactual_advice(mock_feat, base)
    for adv in advices:
        print(adv)
