import json
from pathlib import Path
from typing import Any

import duckdb

from config.settings import DB_PATH
from src.logger import logger


class PromptManager:
    """
    АНТИКРИХКІСТЬ: Централізоване управління промптами з версіонуванням та A/B тестуванням.
    """

    def __init__(self):
        self.prompts_dir = Path(__file__).parent.parent.parent / "prompts"
        self.prompts_dir.mkdir(exist_ok=True)
        self._init_prompts_table()

    def _init_prompts_table(self):
        """Створює таблицю для зберігання промптів в DuckDB."""
        con = duckdb.connect(DB_PATH)
        con.execute("""
            CREATE TABLE IF NOT EXISTS prompts (
                id INTEGER PRIMARY KEY,
                prompt_name VARCHAR,
                version INTEGER,
                template TEXT,
                variables TEXT,
                created_at TIMESTAMP DEFAULT current_timestamp,
                is_active BOOLEAN DEFAULT TRUE,
                success_count INTEGER DEFAULT 0,
                failure_count INTEGER DEFAULT 0,
                avg_response_time_ms INTEGER DEFAULT 0
            )
        """)
        con.close()

    def get_prompt(self, prompt_name: str, variables: dict[str, Any] = None) -> str:
        """
        Отримує активний промпт за назвою та підставляє змінні.
        """
        con = duckdb.connect(DB_PATH, read_only=True)
        try:
            result = con.execute(
                """
                SELECT template, variables FROM prompts
                WHERE prompt_name = ? AND is_active = TRUE
                ORDER BY version DESC
                LIMIT 1
            """,
                [prompt_name],
            ).fetchone()

            if not result:
                # Fallback на вбудований промпт
                return self._get_builtin_prompt(prompt_name, variables)

            template, vars_json = result
            expected_vars = json.loads(vars_json) if vars_json else []

            # Підставляємо змінні
            if variables:
                for var in expected_vars:
                    if var not in variables:
                        logger.warning(f"⚠️ Відсутня змінна '{var}' в промпті '{prompt_name}'")
                        variables[var] = ""

                return template.format(**variables)
            return template
        finally:
            con.close()

    def update_prompt_metrics(self, prompt_name: str, success: bool, response_time_ms: int):
        """Оновлює метрики успішності промпту."""
        con = duckdb.connect(DB_PATH)
        try:
            if success:
                con.execute(
                    """
                    UPDATE prompts SET
                        success_count = success_count + 1,
                        avg_response_time_ms = (avg_response_time_ms + ?) / 2
                    WHERE prompt_name = ? AND is_active = TRUE
                """,
                    [response_time_ms, prompt_name],
                )
            else:
                con.execute(
                    """
                    UPDATE prompts SET
                        failure_count = failure_count + 1
                    WHERE prompt_name = ? AND is_active = TRUE
                """,
                    [prompt_name],
                )
        finally:
            con.close()

    def create_prompt_version(self, prompt_name: str, template: str, variables: list = None):
        """Створює нову версію промпту."""
        con = duckdb.connect(DB_PATH)
        try:
            # Деактивуємо старі версії
            con.execute(
                """
                UPDATE prompts SET is_active = FALSE
                WHERE prompt_name = ? AND is_active = TRUE
            """,
                [prompt_name],
            )

            # Створюємо нову версію
            con.execute(
                """
                INSERT INTO prompts (prompt_name, version, template, variables)
                VALUES (?, COALESCE((SELECT MAX(version) FROM prompts WHERE prompt_name = ?), 0) + 1, ?, ?)
            """,
                [prompt_name, prompt_name, template, json.dumps(variables or [])],
            )

            logger.info(f"✅ Створено нову версію промпту '{prompt_name}'")
        finally:
            con.close()

    def rollback_prompt(self, prompt_name: str, version: int):
        """Відкочує промпт до вказаної версії."""
        con = duckdb.connect(DB_PATH)
        try:
            con.execute(
                """
                UPDATE prompts SET is_active = FALSE
                WHERE prompt_name = ?
            """,
                [prompt_name],
            )

            con.execute(
                """
                UPDATE prompts SET is_active = TRUE
                WHERE prompt_name = ? AND version = ?
            """,
                [prompt_name, version],
            )

            logger.info(f"↩️ Відкочено промпт '{prompt_name}' до версії {version}")
        finally:
            con.close()

    def _get_builtin_prompt(self, prompt_name: str, variables: dict[str, Any] = None) -> str:
        """Fallback на вбудовані промпти (для зворотної сумісності)."""
        builtin_prompts = {
            "idea_brainstormer": """You are an elite product architect.
Brainstorm 3 BRAND NEW, innovative project ideas.

CRITICAL RULES (OBEY OR FAIL):
1. PLATFORM CONSTRAINTS: The developer uses a weak AMD A4 CPU with 6GB RAM.
If App Store publishing is required, you MUST propose web-technologies wrapped with
Capacitor or Expo targeting CLOUD BUILDS.
2. MONETIZATION: For RevenueCat, focus on subscriptions. NEVER use Web Billing SDKs for mobile apps.

Output a JSON with a single key "draft_ideas" containing a list of 3 ideas.
NEW HACKATHON TARGET: {hackathon_data}
""",
            "idea_critic": """You are an extremely strict Hackathon Judge.

YOUR TASKS:
1. HARDWARE & PLATFORM CHECK: Discard ANY idea containing Unity or pure PWA if App Store is required.
2. THEME CHECK: Ensure the idea heavily uses the sponsor's tech.
3. REFINE: Select the best 3 surviving ideas.

Return EXACTLY a JSON object matching this schema: {schema}

🚨 HARD CONSTRAINTS: {constraints}
DRAFT IDEAS TO REVIEW: {draft_ideas}
""",
            "techspec_generator": """You are a senior full-stack architect
and serial hackathon winner. Generate a HIGHLY DETAILED technical specification.

IDEA: {idea}
HACKATHON CONTEXT: {hackathon_context}

CRITICAL HARDWARE CONSTRAINTS: {hardware_constraints}

🚨 RULES & CONSTRAINTS: {constraints}

Return EXACTLY a JSON object matching this schema: {schema}
""",
            "hard_constraints_extractor": """Analyze the following hackathon rules text
and extract ONLY the hard constraints.
Rules text: {rules_text}
Return EXACTLY a JSON object matching this schema: {schema}
""",
            "profile_analyzer": """You are an elite product analyst.
Analyze the following hackathon data and background OSINT.

HACKATHON DATA: {hackathon_data}
ORGANIZER OSINT: {osint_data}

Return EXACTLY a JSON object matching this schema: {schema}
""",
            "judge_simulator": """You are the official judging panel for the "{hackathon_title}" hackathon.
Judging Criteria: {criteria}
Judges Background: {judges}

Critically evaluate this project submission:
Title: {title}
Pitch: {tagline}
Solution: {solution}
Tech Stack: {tech_stack}

Return EXACTLY a JSON object with your evaluation: {schema}
""",
        }

        template = builtin_prompts.get(prompt_name, "")
        if variables:
            return template.format(**variables)
        return template


# Глобальний інстанс
prompt_manager = PromptManager()
