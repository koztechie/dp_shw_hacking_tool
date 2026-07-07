import sys
from pathlib import Path
import json
import time
import duckdb

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.logger import logger
from src.analyzer.ai_client import generate_json_with_failover
from config.settings import DB_PATH

def generate_winning_ideas(hackathon_data: dict, hackathon_analysis: dict, hard_constraints: dict) -> list[dict]:
    logger.info(f"🧠 Запуск Agentic AI для генерації ідей...")
    constraints_text = json.dumps(hard_constraints, indent=2) if hard_constraints else "No strict rules specified."

    # Cache Buster
    cache_buster = str(time.time())

    # ==========================================
    # АГЕНТ 1: CREATIVE BRAINSTORMER (З УВІМКНЕНИМ DEEP THINKING)
    # ==========================================
    draft_prompt = f"""You are an elite product architect. Brainstorm 3 BRAND NEW, innovative project ideas. Cache Buster: {cache_buster}

CRITICAL RULES (OBEY OR FAIL):
1. PLATFORM CONSTRAINTS: The developer uses a weak AMD A4 CPU with 6GB RAM. If App Store publishing is required (like RevenueCat Shipaton), you MUST propose web-technologies wrapped with Capacitor or Expo targeting CLOUD BUILDS (EAS/Ionic Appflow). DO NOT propose Unity, React Native CLI, or pure PWA (PWA cannot be published to iOS App Store natively).
2. MONETIZATION: For RevenueCat, focus on subscriptions. NEVER use Web Billing SDKs for mobile apps; specify native plugins (e.g., @revenuecat/purchases-capacitor or expo-in-app-purchases).

Output a JSON with a single key "draft_ideas" containing a list of 3 ideas (just title and brief concept).
NEW HACKATHON TARGET: {json.dumps(hackathon_data, ensure_ascii=False)[:1000]}
"""
    
    # АНТИКРИХКІСТЬ: Вмикаємо thinking=True, щоб модель змогла осмислити обмеження!
    draft_result = generate_json_with_failover(draft_prompt, thinking=True)
    if "error" in draft_result or "fallback" in draft_result:
        draft_text = "Standard mobile apps with subscriptions."
    else:
        draft_text = json.dumps(draft_result, indent=2)

    # ==========================================
    # АГЕНТ 2: ADVERSARIAL CRITIC (З УВІМКНЕНИМ DEEP THINKING)
    # ==========================================
    critic_prompt = f"""You are an extremely strict Hackathon Judge. Cache Buster: {cache_buster}

YOUR TASKS:
1. HARDWARE & PLATFORM CHECK: Discard ANY idea containing Unity or pure PWA if App Store is required. Force Capacitor/Expo with Cloud Builds and NATIVE RevenueCat SDK.
2. THEME CHECK: Ensure the idea heavily uses the sponsor's tech (RevenueCat).
3. REFINE: Select the best 3 surviving ideas.

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
      "tech_stack": ["Expo or Capacitor", "Native RevenueCat SDK", "other light tech"],
      "target_track": "Prize track to apply for",
      "why_wins": "Why this passes your strict critique",
      "risk": "Main risk"
    }}
  ]
}}

🚨 HARD CONSTRAINTS: {constraints_text}
DRAFT IDEAS TO REVIEW: {draft_text}
"""
    
    # АНТИКРИХКІСТЬ: Вмикаємо thinking=True для суворого аудиту!
    final_result = generate_json_with_failover(critic_prompt, thinking=True)
    
    if "fallback" in final_result or "ideas" not in final_result:
        return [{"title": "Offline Web App", "tech_stack": ["HTML", "JS", "SQLite"]}] * 3
        
    return final_result.get("ideas", [])
