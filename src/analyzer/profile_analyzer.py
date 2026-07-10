import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.analyzer.ai_client import generate_json_with_failover  # noqa: E402
from src.logger import logger  # noqa: E402


def analyze_hackathon_profile(hackathon_data: dict, osint: dict, banner_bytes: bytes = None) -> dict:
    """
    AI-аналіз профілю хакатону з інтеграцією OSINT та Vision-аналізом банера через Xiaomi MiMo.
    """
    logger.info("AI-аналіз профілю хакатону (MiMo)...")

    prompt = f"""
    You are an elite product analyst. Analyze the following hackathon data and background OSINT about the organizer.

    HACKATHON DATA:
    {json.dumps(hackathon_data, ensure_ascii=False, indent=2)}

    ORGANIZER OSINT:
    {json.dumps(osint, ensure_ascii=False, indent=2)}

    YOUR TASK:
    Analyze the themes, sponsors, and historical winning patterns.
    If a banner image is provided, inspect it for hidden sponsors or branding.
    Return EXACTLY a JSON object matching this schema:
    {{
        "themes": ["theme1", "theme2"],
        "participant_count": 100,
        "prize_total": "e.g., $50,000",
        "judging_criteria": "brief summary of how projects are judged",
        "sponsors": ["sponsor1", "sponsor2"]
    }}
    """
    # Маршрутизуємо через наш mimo-клієнт
    # Якщо є banner_bytes, клієнт автоматично задіє mimo-v2.5 (Vision)
    result = generate_json_with_failover(
        prompt,
        image_bytes=banner_bytes,
        thinking=False,
        schema_name="profile_analysis",
    )

    if "fallback" in result or "error" in result:
        logger.warning("Застосовано базовий офлайн-парсинг профілю.")
        return {
            "themes": hackathon_data.get("themes", ["Open Ended"]),
            "participant_count": int(hackathon_data.get("participant_count") or 100),
            "prize_total": hackathon_data.get("prize_total", "Unknown"),
            "judging_criteria": hackathon_data.get("judging_criteria", "Standard"),
            "sponsors": hackathon_data.get("sponsors", []),
        }

    return result
