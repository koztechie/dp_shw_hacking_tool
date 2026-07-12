import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.analyzer.ai_client import generate_json_with_failover  # noqa: E402
from src.analyzer.context_manager import context_manager  # noqa: E402
from src.analyzer.prompt_validator import PromptSchemaValidator  # noqa: E402
from src.logger import logger  # noqa: E402


def generate_techspec(idea: dict, hackathon_data: dict, hard_constraints: dict = None, realtime_news: str = "") -> dict:
    """Генерує детальне ТЗ з урахуванням жорстких правил та використовує failover-роутер."""
    logger.info(f"AI-генерація детального ТЗ для ідеї: {idea.get('title')}")

    constraints_text = json.dumps(hard_constraints, indent=2) if hard_constraints else "None strict rules specified."

    from src.analyzer.prompt_manager import prompt_manager
    prompt_template = prompt_manager.get_prompt("techspec_generator")

    # Змінні для підстановки
    variables = {
        "idea_json": json.dumps(idea, ensure_ascii=False, indent=2),
        "hackathon_title": hackathon_data.get("title", "Unknown"),
        "hardware_constraints": """The developer uses a weak dual-core AMD A4 with 6GB RAM. Local compilation via Android Studio/Xcode will crash the PC.
1. IF MOBILE STORES (App Store/Google Play) ARE REQUIRED: Use Capacitor or Expo with CLOUD BUILDS (EAS/Appflow) for final builds.
2. LIGHTWEIGHT ADB DEBUGGING: Instruct the developer to install ONLY the lightweight Android SDK CLI (Command Line Tools) and ADB. Force them to run and debug the app directly on a physical Android device connected via USB (`npx cap run android`), completely bypassing the heavy Android Studio IDE to save RAM (uses <150MB).
3. APP STORE COMPLIANCE: Ensure MVP is functional before submission. Do NOT use empty skeleton apps.
4. MONETIZATION: Specify native plugins (e.g., `@revenuecat/purchases-capacitor`). Never use Web Billing SDKs inside mobile stores.
5. NO local Docker. Use Supabase.""",
        "constraints_text": constraints_text,
        "realtime_news": realtime_news,
        "schema_json": json.dumps(PromptSchemaValidator.get_schema("techspec"), indent=2),
    }

    # КРИТИЧНИЙ ФІКС: Обрізаємо промпт, щоб вмістити в контекстне вікно
    final_prompt, truncated_vars = context_manager.truncate_to_fit(prompt_template, variables)

    result = generate_json_with_failover(final_prompt, schema_name="techspec")

    # Захист від повної відмови всіх API
    if "fallback" in result or "project_name" not in result:
        logger.warning("Застосування детермінованої офлайн-заглушки для ТЗ...")
        return {
            "project_name": idea.get("title", "Offline MVP"),
            "tagline": idea.get("tagline", "A robust offline fallback solution."),
            "killer_feature": idea.get("killer_feature", "Works without external APIs."),
            "architecture": {
                "frontend": "HTML/Vanilla JS - guaranteed to work",
                "backend": "Python/FastAPI or Node.js",
                "database": "SQLite - zero config",
                "ai_integration": "Mocked responses until AI APIs recover",
                "deployment": "Localhost or Vercel",
            },
            "tech_stack": {
                "must_have": ["Python", "SQLite"],
                "nice_to_have": [],
                "avoid": ["Complex microservices", "Heavy frameworks"],
            },
            "timeline_plan": {
                "phase_1_setup": "Setup repo, DB schema, basic routing",
                "phase_2_core": "Core CRUD operations",
                "phase_3_integration": "UI layout and integration",
                "phase_4_polish": "Refinement and mock AI integration",
                "phase_5_submission": "Record demo and write Devpost submission",
            },
            "ux_design": {
                "color_palette": ["#000000", "#FFFFFF"],
                "typography": "System UI",
                "key_screens": ["Dashboard"],
                "wow_moment": "It actually runs smoothly.",
            },
            "demo_script": "Start with the problem, show the working local MVP, explain the architecture.",
            "antifragile_features": ["Zero external dependencies for demo"],
            "judging_alignment": {
                "innovation": "Proves resilience",
                "technical": "Clean architecture",
                "impact": "Reliable",
                "presentation": "Focus on code quality",
            },
            "do_not": ["Do not rely on cloud services today."],
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
        "tech_stack": ["Python", "FastAPI", "React", "OpenAI"],
    }
    mock_hackathon = {"title": "Healthcare Future 2026"}
    mock_constraints = {"max_team_size": 2, "forbidden_tech": ["PHP"]}

    print("🔄 Запускаємо генератор TechSpec через каскадний роутер...")
    techspec = generate_techspec(mock_idea, mock_hackathon, mock_constraints)

    print(f"\n📋 ЗГЕНЕРОВАНЕ ТЗ ДЛЯ '{techspec.get('project_name')}':")
    print(json.dumps(techspec, indent=2, ensure_ascii=False))
