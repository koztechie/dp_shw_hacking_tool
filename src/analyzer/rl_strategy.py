import sys
from pathlib import Path
import json
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.logger import logger

def thompson_sampling_tech_selector(osint_data: dict, trends_data: dict) -> str:
    """
    Contextual Thompson Sampling (Bayesian Bandit):
    Динамічно обирає технологію, балансуючи між відомим успіхом (Exploitation)
    та інноваціями (Exploration) за допомогою Бета-розподілу.
    Безстанова антикрихка реалізація: стан підтягується прямо з DuckDB OSINT.
    """
    winning_tags = osint_data.get("top_winning_tags", {}) if osint_data else {}
    losing_tags = osint_data.get("top_losing_tags", {}) if osint_data else {}
    
    trends = []
    if trends_data:
        trends.extend(trends_data.get("hacker_news_discussions", []))
        trends.extend(trends_data.get("latest_arxiv_ai_papers", []))

    # Збираємо всіх кандидатів
    candidates = set(list(winning_tags.keys()) + list(losing_tags.keys()) + trends)
    
    if not candidates:
        return "Docker"

    best_tech = "Docker"
    best_score = -1.0

    for tech in candidates:
        # Апріорні знання (Prior)
        alpha = 1.0
        beta = 1.0
        
        # Апостеріорні знання (Posterior evidence з бази даних)
        alpha = max(1.0, alpha + winning_tags.get(tech, 0))
        beta = max(1.0, beta + losing_tags.get(tech, 0))
        
        # Симулюємо значення Бета-розподілу
        try:
            score = np.random.beta(alpha, beta)
        except Exception:
            score = 0.0
            
        if score > best_score:
            best_score = score
            best_tech = tech
            
    # Визначаємо, чи ми ризикнули, чи взяли перевірене
    if best_tech in trends and best_tech not in winning_tags:
        logger.info(f"🎰 Thompson Sampling: EXPLORATION (Ризикнули з новим трендом: {best_tech})")
    else:
        logger.info(f"🎰 Thompson Sampling: EXPLOITATION (Обрано перевірений стек: {best_tech})")

    return best_tech

def optimize_timeline(tech_count: int, team_size: int) -> str:
    """Динамічний розподіл часу."""
    base_sleep = 12
    base_video = 4
    available_hours = (48 - base_sleep - base_video) * team_size
    
    if tech_count >= 5:
        phase_1 = "15 hours (Heavy core implementation)"
        phase_2 = "12 hours (Complex API integrations)"
        phase_3 = f"{max(available_hours - 27, 2)} hours (Testing & Polish)"
    else:
        phase_1 = "10 hours (Rapid prototyping)"
        phase_2 = "10 hours (Feature completion)"
        phase_3 = f"{max(available_hours - 20, 2)} hours (Extensive UX Polish & Testing)"
        
    return f"Phase 1: {phase_1}, Phase 2: {phase_2}, Phase 3: {phase_3}, Sleep: {base_sleep}h, Video/Deploy: {base_video}h"

if __name__ == "__main__":
    print("=== ТЕСТУВАННЯ THOMPSON SAMPLING ===")
    # Мок-дані: React часто виграє, але й часто програє (high alpha, high beta)
    # Python тільки виграє (high alpha, low beta)
    mock_osint = {
        "top_winning_tags": {"React": 15, "Python": 10},
        "top_losing_tags": {"React": 20, "Python": 1}
    }
    mock_trends = {"hacker_news_discussions": ["Supabase Edge Functions"]}
    
    counts = {"React": 0, "Python": 0, "Supabase Edge Functions": 0}
    for _ in range(100):
        t = thompson_sampling_tech_selector(mock_osint, mock_trends)
        counts[t] = counts.get(t, 0) + 1
        
    print("Результати 100 симуляцій (вибір технології):")
    for k, v in counts.items():
        print(f"{k}: {v}% виборів")
