import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.analyzer.ai_client import generate_json_with_failover  # noqa: E402
from src.analyzer.prompt_manager import prompt_manager  # noqa: E402
from src.analyzer.prompt_validator import PromptSchemaValidator  # noqa: E402
from src.logger import logger  # noqa: E402


def generate_winning_ideas(hackathon_data: dict, hackathon_analysis: dict, hard_constraints: dict) -> list[dict]:
    logger.info("🧠 Запуск Agentic AI для генерації ідей...")
    constraints_text = json.dumps(hard_constraints, indent=2) if hard_constraints else "No strict rules specified."

    # ==========================================
    # АГЕНТ 1: CREATIVE BRAINSTORMER
    # ==========================================
    start_time = time.time()

    draft_prompt = prompt_manager.get_prompt(
        "idea_brainstormer", variables={"hackathon_data": json.dumps(hackathon_data, ensure_ascii=False)[:1000]}
    )

    draft_result = generate_json_with_failover(draft_prompt, thinking=True)

    response_time_ms = int((time.time() - start_time) * 1000)
    success = "error" not in draft_result and "fallback" not in draft_result
    prompt_manager.update_prompt_metrics("idea_brainstormer", success, response_time_ms)

    draft_text = "Standard mobile apps with subscriptions." if not success else json.dumps(draft_result, indent=2)

    # ==========================================
    # АГЕНТ 2: ADVERSARIAL CRITIC
    # ==========================================
    start_time = time.time()

    critic_prompt = prompt_manager.get_prompt(
        "idea_critic",
        variables={
            "schema": json.dumps(PromptSchemaValidator.get_schema("idea_generation"), indent=2),
            "constraints": constraints_text,
            "draft_ideas": draft_text,
        },
    )

    final_result = generate_json_with_failover(critic_prompt, thinking=True, schema_name="idea_generation")

    response_time_ms = int((time.time() - start_time) * 1000)
    success = "fallback" not in final_result and "ideas" in final_result
    prompt_manager.update_prompt_metrics("idea_critic", success, response_time_ms)

    if not success:
        return [{"title": "Offline Web App", "tech_stack": ["HTML", "JS", "SQLite"]}] * 3

    return final_result.get("ideas", [])
