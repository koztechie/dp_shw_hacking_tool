import sys
from pathlib import Path
import json
import duckdb

# Гарантуємо правильні шляхи імпорту
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.logger import logger
from src.analyzer.ai_client import generate_json_with_failover
from config.settings import GEMINI_API_KEY, GEMINI_MODEL, DB_PATH

def _get_rag_context() -> str:
    """
    Lightweight RAG: Витягує 3 реальних проекти-переможці з нашої бази даних 
    для натхнення ШІ.
    """
    try:
        con = duckdb.connect(DB_PATH, read_only=True)
        # Беремо 3 успішні проекти з високою кількістю лайків як еталон
        winners = con.execute("""
            SELECT title, description, tech_tags, prize_track 
            FROM projects 
            WHERE is_winner = TRUE AND likes > 5
            ORDER BY RANDOM() LIMIT 3
        """).fetchdf().to_dict('records')
        con.close()
        
        if not winners:
            return "No historical context available."
            
        return json.dumps(winners, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.warning(f"RAG Retrieval failed: {e}")
        return "No historical context available."

def generate_winning_ideas(hackathon_data: dict, hackathon_analysis: dict, hard_constraints: dict) -> list[dict]:
    """
    Мульти-агентна генерація ідей: RAG -> Brainstorming (CoT + Global Trends) -> Adversarial Critic.
    """
    logger.info(f"🧠 Запуск Agentic AI для генерації ідей: {hackathon_data.get('title', 'Unknown')}")
    
    constraints_text = json.dumps(hard_constraints, indent=2) if hard_constraints else "No strict rules specified."
    rag_context = _get_rag_context()

    # Зчитування глобальних технологічних трендів (Hacker News, ArXiv)
    trends_file = Path("data/cache/global_trends.json")
    global_trends = ""
    if trends_file.exists():
        try:
            global_trends = trends_file.read_text(encoding="utf-8")
        except Exception:
            pass

    # ==========================================
    # АГЕНТ 1: CREATIVE BRAINSTORMER
    # ==========================================
    logger.info("Агент 1: Аналіз RAG-контексту та генерація пулу ідей...")
    draft_prompt = f"""
    You are an avant-garde product architect. Brainstorm 5 highly innovative project ideas for this hackathon.
    
    HACKATHON CONTEXT: {json.dumps(hackathon_data, ensure_ascii=False)[:1000]}
    
    CURRENT GLOBAL TECH TRENDS (Use for inspiration to make ideas cutting-edge):
    {global_trends}
    
    HISTORICAL SUCCESSFUL PROJECTS (For inspiration only, DO NOT COPY):
    {rag_context}
    
    Output a JSON with a single key "draft_ideas" containing a list of 5 ideas (just title and brief concept).
    """
    
    draft_result = generate_json_with_failover(draft_prompt)
    if "error" in draft_result or "fallback" in draft_result:
        logger.warning("Агент 1 (Brainstorm) недоступний. Використовуємо базовий фолбек.")
        draft_text = "Standard ideas around AI, health, and automation."
    else:
        draft_text = json.dumps(draft_result, indent=2)

    # ==========================================
    # АГЕНТ 2: ADVERSARIAL CRITIC & CONSTRAINT SOLVER
    # ==========================================
    logger.info("Агент 2: Робота Суворого Критика (фільтрація обмежень та фіналізація)...")
    critic_prompt = f"""
    You are an extremely strict Hackathon Judge and Technical Validator.
    Review these 5 draft ideas:
    {draft_text}
    
    🚨 HARD CONSTRAINTS (YOU MUST ENFORCE THESE):
    {constraints_text}
    
    YOUR TASKS:
    1. CRITIQUE: Discard any idea that violates "forbidden_tech" or fails to use "must_use_apis_or_tech".
    2. REFINE: Select the best 3 surviving ideas. Enhance them to perfectly match the hackathon's goals.
    3. SCOPE: Ensure the tech stack and solution are buildable within 48 hours.
    
    Return EXACTLY a JSON object matching this schema:
    {{
      "ideas": [
        {{
          "title": "Project name",
          "tagline": "1 sentence hook",
          "problem": "Problem it solves",
          "solution": "How it solves it",
          "killer_feature": "One unique feature to win",
          "sponsor_tech_used": ["technologies"],
          "tech_stack": ["technologies"],
          "target_track": "Prize track to apply for",
          "why_wins": "Why this passes your strict critique",
          "risk": "Main risk"
        }}
      ]
    }}
    """
    
    final_result = generate_json_with_failover(critic_prompt)
    
    # Офлайн-фолбек у разі повної відмови мережі
    if "fallback" in final_result or "ideas" not in final_result:
        logger.warning("Застосування детермінованого офлайн-генератора ідей...")
        return [
            {
                "title": f"Offline App Beta for {hackathon_data.get('title', 'Hackathon')}",
                "tagline": "A reliable local-first solution.",
                "problem": "Cloud AI services are currently offline.",
                "solution": "We built a robust local application.",
                "killer_feature": "Works completely offline",
                "sponsor_tech_used": [],
                "tech_stack": ["Python", "FastAPI"],
                "target_track": "General Track",
                "why_wins": "Demonstrates extreme engineering resilience.",
                "risk": "Lacks cloud features."
            }
        ] * 3
        
    return final_result.get("ideas", [])

if __name__ == "__main__":
    mock_data = {"title": "Web3 Future Hack"}
    mock_constraints = {
        "forbidden_tech": ["Python", "React"],
        "must_use_apis_or_tech": ["Rust", "Svelte"]
    }
    print("=== ТЕСТУВАННЯ MULTI-AGENT СИСТЕМИ (CoT + Critic + Global Trends) ===")
    ideas = generate_winning_ideas(mock_data, {}, mock_constraints)
    
    for i, idea in enumerate(ideas, 1):
        print(f"{i}. {idea.get('title')} (Стек: {', '.join(idea.get('tech_stack', []))})")
