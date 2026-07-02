import sys
from pathlib import Path
import json

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.logger import logger
from src.analyzer.ai_client import generate_json_with_failover

def generate_techspec(idea: dict, hackathon_data: dict, hard_constraints: dict = None, realtime_news: str = "") -> dict:
    """Генерує детальне ТЗ з урахуванням жорстких правил та використовує failover-роутер."""
    logger.info(f"AI-генерація детального ТЗ для ідеї: {idea.get('title')}")

    constraints_text = json.dumps(hard_constraints, indent=2) if hard_constraints else "None strict rules specified."

    prompt = f"""
You are a senior full-stack architect and serial hackathon winner. Generate a HIGHLY DETAILED technical specification for a 48-hour hackathon.

IDEA:
{json.dumps(idea, ensure_ascii=False, indent=2)}

HACKATHON CONTEXT:
Title: {hackathon_data.get('title', 'Unknown')}
Time limit: 48 hours


🚨 RULES & CONSTRAINTS (MANDATORY):
{constraints_text}

🔥 REAL-TIME SPONSOR NEWS (Breaking news from today):
{realtime_news}

CRITICAL INSTRUCTIONS: 

1. Scope the MVP Timeline specifically for the "max_team_size" (assume 1 solo developer if null or unspecified).
2. Obey all "forbidden_tech" and "intellectual_property_rules" in architectural choices.

Return EXACTLY a JSON object matching this schema:
{{
  "project_name": "Final catchy name",
  "tagline": "Pitch in 10 words",
  "killer_feature": "The one specific feature that wins the hackathon",
  "architecture": {{
    "frontend": "technology + why",
    "backend": "technology + why",
    "database": "technology + why",
    "ai_integration": "how exactly AI is integrated",
    "deployment": "how to deploy within 5 minutes"
  }},
  "tech_stack": {{
    "must_have": ["core tech 1", "core tech 2"],
    "nice_to_have": ["bonus tech if time permits"],
    "avoid": ["tech to avoid and why"]
  }},
  "mvp_scope": {{
    "hour_0_4": "What to do in hours 0-4",
    "hour_4_12": "Hours 4-12",
    "hour_12_24": "Hours 12-24",
    "hour_24_36": "Hours 24-36",
    "hour_36_48": "Final polish, video recording, and submission"
  }},
  "ux_design": {{
    "color_palette": ["#hex1", "#hex2"],
    "typography": "font name",
    "key_screens": ["screen 1", "screen 2"],
    "wow_moment": "The specific moment the judge says WOW during the demo"
  }},
  "demo_script": "Step-by-step 60-second judging pitch script",
  "antifragile_features": ["what to do if API fails", "fallback plan if killer feature breaks"],
  "judging_alignment": {{
    "innovation": "how it hits innovation criteria",
    "technical": "what makes it technically impressive",
    "impact": "social or business impact",
    "presentation": "how to present it convincingly"
  }},
  "do_not": ["strict list of things to NOT do to save time"]
}}
"""
    result = generate_json_with_failover(prompt)

    # Захист від повної відмови всіх API
    if "fallback" in result or "project_name" not in result:
        logger.warning("Застосування детермінованої офлайн-заглушки для ТЗ...")
        return {
            "project_name": idea.get('title', 'Offline MVP'),
            "tagline": idea.get('tagline', 'A robust offline fallback solution.'),
            "killer_feature": idea.get('killer_feature', 'Works without external APIs.'),
            "architecture": {
                "frontend": "HTML/Vanilla JS - guaranteed to work",
                "backend": "Python/FastAPI or Node.js",
                "database": "SQLite - zero config",
                "ai_integration": "Mocked responses until AI APIs recover",
                "deployment": "Localhost or Vercel"
            },
            "tech_stack": {
                "must_have": ["Python", "SQLite"],
                "nice_to_have": [],
                "avoid": ["Complex microservices", "Heavy frameworks"]
            },
            "mvp_scope": {
                "hour_0_4": "Setup repo, DB schema, basic routing",
                "hour_4_12": "Core CRUD operations",
                "hour_12_24": "UI layout and integration",
                "hour_24_36": "Refinement and mock AI integration",
                "hour_36_48": "Record demo and write Devpost submission"
            },
            "ux_design": {
                "color_palette": ["#000000", "#FFFFFF"],
                "typography": "System UI",
                "key_screens": ["Dashboard"],
                "wow_moment": "It actually runs smoothly."
            },
            "demo_script": "Start with the problem, show the working local MVP, explain the architecture.",
            "antifragile_features": ["Zero external dependencies for demo"],
            "judging_alignment": {
                "innovation": "Proves resilience",
                "technical": "Clean architecture",
                "impact": "Reliable",
                "presentation": "Focus on code quality"
            },
            "do_not": ["Do not rely on cloud services today."]
        }

    return result

if __name__ == "__main__":
    # Тест генератора ТЗ
    mock_idea = {
        "title": "HealthSync AI",
        "tagline": "Unifying patient data with GenAI",
        "problem": "Fragmented health records",
        "solution": "A central dashboard that summarizes patient history using LLMs.",
        "killer_feature": "One-click timeline generation",
        "tech_stack": ["Python", "FastAPI", "React", "OpenAI"]
    }
    mock_hackathon = {"title": "Healthcare Future 2026"}
    mock_constraints = {"max_team_size": 2, "forbidden_tech": ["PHP"]}
    
    print("🔄 Запускаємо генератор TechSpec через каскадний роутер...")
    techspec = generate_techspec(mock_idea, mock_hackathon, mock_constraints)
    
    print(f"\n📋 ЗГЕНЕРОВАНЕ ТЗ ДЛЯ '{techspec.get('project_name')}':")
    print(json.dumps(techspec, indent=2, ensure_ascii=False))
