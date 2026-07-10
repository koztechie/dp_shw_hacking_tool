import sys
from pathlib import Path

from bs4 import BeautifulSoup

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.analyzer.ai_client import generate_json_with_failover  # noqa: E402
from src.logger import logger  # noqa: E402
from src.scraper.http_client import safe_get  # noqa: E402


def fetch_and_clean_rules(rules_url: str) -> str:
    if not rules_url:
        return ""
    logger.info(f"Завантаження правил хакатону: {rules_url}")
    response = safe_get(rules_url)
    if not response or not response.text:
        return ""
    soup = BeautifulSoup(response.text, "lxml")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()
    rules_container = soup.select_one("#challenge-rules") or soup.body
    if not rules_container:
        return ""
    return rules_container.get_text(separator=" ", strip=True)[:15000]


def extract_hard_constraints_with_ai(rules_text: str) -> dict:
    if not rules_text or len(rules_text) < 100:
        return {}

    logger.info("AI-аналіз жорстких обмежень хакатону...")

    prompt = f"""
Analyze the following hackathon rules text and extract ONLY the hard constraints.
Rules text: {rules_text}
Return EXACTLY a JSON object matching this schema:
{{
  "max_team_size": 4,
  "must_use_apis_or_tech": [],
  "forbidden_tech": [],
  "eligibility_restrictions": "",
  "intellectual_property_rules": ""
}}
"""
    result = generate_json_with_failover(prompt, thinking=False, schema_name="hard_constraints")
    if "fallback" in result or "error" in result:
        return {}
    return result
