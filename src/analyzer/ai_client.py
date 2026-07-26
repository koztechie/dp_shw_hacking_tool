import base64
import html
import json
import re
import sys
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from tenacity import retry, stop_after_attempt, wait_exponential

# Гарантуємо правильні шляхи імпорту

from openai import APIConnectionError, APIStatusError, OpenAI, RateLimitError  # noqa: E402

from src.analyzer.prompt_validator import PromptSchemaValidator  # noqa: E402
from src.analyzer.rate_limiter import check_and_increment  # noqa: E402
from src.logger import logger  # noqa: E402

MAX_RESPONSE_SIZE = 100 * 1024  # 100KB ліміт


# ==========================================
# 🔌 CIRCUIT BREAKER PATTERN (АНТИКРИХКІСТЬ)
# ==========================================
class AICircuitBreaker:
    def __init__(self):
        self.failures = {}
        self.cooldown = 300  # 5 хвилин cooldown
    
    def is_open(self, provider: str) -> bool:
        if provider not in self.failures:
            return False
        last_fail, count = self.failures[provider]
        if count >= 3 and datetime.now() - last_fail < timedelta(seconds=self.cooldown):
            logger.warning(f"🔌 Circuit Breaker OPEN для {provider}. Очікування...")
            return True
        return False
    
    def record_failure(self, provider: str):
        now = datetime.now()
        if provider in self.failures:
            _, count = self.failures[provider]
            self.failures[provider] = (now, count + 1)
        else:
            self.failures[provider] = (now, 1)
        logger.error(f"⚠️ Збій API провайдера: {provider}. Помилок поспіль: {self.failures[provider][1]}")
    
    def record_success(self, provider: str):
        if provider in self.failures:
            logger.info(f"🔌 Circuit Breaker CLOSED для {provider} (зв'язок відновлено).")
            del self.failures[provider]

    def reset(self):
        """Скидає стан Circuit Breaker для всіх провайдерів."""
        self.failures.clear()

mimo_circuit_breaker = AICircuitBreaker()


# ==========================================
# 🔌 GENERIC CIRCUIT BREAKER (test-friendly)
# ==========================================
class CircuitBreaker:
    """Generic Circuit Breaker з підтримкою failure_threshold та recovery_timeout."""

    def __init__(self, failure_threshold: int = 3, recovery_timeout: int = 300):
        self._threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._failure_count = 0
        self._opened_at = None
        self._lock = threading.Lock()

    @property
    def failure_count(self) -> int:
        return self._failure_count

    def is_open(self) -> bool:
        with self._lock:
            if self._failure_count < self._threshold:
                return False
            if self._opened_at is None:
                return True
            elapsed = (datetime.now() - self._opened_at).total_seconds()
            if elapsed >= self._recovery_timeout:
                # Half-open: allow one attempt
                return False
            return True

    def record_failure(self, provider: str = "default"):
        with self._lock:
            self._failure_count += 1
            if self._failure_count >= self._threshold and self._opened_at is None:
                self._opened_at = datetime.now()

    def record_success(self, provider: str = "default"):
        self.reset()

    def reset(self):
        with self._lock:
            self._failure_count = 0
            self._opened_at = None

    def call(self, func, *args, **kwargs):
        if self.is_open():
            raise Exception("Circuit breaker is OPEN")
        try:
            result = func(*args, **kwargs)
            self.record_success()
            return result
        except Exception:
            self.record_failure()
            raise


def _get_image_mime_type(image_bytes: bytes) -> str:
    if image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    elif image_bytes.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    elif image_bytes.startswith(b"GIF87a") or image_bytes.startswith(b"GIF89a"):
        return "image/gif"
    elif image_bytes.startswith(b"RIFF") and image_bytes[8:12] == b"WEBP":
        return "image/webp"
    return "image/jpeg"


_clients = {}

def _get_client(api_key: str, base_url: str) -> OpenAI:
    if base_url not in _clients:
        _clients[base_url] = OpenAI(api_key=api_key, base_url=base_url)
    return _clients[base_url]

def _call_api(
    api_key: str,
    base_url: str,
    prompt: str,
    image_bytes: bytes = None,
    thinking: bool = True,
    model: str = None,
    schema_name: str = None,
    max_retries: int = 2
) -> dict:
    try:
        client = _get_client(api_key=api_key, base_url=base_url)
    except Exception as e:
        logger.warning(f"Не вдалося ініціалізувати OpenAI клієнт: {e}")
        return {"error": "Client Init Error", "fallback": True}

    if not check_and_increment():
        return {"error": "Local rate limit exceeded", "fallback": True}

    # АНТИКРИХКІСТЬ: Миттєвий фолбек, якщо запобіжник відкритий (заощаджує час та ресурси)
    provider = "mimo" if "xiaomi" in base_url.lower() or "mimo" in base_url.lower() else "openrouter"
    if mimo_circuit_breaker.is_open(provider):
        return {"error": f"Circuit breaker is OPEN for {provider}", "fallback": True}

    # КРИТИЧНИЙ ФІКС: Додаємо JSON Schema в промпт для структурованого виводу
    if schema_name:
        schema = PromptSchemaValidator.get_schema(schema_name)
        if schema:
            schema_json = json.dumps(schema, indent=2)
            prompt = (
                f"{prompt}\n\n🚨 CRITICAL: Your response MUST strictly match this JSON Schema:\n"
                f"```json\n{schema_json}\n```"
            )

    for attempt in range(max_retries + 1):
        try:
            sys_prompt = (
                f"You are an AI assistant. Today's date: {datetime.now().strftime('%A, %B %d, %Y')}. "
                "Your knowledge cutoff date is December 2024.\n"
                "Return JSON only, no explanations, no extra text."
            )

            target_model = model
            if image_bytes:
                if "mimo" in model:
                    target_model = "mimo-v2.5"
                logger.info(f"ШІ-Клієнт: Виявлено зображення. Маршрутизація на Vision-модель ({target_model})...")
                mime_type = _get_image_mime_type(image_bytes)
                b64_img = base64.b64encode(image_bytes).decode("utf-8")
                user_content = [
                    {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{b64_img}"}},
                    {"type": "text", "text": prompt},
                ]
            else:
                logger.info(f"ШІ-Клієнт: Текстовий запит. Маршрутизація на ({target_model})...")
                user_content = prompt

            messages = [{"role": "system", "content": sys_prompt}, {"role": "user", "content": user_content}]

            # Функція виклику для передачі в обгортку
            def _execute_call(model=target_model, msgs=messages):
                kwargs = {
                    "model": model,
                    "messages": msgs,
                    "response_format": {"type": "json_object"},
                    "temperature": 1.0 if thinking else 0.3,
                    "max_completion_tokens": 16384,
                    "timeout": 120.0,
                    "stream": True,  # Вмикаємо стрімінг для запобігання OOM
                }
                if "mimo" in model:
                    kwargs["extra_body"] = {"thinking": {"type": "enabled" if thinking else "disabled"}}
                
                response_stream = client.chat.completions.create(**kwargs)
                full_content = ""
                for chunk in response_stream:
                    if chunk.choices and chunk.choices[0].delta.content:
                        full_content += chunk.choices[0].delta.content
                        if len(full_content.encode('utf-8')) > MAX_RESPONSE_SIZE:
                            raise ValueError(f"Response too large, exceeding limit of {MAX_RESPONSE_SIZE} bytes.")
                return full_content

            # ВИКЛИКАЄМО API ЧЕРЕЗ ЗАПОБІЖНИК ТА ТЕНАСІТІ
            @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=2, max=10), reraise=True)
            def call_with_retry():
                try:
                    res = _execute_call()
                    mimo_circuit_breaker.record_success(provider)
                    return res
                except Exception as e:
                    mimo_circuit_breaker.record_failure(provider)
                    raise e
                    
            result_text = call_with_retry()

            if not result_text or not result_text.strip():
                raise ValueError("Сервер повернув порожній результат або сталася помилка стрімінгу.")

            # Видаляємо теги міркувань
            result_text = re.sub(r"<think>.*?</think>", "", result_text, flags=re.DOTALL).strip()

            # Очищаємо маркдаун
            if "```json" in result_text:
                result_text = result_text.split("```json")[1].split("```")[0].strip()
            elif "```" in result_text:
                result_text = result_text.split("```")[1].split("```")[0].strip()

            # Ізолюємо JSON
            start_idx = result_text.find("{")
            end_idx = result_text.rfind("}")
            if start_idx != -1 and end_idx != -1:
                result_text = result_text[start_idx : end_idx + 1]

            result_text = re.sub(r'\\(?!["\\/bfnrtu])', r"\\\\", result_text)

            try:
                parsed_result = json.loads(result_text)
            except json.JSONDecodeError as e:
                # АНТИКРИХКІСТЬ: Якщо є зайві дані (Extra data), витягуємо лише перший валідний JSON-об'єкт
                if "Extra data" in str(e):
                    parsed_result, _ = json.JSONDecoder().raw_decode(result_text.lstrip())
                else:
                    raise

            # КРИТИЧНИЙ ФІКС: Валідація схеми
            if schema_name:
                is_valid, error_msg = PromptSchemaValidator.validate_response(parsed_result, schema_name)
                if not is_valid:
                    if attempt < max_retries:
                        logger.warning(f"🔄 Спроба {attempt + 1}/{max_retries}: Невалідний JSON. Повторюю запит...")
                        continue
                    else:
                        logger.error(f"❌ Всі спроби невдалі: {error_msg}")
                        return {"error": error_msg, "fallback": True}

            return parsed_result

        # --- ЗБОЇ ЗВ'ЯЗКУ ТА СЕРВЕРА ТРИГЕРИТЬ ЗАПОБІЖНИК ---
        except RateLimitError as e:
            logger.error(f"❌ Rate Limit Перевищено (429): {e}")
            mimo_circuit_breaker.record_failure(provider)
            return {"error": "RateLimitError", "fallback": True}
        except APIConnectionError as e:
            logger.error(f"❌ Помилка мережевого з'єднання: {e}")
            mimo_circuit_breaker.record_failure(provider)
            return {"error": "APIConnectionError", "fallback": True}
        except APIStatusError as e:
            logger.error(f"❌ Помилка статусу API (Код {e.status_code}): {e.message}")
            mimo_circuit_breaker.record_failure(provider)
            return {"error": f"APIStatusError: {e.status_code}", "fallback": True}
        except Exception as e:
            if attempt < max_retries:
                logger.warning(f"🔄 Неочікувана помилка (спроба {attempt + 1}), повторюю запит: {e}")
                continue
            logger.error(f"❌ Всі спроби вичерпано. Остання помилка: {e}")
            return {"error": str(e), "fallback": True}

    return {"error": "Max retries exceeded", "fallback": True}


def sanitize_user_input(text: str, max_length: int = 5000) -> str:
    """Очищує користувацький ввод від потенційних prompt injection спроб."""
    if not text:
        return ""
    # Екрануємо HTML, обрізаємо, прибираємо спецсимволи
    text = html.escape(text[:max_length])
    # Заміна небезпечних директив
    dangerous = ["ignore previous", "ignore all", "system prompt", "user prompt", 
                 "delete all", "rm -rf", "exec(", "eval(", "import os"]
    for d in dangerous:
        if d.lower() in text.lower():
            text = re.sub(re.escape(d), f"[BLOCKED:{d.upper()}]", text, flags=re.IGNORECASE)
            logger.warning(f"Заблоковано потенційно небезпечний фрагмент: {d}")
    return text

def generate_json_with_failover(
    prompt: str,
    image_bytes: bytes = None,
    thinking: bool = True,
    schema_name: str = None,
    max_retries: int = 2,
) -> dict:
    """Каскадний AI-роутер: MiMo → OpenRouter → Offline Fallback."""
    # Sanitize prompt before sending
    prompt = sanitize_user_input(prompt)
    
    from config.settings import MIMO_API_KEY, MIMO_BASE_URL, OPENROUTER_API_KEY, OPENROUTER_BASE_URL

    # Спроба 1: MiMo
    if MIMO_API_KEY and MIMO_API_KEY != "your_key_here":
        result = _call_api(
            MIMO_API_KEY,
            MIMO_BASE_URL,
            prompt,
            image_bytes,
            thinking,
            model="mimo-v2.5-pro",
            schema_name=schema_name,
            max_retries=max_retries,
        )
        if result and "error" not in result:
            return result

    # Спроба 2: OpenRouter (безкоштовні моделі)
    if OPENROUTER_API_KEY and OPENROUTER_API_KEY != "sk-or-v1-your_key_here":
        result = _call_api(
            OPENROUTER_API_KEY,
            OPENROUTER_BASE_URL,
            prompt,
            image_bytes,
            thinking,
            model="meta-llama/llama-3.3-70b-instruct:free",
            schema_name=schema_name,
            max_retries=max_retries
        )
        if result and "error" not in result:
            return result

    # Fallback
    return {"error": "All APIs unavailable", "fallback": True}


if __name__ == "__main__":
    print("=== ТЕСТУВАННЯ СТАТУСУ ЗАПОБІЖНИКА ===")
    print(f"Початковий стан заблоковано? - {mimo_circuit_breaker.is_open()}")
