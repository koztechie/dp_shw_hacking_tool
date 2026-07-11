import sys
from pathlib import Path
import copy
import numpy as np
import pandas as pd
import warnings

# Вимикаємо настирливі попередження від shap та sklearn
warnings.filterwarnings("ignore")

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.logger import logger
from src.ml.predictor import predict_win_probability, load_model

try:
    import shap
    SHAP_AVAILABLE = True
except ImportError:
    SHAP_AVAILABLE = False
    logger.warning("SHAP не встановлено. Буде використано Feature Ablation.")

def _ablation_explain_prediction(features: dict, base_ml_score: float) -> dict:
    """Резервний метод пояснення (Feature Ablation) на випадок збою SHAP."""
    contributions = []
    positive_checks = [
        ("has_video_demo", 0, "Наявність відео-демо"),
        ("uses_sponsor_tech", 0, "Технології спонсора"),
        ("sponsor_challenge_match", 0, "Попадання в цільовий трек"),
        ("has_social_angle", 0, "Соціальна значущість"),
        ("has_github", 0, "Відкритий репозиторій")
    ]
    
    for feat_key, ablated_val, feat_name in positive_checks:
        if features.get(feat_key):
            cf_features = copy.deepcopy(features)
            cf_features[feat_key] = ablated_val
            ablated_score = predict_win_probability(cf_features)
            impact = base_ml_score - ablated_score
            if impact > 0.01:
                contributions.append({
                    "impact": impact, "type": "positive",
                    "text": f"✅ {feat_name}: +{impact*100:.1f}% до шансів"
                })

    if features.get("novelty_score", 0) > 0.7:
        cf_features = copy.deepcopy(features)
        cf_features["novelty_score"] = 0.5
        ablated_score = predict_win_probability(cf_features)
        impact = base_ml_score - ablated_score
        if impact > 0.01:
            contributions.append({
                "impact": impact, "type": "positive",
                "text": f"✅ Висока унікальність: +{impact*100:.1f}% до шансів"
            })

    contributions.sort(key=lambda x: x["impact"], reverse=True)
    positives = [c["text"] for c in contributions if c["type"] == "positive"][:3]
    negatives = []
    if base_ml_score < 0.2:
        negatives.append("❌ Відсутні ключові драйвери перемоги (спонсори, відео, унікальність).")

    return {"positive": positives, "negative": negatives}

def explain_prediction(features: dict, base_ml_score: float) -> dict:
    """
    Головний метод XAI. 
    Спроба 1: Використовує SHAP (просунута математика з теорії ігор).
    Спроба 2: Безшовний фолбек на Feature Ablation у разі збою.
    """
    if not SHAP_AVAILABLE:
        return _ablation_explain_prediction(features, base_ml_score)

    try:
        model, feature_names = load_model()
        
        # Вирівнюємо фічі за схемою моделі
        row = [features.get(f, 0) for f in feature_names]
        X_df = pd.DataFrame([row], columns=feature_names)
        
        # Створюємо базовий "нульовий" проект як бекграунд для KernelExplainer (оптимізація швидкості)
        background = pd.DataFrame([np.zeros(len(feature_names))], columns=feature_names)
        
        # Функція передбачення для SHAP
        def predict_fn(x):
            return model.predict_proba(x)[:, 1]

        # Використовуємо KernelExplainer (підтримує ансамблі та PyTorch). 
        explainer = shap.KernelExplainer(predict_fn, background)
        
        # Обчислюємо SHAP-значення (nsamples=100 гарантує високу швидкість)
        shap_vals = explainer.shap_values(X_df, nsamples=100, silent=True)
        
        # SHAP може повертати масив масивів залежно від версії, нормалізуємо
        if isinstance(shap_vals, list):
            shap_vals = shap_vals[0]
        if len(np.array(shap_vals).shape) > 1:
            shap_vals = shap_vals[0]

        # Збираємо пояснення
        contributions = []
        for feat_name, shap_val in zip(feature_names, shap_vals):
            if shap_val > 0.005:  # Більше 0.5% позитивного впливу
                contributions.append({"val": shap_val, "text": f"✅ {feat_name}: +{shap_val*100:.1f}% до шансів"})
            elif shap_val < -0.005: # Негативний вплив
                contributions.append({"val": shap_val, "text": f"🔻 {feat_name}: {shap_val*100:.1f}% зниження шансів"})

        positives = [c["text"] for c in sorted(contributions, key=lambda x: x["val"], reverse=True) if c["val"] > 0][:3]
        negatives = [c["text"] for c in sorted(contributions, key=lambda x: x["val"]) if c["val"] < 0][:2]

        # Фолбек на абляцію, якщо SHAP не знайшов сильних сигналів
        if not positives and base_ml_score > 0.1:
             return _ablation_explain_prediction(features, base_ml_score)

        return {"positive": positives, "negative": negatives}

    except Exception as e:
        logger.error(f"Збій SHAP Explainer (перехід на Ablation): {e}")
        return _ablation_explain_prediction(features, base_ml_score)

if __name__ == "__main__":
    print("=== ТЕСТУВАННЯ ГІБРИДНОГО XAI (SHAP + ABLATION) ===")
    mock_feat = {
        "uses_sponsor_tech": 1, "has_video_demo": 1, "has_github": 1,
        "novelty_score": 0.85, "likes": 42, "team_size": 1, "sponsor_challenge_match": 1,
        "tech_count": 4, "description_length": 150, "has_social_angle": 1,
        "competition_density": 0.02, "prize_numeric": 5000,
        "semantic_pca_1": 0.0, "semantic_pca_2": 0.0, "semantic_pca_3": 0.0, "github_stars": 15
    }
    
    base = predict_win_probability(mock_feat)
    print(f"Базовий ML Score: {base*100:.2f}%")
    
    explanation = explain_prediction(mock_feat, base)
    print("\nГотово. Тепер можу пояснити, чому кожна ідея має такі шанси:")
    for p in explanation["positive"]: print(p)
    for n in explanation["negative"]: print(n)
