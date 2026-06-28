import sys
from pathlib import Path
import json
import os
import httpx

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.logger import logger
from config.settings import GEMINI_API_KEY, GEMINI_MODEL

# Зчитуємо альтернативні безкоштовні ключі з оточення
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

def generate_json_with_failover(prompt: str) -> dict:
    """
    Каскадний маршрутизатор генерації JSON:
    Спроба 1: Gemini (Основна модель, наприклад gemini-2.5-flash)
    Спроба 2: Gemini (Резервна модель на іншому серверному ендпоінті, наприклад gemini-1.5-pro)
    Спроба 3: OpenRouter (Найкращі безкоштовні моделі: qwen3-coder:free або llama-3.1-8b)
    Спроба 4: Розумний офлайн-фолбек
    """
    
    # --- СПРОБА 1: Google Gemini (Основна модель) ---
    if GEMINI_API_KEY and GEMINI_API_KEY != "your_key_here":
        try:
            logger.info(f"ШІ-Маршрутизатор [Спроба 1]: Виклик Gemini API ({GEMINI_MODEL})...")
            from google import genai
            from google.genai import types
            
            client = genai.Client(api_key=GEMINI_API_KEY)
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.3
                )
            )
            return json.loads(response.text.strip())
        except Exception as e:
            logger.warning(f"⚠️ Основна модель Gemini ({GEMINI_MODEL}) перевантажена або недоступна: {e}")

    # --- СПРОБА 2: Google Gemini (Резервна модель Pro для обходу квот) ---
    if GEMINI_API_KEY and GEMINI_API_KEY != "your_key_here":
        # Спробуємо переключитися на PRO версію (вона хоститься на окремих кластерах)
        fallback_model = "gemini-1.5-pro" if GEMINI_MODEL != "gemini-1.5-pro" else "gemini-1.5-flash"
        try:
            logger.info(f"ШІ-Маршрутизатор [Спроба 2]: Переключення на альтернативну модель ({fallback_model})...")
            from google import genai
            from google.genai import types
            
            client = genai.Client(api_key=GEMINI_API_KEY)
            response = client.models.generate_content(
                model=fallback_model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.3
                )
            )
            return json.loads(response.text.strip())
        except Exception as e:
            logger.warning(f"⚠️ Резервна модель Gemini ({fallback_model}) також недоступна: {e}")

    # --- СПРОБА 3: OpenRouter API (Повністю безкоштовні відкриті моделі) ---
    if OPENROUTER_API_KEY and OPENROUTER_API_KEY != "your_key_here":
        # Спробуємо три безкоштовні моделі по черзі для повної стійкості
        openrouter_models = [
            "qwen/qwen3-coder:free",                  # Надійна та розумна модель кодування 2026 року
            "meta-llama/llama-3.1-8b-instruct:free",  # Перевірений стандарт
            "google/gemma-3-27b-it:free"              # Легка та швидка модель
        ]
        
        for model_name in openrouter_models:
            try:
                logger.info(f"ШІ-Маршрутизатор [Спроба 3]: Виклик OpenRouter ({model_name})...")
                headers = {
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json"
                }
                payload = {
                    "model": model_name,
                    "messages": [
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.3
                }
                r = httpx.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload, timeout=25.0)
                if r.status_code == 200:
                    result_text = r.json()["choices"][0]["message"]["content"].strip()
                    
                    # Захист від маркдауну в безкоштовних моделях OpenRouter
                    if "```json" in result_text:
                        result_text = result_text.split("```json")[1].split("```")[0].strip()
                    elif "```" in result_text:
                        result_text = result_text.split("```")[1].split("```")[0].strip()
                        
                    return json.loads(result_text)
                else:
                    logger.warning(f"⚠️ OpenRouter ({model_name}) повернув статус {r.status_code}: {r.text}")
            except Exception as e:
                logger.warning(f"⚠️ Збій підключення до OpenRouter ({model_name}): {e}")

    # --- СПРОБА 4: Розумний офлайн-фолбек ---
    logger.error("❌ Усі безкоштовні ШІ-провайдери недоступні! Запуск локального алгоритму.")
    return {
        "error": "All AI providers failed",
        "fallback": True
    }
