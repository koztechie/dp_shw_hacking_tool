import sys
from pathlib import Path
import json

PROJECT_ROOT = Path.cwd()
sys.path.insert(0, str(PROJECT_ROOT))

# Let's get the exact idea and hackathon data from the database for the failed run
import duckdb
from config.settings import DB_PATH

con = duckdb.connect(DB_PATH, read_only=True)
row = con.execute("""
    SELECT p.id, p.idea_1_description, h.sponsors, h.title, h.url
    FROM predictions p
    JOIN hackathons h ON p.hackathon_url = h.url
    ORDER BY p.generated_at DESC LIMIT 1
""").fetchone()
con.close()

if not row:
    print("❌ No data found.")
    sys.exit(1)

pred_id, idea_json, sponsors_raw, h_title, h_url = row
idea = json.loads(idea_json)
sponsors = json.loads(sponsors_raw) if sponsors_raw else []

print(f"Testing for Idea: {idea.get('title')}")
print(f"Hackathon: {h_title}")

from src.scraper.realtime_news import get_realtime_sponsor_news
realtime_news = get_realtime_sponsor_news(sponsors)

from src.analyzer.techspec_generator import generate_techspec
# Let's run it directly and print the raw response
from openai import OpenAI
from config.settings import MIMO_API_KEY, MIMO_BASE_URL
from datetime import datetime

client = OpenAI(api_key=MIMO_API_KEY, base_url=MIMO_BASE_URL)

sys_prompt = f"You are MiMo, an AI assistant developed by Xiaomi. Today's date: {datetime.now().strftime('%A, %B %d, %Y')}. Your knowledge cutoff date is December 2024.\nReturn JSON only, no explanations, no extra text."

from src.analyzer.techspec_generator import _draft_prompt # wait, we proved it doesn't exist.
# Let's reconstruct the exact prompt from techspec_generator.py:
prompt = f"""
You are a senior full-stack architect and serial hackathon winner. Generate a HIGHLY DETAILED technical specification for a 48-hour hackathon.

IDEA:
{json.dumps(idea, ensure_ascii=False, indent=2)}

HACKATHON CONTEXT:
Title: {h_title}
Time limit: 48 hours


🚨 RULES & CONSTRAINTS (MANDATORY):
None strict rules specified.

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

messages = [
    {"role": "system", "content": sys_prompt},
    {"role": "user", "content": prompt}
]

print("🚀 Sending live request to mimo-v2.5-pro...")
try:
    response = client.chat.completions.create(
        model="mimo-v2.5-pro",
        messages=messages,
        response_format={"type": "json_object"},
        temperature=1.0,
        max_completion_tokens=4096,
        extra_body={"thinking": {"type": "enabled"}}
    )
    raw = response.choices[0].message.content
    print("✅ Success!")
    print(f"Length: {len(raw)}")
    print(repr(raw[:200]))
    json.loads(raw)
    print("✅ Parsed successfully!")
except Exception as e:
    print(f"❌ Error: {e}")
    if 'raw' in locals():
        print("Raw response:")
        print(repr(raw))
