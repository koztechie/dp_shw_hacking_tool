from typing import Any

import tiktoken

from src.logger import logger


class ContextWindowManager:
    """
    АНТИКРИХКІСТЬ: Керування контекстним вікном для запобігання обрізанню промптів.
    """

    # Ліміти для різних моделей (в токенах)
    MODEL_LIMITS = {"mimo-v2.5-pro": 32000, "mimo-v2.5": 16000, "gpt-4-turbo": 128000, "claude-3-opus": 200000}

    # Резерв для відповіді (30% від ліміту)
    RESPONSE_RESERVE_RATIO = 0.3

    def __init__(self, model_name: str = "mimo-v2.5-pro"):
        self.model_name = model_name
        self.max_tokens = self.MODEL_LIMITS.get(model_name, 32000)
        self.max_prompt_tokens = int(self.max_tokens * (1 - self.RESPONSE_RESERVE_RATIO))

        try:
            # Tiktoken не підтримує MiMo, використовуємо GPT-4 як проксі
            self.encoder = tiktoken.encoding_for_model("gpt-4")
        except Exception:
            self.encoder = tiktoken.get_encoding("cl100k_base")

    def count_tokens(self, text: str) -> int:
        """Підраховує кількість токенів в тексті."""
        return len(self.encoder.encode(text))

    def truncate_to_fit(self, prompt: str, variables: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        """
        Обрізає змінні, щоб промпт вмістився в контекстне вікно.
        Пріоритет обрізання:
        1. Довгі описи (solution, problem)
        2. Технічні деталі (tech_stack)
        3. JSON схеми
        """
        # Підраховуємо базовий розмір промпту (без змінних)
        base_prompt = prompt
        for var_name in variables:
            base_prompt = base_prompt.replace(f"{{{var_name}}}", "")

        base_tokens = self.count_tokens(base_prompt)
        available_tokens = self.max_prompt_tokens - base_tokens

        # Сортуємо змінні за пріоритетом обрізання
        priority_order = [
            "solution",
            "problem",
            "description",  # Високий пріоритет обрізання
            "tech_stack",
            "sponsor_tech_used",
            "hackathon_data",
            "osint_data",
            "schema",
            "constraints",  # Низький пріоритет обрізання
        ]

        truncated_vars = variables.copy()

        # Спочатку підраховуємо загальний розмір
        total_tokens = base_tokens
        for _, var_value in variables.items():
            var_text = var_value if isinstance(var_value, str) else str(var_value)
            total_tokens += self.count_tokens(var_text)

        # Обрізаємо, якщо перевищує ліміт
        if total_tokens > self.max_prompt_tokens:
            logger.warning(f"⚠️ Промпт перевищує ліміт ({total_tokens} > {self.max_prompt_tokens} токенів). Обрізаю...")

            for var_name in priority_order:
                if var_name not in truncated_vars:
                    continue

                var_value = truncated_vars[var_name]
                var_text = var_value if isinstance(var_value, str) else str(var_value)
                var_tokens = self.count_tokens(var_text)

                # Якщо змінна займає більше 20% доступного простору - обрізаємо
                if var_tokens > available_tokens * 0.2:
                    max_tokens_for_var = int(available_tokens * 0.15)
                    truncated_text = self._truncate_text(var_text, max_tokens_for_var)
                    truncated_vars[var_name] = truncated_text

                    logger.info(
                        f"📏 Обрізано '{var_name}': {var_tokens} -> {self.count_tokens(truncated_text)} токенів"
                    )

                    # Перераховуємо доступний простір
                    available_tokens += var_tokens - self.count_tokens(truncated_text)

                if total_tokens <= self.max_prompt_tokens:
                    break

        # Формуємо фінальний промпт
        final_prompt = prompt
        for var_name, var_value in truncated_vars.items():
            final_prompt = final_prompt.replace(f"{{{var_name}}}", str(var_value))

        final_tokens = self.count_tokens(final_prompt)
        logger.info(
            f"✅ Фінальний розмір промпту: {final_tokens} токенів "
            f"({final_tokens / self.max_prompt_tokens * 100:.1f}% від ліміту)"
        )

        return final_prompt, truncated_vars

    def _truncate_text(self, text: str, max_tokens: int) -> str:
        """Обрізає текст до вказаної кількості токенів."""
        tokens = self.encoder.encode(text)
        if len(tokens) <= max_tokens:
            return text

        truncated_tokens = tokens[:max_tokens]
        truncated_text = self.encoder.decode(truncated_tokens)

        # Додаємо індикатор обрізання
        return truncated_text + "... [TRUNCATED]"


# Глобальний інстанс
context_manager = ContextWindowManager()
