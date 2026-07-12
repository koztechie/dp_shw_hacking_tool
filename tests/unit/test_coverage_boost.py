"""
Coverage boost tests: cache, prompt_validator, profile_analyzer, causal_inference.
These are pure/logic modules that were uncovered — adding them closes the 70% gap.
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# src/analyzer/cache.py
# ---------------------------------------------------------------------------

class TestCache:
    """Tests for cache_key, get_cached, set_cache."""

    def _make_cache_module(self, tmp_path: Path):
        """Import cache with CACHE_DIR patched to a temp directory."""
        import importlib
        import sys

        # Patch CACHE_DIR in settings before importing cache
        with patch.dict("sys.modules", {}):
            with patch("config.settings.CACHE_DIR", str(tmp_path)):
                # Force re-import so module-level CACHE_PATH uses tmp_path
                if "src.analyzer.cache" in sys.modules:
                    del sys.modules["src.analyzer.cache"]
                from src.analyzer import cache as cache_mod
                # Redirect CACHE_PATH to our temp dir for this test
                cache_mod.CACHE_PATH = tmp_path
                return cache_mod

    def test_cache_key_string(self):
        from src.analyzer.cache import cache_key
        k = cache_key("hello")
        assert isinstance(k, str)
        assert len(k) == 32  # MD5 hex

    def test_cache_key_dict_order_independent(self):
        from src.analyzer.cache import cache_key
        k1 = cache_key({"b": 2, "a": 1})
        k2 = cache_key({"a": 1, "b": 2})
        assert k1 == k2

    def test_cache_key_list(self):
        from src.analyzer.cache import cache_key
        k = cache_key([1, 2, 3])
        assert isinstance(k, str)

    def test_get_cached_returns_none_for_missing_key(self, tmp_path):
        mod = self._make_cache_module(tmp_path)
        result = mod.get_cached("nonexistent_key_xyz")
        assert result is None

    def test_set_and_get_cache_roundtrip(self, tmp_path):
        mod = self._make_cache_module(tmp_path)
        payload = {"score": 0.92, "label": "winner"}
        mod.set_cache("test_key_001", payload)
        retrieved = mod.get_cached("test_key_001")
        assert retrieved == payload

    def test_get_cached_handles_corrupted_file(self, tmp_path):
        mod = self._make_cache_module(tmp_path)
        bad_file = tmp_path / "bad_key.json"
        bad_file.write_text("{invalid_json_", encoding="utf-8")
        result = mod.get_cached("bad_key")
        assert result is None
        # Corrupted file must be deleted
        assert not bad_file.exists()

    def test_get_cached_handles_generic_exception(self, tmp_path):
        mod = self._make_cache_module(tmp_path)
        file_path = tmp_path / "err_key.json"
        file_path.write_text('{"ok": 1}', encoding="utf-8")
        with patch("builtins.open", side_effect=PermissionError("no access")):
            result = mod.get_cached("err_key")
        assert result is None

    def test_set_cache_handles_write_error(self, tmp_path):
        mod = self._make_cache_module(tmp_path)
        with patch("builtins.open", side_effect=OSError("disk full")):
            # Should not raise — just log the error
            mod.set_cache("any_key", {"data": 1})


# ---------------------------------------------------------------------------
# src/analyzer/prompt_validator.py
# ---------------------------------------------------------------------------

class TestPromptSchemaValidator:
    """Tests for PromptSchemaValidator.validate_response and get_schema."""

    @pytest.fixture(autouse=True)
    def import_validator(self):
        from src.analyzer.prompt_validator import PromptSchemaValidator
        self.validator = PromptSchemaValidator

    def test_validate_unknown_schema_passes(self):
        ok, msg = self.validator.validate_response({"anything": 1}, "unknown_schema_xyz")
        assert ok is True
        assert msg == ""

    def test_validate_idea_generation_valid(self):
        valid = {
            "ideas": [
                {
                    "title": "EcoTrack",
                    "tagline": "Track your carbon footprint in real time",
                    "problem": "Climate change",
                    "solution": "An app",
                    "tech_stack": ["Python", "FastAPI"],
                }
            ]
        }
        ok, msg = self.validator.validate_response(valid, "idea_generation")
        assert ok is True

    def test_validate_idea_generation_missing_required_field(self):
        invalid = {"ideas": [{"title": "X", "tagline": "Y", "problem": "Z"}]}  # missing solution, tech_stack
        ok, msg = self.validator.validate_response(invalid, "idea_generation")
        assert ok is False
        assert "solution" in msg or "tech_stack" in msg or "JSON Schema" in msg

    def test_validate_idea_generation_empty_ideas_list(self):
        invalid = {"ideas": []}
        ok, msg = self.validator.validate_response(invalid, "idea_generation")
        assert ok is False

    def test_validate_techspec_valid(self):
        valid = {
            "project_name": "BuildBot",
            "architecture": {"frontend": "React", "backend": "FastAPI", "database": "DuckDB"},
            "tech_stack": {"must_have": ["Python"]},
            "timeline_plan": {
                "phase_1_setup": "Setup",
                "phase_2_core": "Core",
                "phase_3_integration": "Integration",
                "phase_4_polish": "Polish",
                "phase_5_submission": "Submission"
            },
        }
        ok, msg = self.validator.validate_response(valid, "techspec")
        assert ok is True

    def test_validate_techspec_missing_project_name(self):
        invalid = {
            "architecture": {"frontend": "React", "backend": "FastAPI", "database": "DuckDB"},
            "tech_stack": {"must_have": ["Python"]},
            "timeline_plan": {
                "phase_1_setup": "Setup",
                "phase_2_core": "Core",
                "phase_3_integration": "Integration",
                "phase_4_polish": "Polish",
                "phase_5_submission": "Submission"
            },
        }
        ok, msg = self.validator.validate_response(invalid, "techspec")
        assert ok is False

    def test_validate_profile_analysis_valid(self):
        valid = {"themes": ["AI", "Health"], "sponsors": ["Google", "AWS"]}
        ok, msg = self.validator.validate_response(valid, "profile_analysis")
        assert ok is True

    def test_validate_profile_analysis_missing_required(self):
        invalid = {"participant_count": 200}
        ok, msg = self.validator.validate_response(invalid, "profile_analysis")
        assert ok is False

    def test_validate_judge_evaluation_valid(self):
        valid = {"judge_score": 0.85, "critique": "Solid execution."}
        ok, msg = self.validator.validate_response(valid, "judge_evaluation")
        assert ok is True

    def test_validate_judge_evaluation_score_out_of_range(self):
        invalid = {"judge_score": 1.5, "critique": "Too high"}
        ok, msg = self.validator.validate_response(invalid, "judge_evaluation")
        assert ok is False

    def test_get_schema_returns_dict_for_known_name(self):
        schema = self.validator.get_schema("idea_generation")
        assert isinstance(schema, dict)
        assert "required" in schema

    def test_get_schema_returns_empty_dict_for_unknown(self):
        schema = self.validator.get_schema("totally_unknown")
        assert schema == {}


# ---------------------------------------------------------------------------
# src/analyzer/profile_analyzer.py
# ---------------------------------------------------------------------------

class TestProfileAnalyzer:
    """Tests for analyze_hackathon_profile."""

    def test_returns_ai_result_on_success(self):
        ai_result = {
            "themes": ["AI", "Fintech"],
            "participant_count": 300,
            "prize_total": "$25,000",
            "judging_criteria": "Innovation",
            "sponsors": ["Stripe", "OpenAI"],
        }
        with patch("src.analyzer.profile_analyzer.generate_json_with_failover", return_value=ai_result):
            from src.analyzer.profile_analyzer import analyze_hackathon_profile
            result = analyze_hackathon_profile({"title": "Hackathon"}, {})
        assert result["themes"] == ["AI", "Fintech"]
        assert result["sponsors"] == ["Stripe", "OpenAI"]

    def test_returns_fallback_on_ai_error(self):
        fallback_response = {"error": "LLM unavailable"}
        hackathon_data = {
            "themes": ["Climate"],
            "participant_count": 150,
            "prize_total": "$10,000",
            "judging_criteria": "Impact",
            "sponsors": ["NASA"],
        }
        with patch("src.analyzer.profile_analyzer.generate_json_with_failover", return_value=fallback_response):
            from src.analyzer.profile_analyzer import analyze_hackathon_profile
            result = analyze_hackathon_profile(hackathon_data, {})
        assert result["themes"] == ["Climate"]
        assert result["sponsors"] == ["NASA"]
        assert result["prize_total"] == "$10,000"

    def test_fallback_on_fallback_key_in_response(self):
        with patch("src.analyzer.profile_analyzer.generate_json_with_failover", return_value={"fallback": True}):
            from src.analyzer.profile_analyzer import analyze_hackathon_profile
            result = analyze_hackathon_profile({"themes": ["Health"], "sponsors": []}, {})
        assert result["themes"] == ["Health"]

    def test_fallback_missing_hackathon_fields_uses_defaults(self):
        with patch("src.analyzer.profile_analyzer.generate_json_with_failover", return_value={"error": "fail"}):
            from src.analyzer.profile_analyzer import analyze_hackathon_profile
            result = analyze_hackathon_profile({}, {})
        assert result["themes"] == ["Open Ended"]
        assert result["participant_count"] == 100
        assert result["prize_total"] == "Unknown"
        assert result["judging_criteria"] == "Standard"
        assert result["sponsors"] == []

    def test_passes_banner_bytes_to_ai(self):
        ai_result = {"themes": ["Vision"], "sponsors": ["NVIDIA"]}
        with patch("src.analyzer.profile_analyzer.generate_json_with_failover", return_value=ai_result) as mock_fn:
            from src.analyzer.profile_analyzer import analyze_hackathon_profile
            analyze_hackathon_profile({}, {}, banner_bytes=b"fake_image_bytes")
        _, kwargs = mock_fn.call_args
        assert kwargs.get("image_bytes") == b"fake_image_bytes"


# ---------------------------------------------------------------------------
# src/analyzer/causal_inference.py
# ---------------------------------------------------------------------------

class TestCausalInference:
    """Tests for get_counterfactual_advice."""

    def test_no_advice_when_all_features_already_set(self):
        features = {"uses_sponsor_tech": 1, "has_video_demo": 1, "has_github": 1}
        with patch("src.analyzer.causal_inference.predict_win_probability", return_value=0.7):
            from src.analyzer.causal_inference import get_counterfactual_advice
            advice = get_counterfactual_advice(features, 0.7)
        assert advice == []

    def test_advice_generated_when_feature_missing_and_delta_large(self):
        # Base = 0.3, counterfactual = 0.6 → delta_rel = (0.6-0.3)/0.3 = 1.0 > 0.10
        features = {"uses_sponsor_tech": 0, "has_video_demo": 1, "has_github": 1}

        def mock_predict(f):
            return 0.6  # Always return high score for sponsor tech

        with patch("src.analyzer.causal_inference.predict_win_probability", side_effect=mock_predict):
            from src.analyzer.causal_inference import get_counterfactual_advice
            advice = get_counterfactual_advice(features, 0.3)
        assert len(advice) == 1
        assert "Causal Insight" in advice[0]

    def test_no_advice_when_delta_too_small(self):
        # Base = 0.5, counterfactual = 0.505 → delta_rel = 0.01 < 0.10
        features = {"uses_sponsor_tech": 0, "has_video_demo": 0, "has_github": 0}
        with patch("src.analyzer.causal_inference.predict_win_probability", return_value=0.505):
            from src.analyzer.causal_inference import get_counterfactual_advice
            advice = get_counterfactual_advice(features, 0.5)
        assert advice == []

    def test_protects_against_zero_base_score(self):
        features = {"uses_sponsor_tech": 0, "has_video_demo": 1, "has_github": 1}
        with patch("src.analyzer.causal_inference.predict_win_probability", return_value=0.5):
            from src.analyzer.causal_inference import get_counterfactual_advice
            # base_score=0 should be clamped to 0.01 — no ZeroDivisionError
            advice = get_counterfactual_advice(features, 0.0)
        assert isinstance(advice, list)

    def test_multiple_missing_features_yield_multiple_advices(self):
        features = {"uses_sponsor_tech": 0, "has_video_demo": 0, "has_github": 0}
        with patch("src.analyzer.causal_inference.predict_win_probability", return_value=0.9):
            from src.analyzer.causal_inference import get_counterfactual_advice
            advice = get_counterfactual_advice(features, 0.1)
        assert len(advice) == 3
