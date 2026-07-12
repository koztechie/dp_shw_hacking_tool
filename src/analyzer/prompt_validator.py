from typing import Any

from jsonschema import ValidationError, validate

from src.logger import logger


class PromptSchemaValidator:
    """
    АНТИКРИХКІСТЬ: Валідація JSON відповідей від LLM за строгою схемою.
    """

    # Схеми для різних типів запитів
    SCHEMAS = {
        "idea_generation": {
            "type": "object",
            "required": ["ideas"],
            "properties": {
                "ideas": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 5,
                    "items": {
                        "type": "object",
                        "required": ["title", "tagline", "problem", "solution", "tech_stack"],
                        "properties": {
                            "title": {"type": "string", "minLength": 3},
                            "tagline": {"type": "string", "minLength": 5},
                            "problem": {"type": "string"},
                            "solution": {"type": "string"},
                            "killer_feature": {"type": "string"},
                            "sponsor_tech_used": {"type": "array", "items": {"type": "string"}},
                            "tech_stack": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                            "target_track": {"type": "string"},
                            "why_wins": {"type": "string"},
                            "risk": {"type": "string"}
                        }
                    }
                }
            }
        },
        "techspec": {
            "type": "object",
            "required": ["project_name", "architecture", "tech_stack", "timeline_plan"],
            "properties": {
                "project_name": {"type": "string", "minLength": 3},
                "tagline": {"type": "string"},
                "killer_feature": {"type": "string"},
                "architecture": {
                    "type": "object",
                    "required": ["frontend", "backend", "database"],
                    "properties": {
                        "frontend": {"type": "string"},
                        "backend": {"type": "string"},
                        "database": {"type": "string"},
                        "ai_integration": {"type": "string"},
                        "deployment": {"type": "string"}
                    }
                },
                "tech_stack": {
                    "type": "object",
                    "required": ["must_have"],
                    "properties": {
                        "must_have": {"type": "array", "items": {"type": "string"}},
                        "nice_to_have": {"type": "array", "items": {"type": "string"}},
                        "avoid": {"type": "array", "items": {"type": "string"}}
                    }
                },
                "timeline_plan": {
                    "type": "object",
                    "properties": {
                        "phase_1_setup": {"type": "string"},
                        "phase_2_core": {"type": "string"},
                        "phase_3_integration": {"type": "string"},
                        "phase_4_polish": {"type": "string"},
                        "phase_5_submission": {"type": "string"}
                    },
                    "required": ["phase_1_setup", "phase_2_core", "phase_3_integration", "phase_4_polish", "phase_5_submission"]
                },
                "ux_design": {"type": "object"},
                "demo_script": {"type": "string"},
                "antifragile_features": {"type": "array", "items": {"type": "string"}},
                "judging_alignment": {"type": "object"},
                "do_not": {"type": "array", "items": {"type": "string"}}
            }
        },
        "hard_constraints": {
            "type": "object",
            "properties": {
                "max_team_size": {"type": "integer", "minimum": 1, "maximum": 10},
                "must_use_apis_or_tech": {"type": "array", "items": {"type": "string"}},
                "forbidden_tech": {"type": "array", "items": {"type": "string"}},
                "eligibility_restrictions": {"type": "string"},
                "intellectual_property_rules": {"type": "string"}
            }
        },
        "profile_analysis": {
            "type": "object",
            "required": ["themes", "sponsors"],
            "properties": {
                "themes": {"type": "array", "items": {"type": "string"}},
                "participant_count": {"type": "integer", "minimum": 0},
                "prize_total": {"type": "string"},
                "judging_criteria": {"type": "string"},
                "sponsors": {"type": "array", "items": {"type": "string"}}
            }
        },
        "judge_evaluation": {
            "type": "object",
            "required": ["judge_score", "critique"],
            "properties": {
                "judge_score": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                "critique": {"type": "string"}
            }
        },
        "idea_uniqueness_check": {
            "type": "object",
            "required": ["reasoning", "is_unique", "max_similarity_percentage", "prompt_modification"],
            "properties": {
                "reasoning": {"type": "string"},
                "is_unique": {"type": "boolean"},
                "max_similarity_percentage": {"type": "integer", "minimum": 0, "maximum": 100},
                "prompt_modification": {"type": "string"}
            }
        }
    }

    @classmethod
    def validate_response(cls, response: dict[str, Any], schema_name: str) -> tuple[bool, str]:
        """
        Валідує JSON відповідь за схемою.
        Повертає: (is_valid, error_message)
        """
        if schema_name not in cls.SCHEMAS:
            return True, ""  # Невідома схема - пропускаємо валідацію

        schema = cls.SCHEMAS[schema_name]

        try:
            validate(instance=response, schema=schema)
            return True, ""
        except ValidationError as e:
            error_msg = f"JSON Schema Validation Failed: {e.message} at path {'.'.join(map(str, e.path))}"
            logger.warning(f"⚠️ {error_msg}")
            return False, error_msg

    @classmethod
    def get_schema(cls, schema_name: str) -> dict[str, Any]:
        """Повертає схему для використання в промпті."""
        return cls.SCHEMAS.get(schema_name, {})
