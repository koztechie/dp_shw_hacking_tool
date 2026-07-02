import sys
from pathlib import Path
import pickle
import pandas as pd
import numpy as np

PROJECT_ROOT = Path.cwd()
sys.path.insert(0, str(PROJECT_ROOT))

from src.ml.prepare_dataset import prepare_dataset

X_train, X_test, y_train, y_test = prepare_dataset()

with open('data/models/best_model.pkl', 'rb') as f:
    model = pickle.load(f)

# Let's inspect some real winners in X_test
test_df = pd.concat([X_test, y_test], axis=1)
winners = test_df[test_df['is_winner'] == 1]
print("=== REAL WINNERS IN TEST SET (TOP 3 BY PREDICTED PROBABILITY) ===")
test_probs = model.predict_proba(X_test)[:, 1]
X_test_with_probs = X_test.copy()
X_test_with_probs['prob'] = test_probs
X_test_with_probs['is_winner'] = y_test

top_winners = X_test_with_probs[X_test_with_probs['is_winner'] == 1].sort_values(by='prob', ascending=False)
print(top_winners.head(3).T)

print("\n=== STEP-BY-STEP WATERFALL DIAGNOSIS FOR OPTIMIZED_FEAT ===")
# Start from the mean of X_test (representing an average project)
current_feat = X_test.mean().to_dict()
base_prob = model.predict_proba(pd.DataFrame([current_feat]))[0][1]
print(f"Base (Average Project) Probability: {base_prob*100:.2f}%")

optimized_feat = {
    'uses_sponsor_tech': 1, 
    'tech_count': 5, 
    'has_social_angle': 1,
    'description_length': 400,        
    'has_github': 1, 
    'readme_length': 3500,            
    'commit_count_48h': 18,           
    'novelty_score': 0.85, 
    'sponsor_challenge_match': 1,     
    'has_video_demo': 1, 
    'competition_density': 2.0, 
    'prize_numeric': 5000,
    'semantic_pca_1': 0.05, 
    'semantic_pca_2': 0.02, 
    'semantic_pca_3': 0.01, 
    'github_stars': 15,
    'likes': 42, 
    'team_size': 1
}

# Change one feature at a time and see where the drop happens
temp_feat = current_feat.copy()
for key in X_test.columns:
    old_val = temp_feat[key]
    new_val = optimized_feat.get(key, 0)
    temp_feat[key] = new_val
    new_prob = model.predict_proba(pd.DataFrame([temp_feat]))[0][1]
    diff = new_prob - base_prob
    print(f"Change '{key}' from {old_val:.2f} to {new_val:.2f} -> Prob: {new_prob*100:.2f}% (Delta: {diff*100:+.2f}%)")
    base_prob = new_prob

