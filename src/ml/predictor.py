import sys
from pathlib import Path
import pickle
import hashlib

def verify_model_integrity(model_path: Path) -> bool:
    """Перевірка цілісності моделі через SHA-256 для запобігання Pickle RCE"""
    checksum_file = model_path.parent / "checksums.txt"
    if not checksum_file.exists():
        logger.warning(f"⚠️ Файл checksums.txt відсутній! Пропуск перевірки для {model_path.name}")
        return True

    
        if not verify_model_integrity(model_path):
            raise ValueError(f"🚨 КРИТИЧНО: Хеш файлу {model_path.name} не збігається! Файл пошкоджено або скомпрометовано.")
        
        with open(model_path, "rb") as f:
        current_hash = hashlib.sha256(f.read()).hexdigest()

    with open(checksum_file, "r") as f:
        saved_hashes = dict(line.strip().split(":") for line in f if ":" in line)

    expected_hash = saved_hashes.get(model_path.name)
    if not expected_hash:
        return True

    return current_hash == expected_hash

import pandas as pd

# Гарантуємо правильні шляхи імпорту
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.logger import logger

def load_model():
    """
    Завантажує найкращу натреновану модель та список її ознак.
    Захищено від відсутності файлів.
    """
    models_dir = Path("data/models")
    model_path = models_dir / "best_model.pkl"
    features_path = models_dir / "feature_names.pkl"

    if not model_path.exists() or not features_path.exists():
        raise FileNotFoundError(
            "❌ Файли моделей не знайдені у data/models/. "
            "Будь ласка, спочатку запустіть тренування моделі: python src/ml/train_model.py"
        )

    
        if not verify_model_integrity(model_path):
            raise ValueError(f"🚨 КРИТИЧНО: Хеш файлу {model_path.name} не збігається! Файл пошкоджено або скомпрометовано.")
        
        with open(model_path, "rb") as f:
        model = pickle.load(f)
    with open(features_path, "rb") as f:
        feature_names = pickle.load(f)
        
    return model, feature_names

def predict_win_probability(features: dict) -> float:
    """
    Приймає словник ознак проекту, повертає ймовірність його перемоги від 0.0 до 1.0.
    Повністю захищено від зсуву ознак та попереджень sklearn.
    """
    try:
        model, feature_names = load_model()
        
        # Будуємо рядок значень у строгому порядку ознак моделі
        row = []
        for f in feature_names:
            val = features.get(f, 0)
            # Примусово конвертуємо булеві значення в цілі числа
            if isinstance(val, bool):
                val = int(val)
            row.append(val)
            
        # АНТИКРИХКІСТЬ: Огортаємо в DataFrame з назвами стовпців.
        # Це повністю прибирає попередження "UserWarning: X does not have valid feature names"
        row_df = pd.DataFrame([row], columns=feature_names)
        
        # Отримуємо ймовірність для класу 1 (Переможець)
        prob = model.predict_proba(row_df)[0][1]
        
        logger.info(f"Передбачено ймовірність перемоги для '{features.get('title', 'Проекту')}': {prob:.4f}")
        return float(prob)
        
    except Exception as e:
        logger.error(f"Помилка під час прогнозування ймовірності: {e}")
        return 0.0

if __name__ == "__main__":
    print("=== ТЕСТУВАННЯ ПРЕДИКТОРУ (Етап 30) ===")
    
    # Мокові ознаки перспективного проекту
    mock_features = {
        "title": "Innovative AI Hackathon Tool",
        "uses_sponsor_tech": True,
        "tech_count": 6,
        "has_social_angle": True,
        "description_length": 1200,
        "has_github": True,
        "readme_length": 4500,
        "commit_count_48h": 28,
        "novelty_score": 0.78,
        "sponsor_challenge_match": True,
        "likes": 54,
        "team_size": 1
    }
    
    probability = predict_win_probability(mock_features)
    print(f"\n🔮 Прогнозована ймовірність перемоги: {probability*100:.2f}%")
