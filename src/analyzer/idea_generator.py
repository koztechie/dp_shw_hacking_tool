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

    base_draft_prompt = prompt_manager.get_prompt(
        "idea_brainstormer", variables={"hackathon_data": json.dumps(hackathon_data, ensure_ascii=False)[:1000]}
    )
    draft_prompt = base_draft_prompt
    
    max_retries = 5
    is_unique = False
    draft_text = "Standard mobile apps with subscriptions."
    draft_result = {}
    success = False
    
    for attempt in range(max_retries):
        logger.info(f"💡 Генерація ідей (спроба {attempt + 1})...")
        draft_result = generate_json_with_failover(draft_prompt, thinking=True)
        
        response_time_ms = int((time.time() - start_time) * 1000)
        success = "error" not in draft_result and "fallback" not in draft_result
        prompt_manager.update_prompt_metrics("idea_brainstormer", success, response_time_ms)
        
        if not success:
            break
            
        draft_text = json.dumps(draft_result, indent=2)
        
        # 🔎 Live App Store Scrape for each idea to provide real context
        logger.info("🔎 Збір даних з реальних App Stores (Apple/Google)...")
        real_app_store_context = []
        try:
            from src.scraper.app_store_scraper import check_existing_apps
            
            draft_ideas_list = draft_result.get("draft_ideas", [])
            for idea in draft_ideas_list:
                title = idea.get("title", "")
                tagline = idea.get("tagline", "")
                
                if title:
                    # Search by title
                    results = check_existing_apps(title)
                    # Search by broader concept (first few words of tagline)
                    if tagline:
                        broad_query = " ".join(tagline.split()[:4])
                        results += check_existing_apps(broad_query)
                        
                    # deduplicate results by URL
                    unique_results = {r['url']: r for r in results if 'url' in r}.values()
                        
                    if unique_results:
                        real_app_store_context.append({"idea_title": title, "found_apps": list(unique_results)})
        except Exception as e:
            logger.error(f"Failed to scrape app stores: {e}")
            
        store_context_str = json.dumps(real_app_store_context, indent=2) if real_app_store_context else "No direct matches found in live store search, use your internal knowledge."
        
        # Uniqueness Check Agent
        logger.info("🔍 Перевірка ідей на унікальність...")
        uniqueness_prompt = prompt_manager.get_prompt(
            "idea_uniqueness_checker",
            variables={
                "draft_ideas": draft_text,
                "store_context": store_context_str,
                "threshold": 65,  # 65% similarity threshold
                "schema": json.dumps(PromptSchemaValidator.get_schema("idea_uniqueness_check"), indent=2)
            }
        )
        uniqueness_result = generate_json_with_failover(uniqueness_prompt, thinking=True, schema_name="idea_uniqueness_check")
        
        is_unique = uniqueness_result.get("is_unique", True)
        if is_unique:
            logger.info("✨ Згенеровані ідеї пройшли перевірку на унікальність!")
            break
            
        modification = uniqueness_result.get("prompt_modification", "")
        max_sim = uniqueness_result.get("max_similarity_percentage", 100)
        logger.warning(f"⚠️ Ідеї занадто схожі на існуючі (схожість {max_sim}%). Оновлюємо промпт...")
        
        if modification:
            # Accumulate rejected instructions
            draft_prompt += f"\n\n🚨 REJECTED ATTEMPT {attempt + 1} (Similarity: {max_sim}%). DO NOT REPEAT THIS: {modification}"

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
