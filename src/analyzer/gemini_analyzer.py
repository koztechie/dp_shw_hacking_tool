import sys
from pathlib import Path
import json

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.logger import logger
from src.analyzer.ai_client import generate_json_with_failover

def analyze_hackathon_with_gemini(hackathon_data: dict, osint_data: dict) -> dict:
    logger.info(f"AI-аналіз профілю хакатону: {hackathon_data.get('title', 'Unknown')}")
    
    sponsors = ", ".join(hackathon_data.get('sponsors', []))
    themes = ", ".join(hackathon_data.get('themes', []))
    criteria = str(hackathon_data.get('judging_criteria', ''))[:1000]
    prizes = str(hackathon_data.get('prizes_detail', ''))[:500]
    about = str(hackathon_data.get('about', ''))[:1000]
    osint_text = json.dumps(osint_data, ensure_ascii=False)[:1000] if osint_data else "No previous data."

    prompt = f"""
You are a hackathon analyst with 10 years of experience. Analyze this hackathon and provide a structured strategic profile.

HACKATHON DATA:
Title: {hackathon_data.get('title')}
Sponsors: {sponsors}
Themes: {themes}
Judging Criteria: {criteria}
Prize Pool / Details: {prizes}
About: {about}
OSINT DATA:
{osint_text}

Return the analysis STRICTLY as a JSON object matching exactly this schema:
{{
  "hidden_objective": "1 sentence describing the organizer's true goal",
  "sponsor_tech_priority": ["sponsor tech"],
  "winning_formula": "formula for winning",
  "avoid": ["things to avoid"],
  "ideal_problem_domain": "Problem area",
  "complexity_sweet_spot": "Technical complexity",
  "judge_profile": "Judge profile",
  "trend_alignment": ["trends"]
}}
"""
    result = generate_json_with_failover(prompt)
    
    # Абсолютна антикрихкість: якщо всі моделі світу впадуть, ми не зламаємо пайплайн
    if "fallback" in result or "error" in result:
        logger.warning("Застосування детермінованого офлайн-аналізу...")
        return {
            "hidden_objective": "Build a working prototype integrating sponsor APIs.",
            "sponsor_tech_priority": hackathon_data.get('sponsors', []),
            "winning_formula": "Clean UI + Working Sponsor API integration + Solves real problem.",
            "avoid": ["Broken demos", "Overcomplicated architectures"],
            "ideal_problem_domain": hackathon_data.get('themes', ["General"])[0] if hackathon_data.get('themes') else "General",
            "complexity_sweet_spot": "MVP with 1-2 core features working perfectly",
            "judge_profile": "Industry professionals looking for real-world application",
            "trend_alignment": ["Automation", "Efficiency"]
        }
        
    return result
