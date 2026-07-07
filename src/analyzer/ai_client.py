import sys
from pathlib import Path
import json
import base64
from datetime import datetime
import re

# Гарантуємо правильні шляхи імпорту
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.logger import logger
from config.settings import MIMO_API_KEY, MIMO_BASE_URL
from src.analyzer.rate_limiter import check_and_increment

from openai import OpenAI, RateLimitError, APIStatusError, APIConnectionError, APIError

try:
    client = OpenAI(
        api_key=MIMO_API_KEY,
        base_url=MIMO_BASE_URL
    )
except Exception as e:
    logger.warning(f"Не вдалося ініціалізувати OpenAI клієнт: {e}")
    client = None

def _get_image_mime_type(image_bytes: bytes) -> str:
    if image_bytes.startswith(b'\x89PNG\r\n\x1a\n'): return "image/png"
    elif image_bytes.startswith(b'\xff\xd8\xff'): return "image/jpeg"
    elif image_bytes.startswith(b'GIF87a') or image_bytes.startswith(b'GIF89a'): return "image/gif"
    elif image_bytes.startswith(b'RIFF') and image_bytes[8:12] == b'WEBP': return "image/webp"
    return "image/jpeg"

def generate_json_with_failover(prompt: str, image_bytes: bytes = None, thinking: bool = True) -> dict:
    if not client or not MIMO_API_KEY or MIMO_API_KEY == "your_key_here":
        return {"error": "API Key missing", "fallback": True}

    if not check_and_increment():
        return {"error": "Local rate limit exceeded", "fallback": True}

    try:
        sys_prompt = f"You are MiMo, an AI assistant developed by Xiaomi. Today's date: {datetime.now().strftime('%A, %B %d, %Y')}. Your knowledge cutoff date is December 2024.\nReturn JSON only, no explanations, no extra text."
        
        if image_bytes:
            target_model = "mimo-v2.5"
            logger.info(f"ШІ-Клієнт: Виявлено зображення. Маршрутизація на Vision-модель ({target_model})...")
            mime_type = _get_image_mime_type(image_bytes)
            b64_img = base64.b64encode(image_bytes).decode('utf-8')
            user_content = [
                {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{b64_img}"}},
                {"type": "text", "text": prompt}
            ]
        else:
            target_model = "mimo-v2.5-pro"
            logger.info(f"ШІ-Клієнт: Текстовий запит. Маршрутизація на флагман ({target_model})...")
            user_content = prompt

        messages = [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_content}
        ]

        # АНТИКРИХКІСТЬ: Додано timeout=120.0 для запобігання 30-секундним обривам довгих відповідей!
        response = client.chat.completions.create(
            model=target_model,
            messages=messages,
            response_format={"type": "json_object"},
            temperature=1.0 if thinking else 0.3,
            max_completion_tokens=16384, 
            timeout=120.0,
            extra_body={"thinking": {"type": "enabled" if thinking else "disabled"}}
        )
        
        result_text = response.choices[0].message.content
        
        if not result_text or not result_text.strip():
            finish_reason = response.choices[0].finish_reason
            raise ValueError(f"Сервер повернув порожній результат. Причина: {finish_reason}")

        # АНТИКРИХКІСТЬ: Видаляємо можливі теги міркувань <think> (характерно для DeepSeek R1)
        result_text = re.sub(r'<think>.*?</think>', '', result_text, flags=re.DOTALL).strip()

        # АНТИКРИХКІСТЬ: Очищаємо маркдаун-обгортки, які MiMo все одно повертає навіть у JSON Mode
        if "```json" in result_text:
            result_text = result_text.split("```json")[1].split("```")[0].strip()
        elif "```" in result_text:
            result_text = result_text.split("```")[1].split("```")[0].strip()

        # АНТИКРИХКІСТЬ: Ізолюємо безпосередньо сам JSON-об'єкт (від першої { до останньої })
        start_idx = result_text.find('{')
        end_idx = result_text.rfind('}')
        if start_idx != -1 and end_idx != -1:
            result_text = result_text[start_idx:end_idx+1]

        # АНТИКРИХКІСТЬ: Автоматично виправляємо невалідні одинарні бекслеші у подвійні
        result_text = re.sub(r'\\(?!["\\/bfnrtu])', r'\\\\', result_text)

        return json.loads(result_text)

    except RateLimitError as e:
        logger.error(f"❌ MiMo Rate Limit Перевищено (429): {e}")
        return {"error": "RateLimitError", "fallback": True}
    except APIConnectionError as e:
        logger.error(f"❌ Помилка мережевого з'єднання з серверами Xiaomi: {e}")
        return {"error": "APIConnectionError", "fallback": True}
    except APIStatusError as e:
        logger.error(f"❌ Помилка статусу MiMo API (Код {e.status_code}): {e.message}")
        return {"error": f"APIStatusError: {e.status_code}", "fallback": True}
    except APIError as e:
        logger.error(f"❌ Внутрішня помилка MiMo API: {e}")
        return {"error": "APIError", "fallback": True}
    except Exception as e:
        logger.error(f"❌ Неочікувана помилка парсингу: {e}")
        return {"error": str(e), "fallback": True}

if __name__ == "__main__":
    print("=== ТЕСТУВАННЯ МОНОЛІТНОГО КЛІЄНТА XIAOMI MIMO ===")
    test_prompt = "Generate a JSON object with one key 'status' and value 'ok'."
    result = generate_json_with_failover(test_prompt, thinking=False)
    print(json.dumps(result, indent=2))
