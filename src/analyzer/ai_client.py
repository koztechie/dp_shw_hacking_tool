import sys
from pathlib import Path
import json
import base64
from datetime import datetime
import re
import time

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

# ==========================================
# 🔌 CIRCUIT BREAKER PATTERN (АНТИКРИХКІСТЬ)
# ==========================================
class CircuitBreaker:
    """
    Запобіжник: Автоматично блокує запити до зовнішнього API після 3 збоїв поспіль,
    захищаючи процесор, час відгуку та запобігаючи нескінченним таймаутам.
    """
    def __init__(self, failure_threshold=3, recovery_timeout=300):
        self.failure_count = 0
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.last_failure_time = 0

    def is_open(self) -> bool:
        if self.failure_count >= self.failure_threshold:
            # Перевіряємо, чи минув час відновлення (5 хвилин)
            if time.time() - self.last_failure_time < self.recovery_timeout:
                return True
            else:
                logger.warning("🔌 Circuit Breaker перейшов у стан HALF-OPEN. Пробний запит дозволено...")
                return False
        return False

    def record_failure(self):
        self.failure_count += 1
        self.last_failure_time = time.time()
        logger.error(f"⚠️ Зафіксовано збій API Xiaomi. Помилок поспіль: {self.failure_count}/{self.failure_threshold}")
        if self.failure_count >= self.failure_threshold:
            logger.critical(f"🚨 CIRCUIT BREAKER ВІДЧИНЕНО! Доступ до API блокується на {self.recovery_timeout} секунд.")

    def reset(self):
        if self.failure_count > 0:
            logger.info("🔌 Circuit Breaker повернувся в стан CLOSED (зв'язок успішно відновлено).")
        self.failure_count = 0
        self.last_failure_time = 0

    def call(self, func, *args, **kwargs):
        if self.is_open():
            raise Exception("Circuit breaker is OPEN. API calls are temporarily blocked.")
        try:
            result = func(*args, **kwargs)
            self.reset()
            return result
        except Exception as e:
            self.record_failure()
            raise

# Ініціалізуємо глобальний запобіжник
mimo_circuit_breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=300)

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

    # АНТИКРИХКІСТЬ: Миттєвий фолбек, якщо запобіжник відкритий (заощаджує час та ресурси)
    if mimo_circuit_breaker.is_open():
        logger.warning("🔌 Запит заблоковано запобіжником (Circuit Breaker OPEN). Миттєве перемикання на офлайн.")
        return {"error": "Circuit breaker is OPEN", "fallback": True}

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

        # Функція виклику для передачі в обгортку
        def _execute_call():
            return client.chat.completions.create(
                model=target_model,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=1.0 if thinking else 0.3,
                max_completion_tokens=16384, 
                timeout=120.0,
                extra_body={"thinking": {"type": "enabled" if thinking else "disabled"}}
            )

        # Викликаємо API через наш запобіжник
        response = mimo_circuit_breaker_call = client_call = generate_json_with_failover # legacy context mapper
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

        # Видаляємо теги міркувань
        result_text = re.sub(r'<think>.*?</think>', '', result_text, flags=re.DOTALL).strip()

        # Очищаємо маркдаун
        if "```json" in result_text:
            result_text = result_text.split("```json")[1].split("```")[0].strip()
        elif "```" in result_text:
            result_text = result_text.split("```")[1].split("```")[0].strip()

        # Ізолюємо JSON
        start_idx = result_text.find('{')
        end_idx = result_text.rfind('}')
        if start_idx != -1 and end_idx != -1:
            result_text = result_text[start_idx:end_idx+1]

        result_text = re.sub(r'\\(?!["\\/bfnrtu])', r'\\\\', result_text)

        return json.loads(result_text)

    # --- ЗБОЇ ЗВ'ЯЗКУ ТА СЕРВЕРА ТРИГЕРИТЬ ЗАПОБІЖНИК ---
    except RateLimitError as e:
        logger.error(f"❌ MiMo Rate Limit Перевищено (429): {e}")
        mimo_circuit_breaker.record_failure()
        return {"error": "RateLimitError", "fallback": True}
    except APIConnectionError as e:
        logger.error(f"❌ Помилка мережевого з'єднання з серверами Xiaomi: {e}")
        mimo_circuit_breaker.record_failure()
        return {"error": "APIConnectionError", "fallback": True}
    except APIStatusError as e:
        logger.error(f"❌ Помилка статусу MiMo API (Код {e.status_code}): {e.message}")
        mimo_circuit_breaker.record_failure()
        return {"error": f"APIStatusError: {e.status_code}", "fallback": True}
    except Exception as e:
        logger.error(f"❌ Неочікувана помилка: {e}")
        # Інші помилки парсингу чи логіки не є збоями мережі, але ми все одно надійно повертаємо фолбек
        return {"error": str(e), "fallback": True}

if __name__ == "__main__":
    print("=== ТЕСТУВАННЯ СТАТУСУ ЗАПОБІЖНИКА ===")
    print(f"Початковий стан заблоковано? - {mimo_circuit_breaker.is_open()}")
