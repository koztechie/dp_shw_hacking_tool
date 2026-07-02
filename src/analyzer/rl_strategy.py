import sys
from pathlib import Path
import random
import json

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.logger import logger

def epsilon_greedy_tech_selector(osint_data: dict, trends_data: dict, epsilon: float = 0.25) -> str:
    """
    Multi-Armed Bandit (Epsilon-Greedy):
    Обирає бонусну технологію для проекту.
    - Exploitation (1 - epsilon): Беремо перевірену технологію, що вигравала раніше.
    - Exploration (epsilon): Беремо ризиковану нову технологію з глобальних трендів.
    """
    explore = random.random() < epsilon
    
    if explore and trends_data:
        logger.info("🎰 Multi-Armed Bandit: EXPLORATION (додаємо новий тренд)")
        trends = trends_data.get("hacker_news_discussions", []) + trends_data.get("latest_arxiv_ai_papers", [])
        if trends:
            return random.choice(trends)
            
    logger.info("🎰 Multi-Armed Bandit: EXPLOITATION (використовуємо перевірений стек)")
    if osint_data and osint_data.get("top_winning_tags"):
        # Обираємо найпопулярнішу або другу за популярністю
        top_tags = list(osint_data["top_winning_tags"].keys())
        if top_tags:
            return random.choice(top_tags[:3])
            
    return "Docker" # Fallback

def optimize_timeline(tech_count: int, team_size: int) -> str:
    """
    Dynamic Bayesian Optimization Proxy:
    Розподіляє 48 годин на основі складності (кількості технологій) та робочих рук (команди).
    """
    base_sleep = 12 # 6 годин сну на ніч
    base_video = 4  # Запис відео та подача
    
    # Решта часу йде на кодінг та інтеграцію
    available_hours = (48 - base_sleep - base_video) * team_size
    
    # Якщо технологій багато, виділяємо більше часу на інтеграцію (hour_12_24)
    if tech_count >= 5:
        phase_1 = "15 hours (Heavy core implementation)"
        phase_2 = "12 hours (Complex API integrations)"
        phase_3 = f"{available_hours - 27} hours (Testing & Polish)"
    else:
        phase_1 = "10 hours (Rapid prototyping)"
        phase_2 = "10 hours (Feature completion)"
        phase_3 = f"{available_hours - 20} hours (Extensive UX Polish & Testing)"
        
    return f"Phase 1: {phase_1}, Phase 2: {phase_2}, Phase 3: {phase_3}, Sleep: {base_sleep}h, Video/Deploy: {base_video}h"

if __name__ == "__main__":
    print("=== ТЕСТУВАННЯ МУЛЬТИ-РУКОГО БАНДИТА ===")
    mock_osint = {"top_winning_tags": {"React": 10, "Python": 8, "AWS": 5}}
    mock_trends = {"hacker_news_discussions": ["Supabase Edge Functions", "Claude 3.5"]}
    
    # Проведемо 10 симуляцій
    explores = 0
    for i in range(10):
        tech = epsilon_greedy_tech_selector(mock_osint, mock_trends, epsilon=0.25)
        print(f"Спроба {i+1}: Обрана технологія -> {tech}")
        if tech in mock_trends["hacker_news_discussions"]: explores += 1
        
    print(f"\nСтатистика: Exploration={explores}/10, Exploitation={10-explores}/10")
    
    print("\n=== ТЕСТУВАННЯ ОПТИМІЗАЦІЇ ЧАСУ ===")
    print("Для соло-розробника зі складним стеком (6 технологій):")
    print(optimize_timeline(6, 1))
