import sys
from pathlib import Path
import pickle
import pandas as pd
import json

PROJECT_ROOT = Path.cwd()
sys.path.insert(0, str(PROJECT_ROOT))

from src.ml.predictor import predict_win_probability
from src.analyzer.xai_explainer import explain_prediction

# Mathematically optimized features based on the real winners in the database!
perfect_feat = {
    'uses_sponsor_tech': 0, 
    'tech_count': 15,                 # Оптика переможців (11-32)
    'has_social_angle': 0,
    'description_length': 150,        # Оптика переможців (короткі описи)
    'has_github': 1, 
    'readme_length': 6000,            # Оптика переможців (багатий README)
    'commit_count_48h': 20,           # Оптика переможців (активна розробка)
    'novelty_score': 0.97,            # Оптика переможців (0.97-0.99)
    'sponsor_challenge_match': 0,     
    'has_video_demo': 0, 
    'competition_density': 0.02,      # КЛЮЧОВИЙ ФІКС: 0.02 замість 2.0 (позбавляє від -50.78% штрафу)
    'prize_numeric': 0,
    'semantic_pca_1': 0.15, 
    'semantic_pca_2': 0.10, 
    'semantic_pca_3': 0.10, 
    'github_stars': 0,
    'likes': 3,                       # Оптика переможців (1-4 лайки)
    'team_size': 1
}

base = predict_win_probability(perfect_feat)
print('=== ОПТИМАЛЬНИЙ ТЕСТ (МАТЕМАТИЧНА ТОЧНІСТЬ) ===')
print(f'Прогнозована ймовірність перемоги: {base*100:.2f}%')

explanation = explain_prediction(perfect_feat, base)
print('\nЧОМУ ТАКИЙ БАЛ (XAI):')
for p in explanation['positive']: print(p)
for n in explanation['negative']: print(n)
