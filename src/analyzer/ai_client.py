import sys
from pathlib import Path
import json
import os
import httpx
import re

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.logger import logger
from config.settings import GEMINI_API_KEY, GEMINI_MODEL
from src.analyzer.rate_limiter import check_and_increment

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

def generate_json_with_failover(prompt: str, image_bytes: bytes = None) -> dict:
    """
    Каскадний маршрутизатор генерації JSON:
    Спроба 1: Gemini 3.5 (Основна модель gemini-3.5-flash) з підтримкою Vision.
    Спроба 2: Gemini 2.5 Pro (Резервна модель gemini-2.5-pro) з підтримкою Vision.
    Спроба 3: OpenRouter API з каскадом безкоштовних моделей 2026 року.
    Спроба 4: Розумний офлайн-фолбек.
    """
    
    # --- СПРОБА 1: Google Gemini (Основна модель 3.5) ---
    if GEMINI_API_KEY and GEMINI_API_KEY != "your_key_here" and check_and_increment():
        try:
            logger.info(f"ШІ-Маршрутизатор [Спроба 1]: Виклик Gemini API ({GEMINI_MODEL})...")
            from google import genai
            from google.genai import types
            
            client = genai.Client(api_key=GEMINI_API_KEY)
            contents_list = [types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"), prompt] if image_bytes else prompt
            
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=contents_list,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.3
                )
            )
            return json.loads(response.text.strip())
        except Exception as e:
            logger.warning(f"⚠️ Модель Gemini ({GEMINI_MODEL}) недоступна або повернула невалідний JSON: {e}")

    # --- СПРОБА 2: Google Gemini (Альтернативна модель Pro) ---
    if GEMINI_API_KEY and GEMINI_API_KEY != "your_key_here" and check_and_increment():
        fallback_model = "gemini-2.5-pro" if GEMINI_MODEL != "gemini-2.5-pro" else "gemini-3.5-flash"
        try:
            logger.info(f"ШІ-Маршрутизатор [Спроба 2]: Переключення на резервну модель ({fallback_model})...")
            from google import genai
            from google.genai import types
            
            client = genai.Client(api_key=GEMINI_API_KEY)
            contents_list = [types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"), prompt] if image_bytes else prompt
            
            response = client.models.generate_content(
                model=fallback_model,
                contents=contents_list,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.3
                )
            )
            return json.loads(response.text.strip())
        except BaseException as e:
            logger.warning(f"⚠️ Резервна модель Gemini ({fallback_model}) також недоступна: {e}. Перехід до OpenRouter...")

    # --- СПРОБА 3: OpenRouter API (Каскад новітніх безкоштовних моделей 2026 року) ---
    if OPENROUTER_API_KEY and OPENROUTER_API_KEY != "your_key_here":
        # Спроба послідовного зчитування кращих безкоштовних моделей
        openrouter_models = [
            "qwen/qwen3-coder:free",                         # Qwen3 Coder (480B A35B) - еталон для коду та ТЗ
            "google/gemma-4-26b-a4b-it:free",               # Gemma 4 (26B MoE) - Gemini-рівень безкоштовно
            "poolside/laguna-xs-2.1:free",                   # Poolside Laguna 2.1 - спеціалізований кодинг-агент
            "meta-llama/llama-3.3-70b-instruct:free",       # Llama 3.3 70B - лідер загальних міркувань
            "openai/gpt-oss-20b:free",                       # gpt-oss-20b - швидкі структуровані виводи
            "meta-llama/llama-3.2-3b-instruct:free"         # Llama 3.2 3B - надшвидкий резерв
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
                    "temperature": 0.3,
                    "response_format": {"type": "json_object"}  # Примусовий JSON Mode
                }
                r = httpx.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload, timeout=35.0)
                if r.status_code == 200:
                    result_text = r.json()["choices"][0]["message"]["content"].strip()
                    
                    # Очищення тегів міркувань (DeepSeek R1, Nemotron та ін.)
                    result_text = re.sub(r'<think>.*?</think>', '', result_text, flags=re.DOTALL).strip()
                    
                    # Вирізання markdown
                    if "```json" in result_text:
                        result_text = result_text.split("```json")[1].split("```")[0].strip()
                    elif "```" in result_text:
                        result_text = result_text.split("```")[1].split("```")[0].strip()
                        
                    # Надійна ізоляція безпосередньо структури JSON
                    start_idx = result_text.find('{')
                    end_idx = result_text.rfind('}')
                    if start_idx != -1 and end_idx != -1:
                        result_text = result_text[start_idx:end_idx+1]
                        
                    return json.loads(result_text)
                else:
                    logger.warning(f"⚠️ OpenRouter ({model_name}) повернув статус {r.status_code}: {r.text}")
            except Exception as e:
                logger.warning(f"⚠️ Збій підключення або парсингу OpenRouter ({model_name}): {e}")

    # --- СПРОБА 4: Розумний офлайн-фолбек ---
    logger.error("❌ Усі безкоштовні ШІ-провайдери недоступні або повернули некоректні дані! Запуск локального алгоритму.")
    return {
        "error": "All AI providers failed",
        "fallback": True
    }
