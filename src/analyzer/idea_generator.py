import sys
from pathlib import Path
import json

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.logger import logger
from src.analyzer.ai_client import generate_json_with_failover

def generate_winning_ideas(hackathon_data: dict, hackathon_analysis: dict, hard_constraints: dict) -> list[dict]:
    logger.info(f"AI-генерація ідей для хакатону: {hackathon_data.get('title', 'Unknown')}")
    
    constraints_text = json.dumps(hard_constraints, indent=2) if hard_constraints else "No strict rules specified."

    prompt = f"""
You are a serial hackathon winner and product strategist. Generate 3 distinct project ideas.

HACKATHON PROFILE:
{json.dumps(hackathon_data, ensure_ascii=False, indent=2)[:1000]}

🚨 HARD CONSTRAINTS (MANDATORY) 🚨
{constraints_text}

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
      "why_wins": "Why this hits criteria",
      "risk": "Main risk"
    }}
  ]
}}
"""
    result = generate_json_with_failover(prompt)
    
    # Якщо всі сервіси недоступні, гарантовано генеруємо 3 ідеї-заглушки для БД
    if "fallback" in result or "ideas" not in result:
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
        ] * 3  # Множимо на 3, щоб пайплайн мав достатньо ідей
        
    return result.get("ideas", [])
