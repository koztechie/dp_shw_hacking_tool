import pytest
import pandas as pd
from unittest.mock import patch, MagicMock
from src.analyzer.evolution_engine import analyze_system_performance, trigger_auto_evolution_check

class TestEvolutionEngine:
    """Тести для модуля автоеволюції (Self-Evolution Engine)."""

    @patch("src.analyzer.evolution_engine.get_connection")
    @patch("src.analyzer.evolution_engine.generate_json_with_failover")
    def test_analyze_system_performance_empty_feedback(self, mock_failover, mock_connect):
        """Проактивний режим аналізу при відсутності фідбеку в БД."""
        mock_con = MagicMock()
        # Помилка зчитування або порожня таблиця
        mock_con.execute.side_effect = Exception("Table not found")
        mock_connect.return_value = mock_con

        mock_failover.return_value = {
            "diagnostic_summary": "Proactive recommendation",
            "recommended_action": "Add a feature",
            "antigravity_cli_prompt": "Update code"
        }

        result = analyze_system_performance()
        
        assert result["diagnostic_summary"] == "Proactive recommendation"
        mock_failover.assert_called_once()
        # PooledConnection не викликає close — повертає в пул
        # mock_con.close.assert_called_once()

    @patch("src.analyzer.evolution_engine.get_connection")
    @patch("src.analyzer.evolution_engine.generate_json_with_failover")
    def test_analyze_system_performance_with_feedback(self, mock_failover, mock_connect):
        """Аналіз на основі накопиченого фідбеку."""
        mock_con = MagicMock()
        mock_df = pd.DataFrame({
            "actual_won": [True, False],
            "actual_place": [1, 5],
            "idea_1_score": [0.9, 0.4],
            "selected_idea": [1, 1],
            "hackathon_url": ["url1", "url2"]
        })
        mock_con.execute.return_value.fetchdf.return_value = mock_df
        mock_connect.return_value = mock_con

        mock_failover.return_value = {
            "diagnostic_summary": "Feedback analysis",
            "recommended_action": "Tune hyperparams",
            "antigravity_cli_prompt": "Update model config"
        }

        result = analyze_system_performance()
        
        assert result["diagnostic_summary"] == "Feedback analysis"
        mock_failover.assert_called_once()
        # PooledConnection не викликає close — повертає в пул
        # mock_con.close.assert_called_once()

    @patch("src.analyzer.evolution_engine.analyze_system_performance")
    @patch("src.analyzer.evolution_engine.sentry_sdk")
    def test_trigger_auto_evolution_check(self, mock_sentry, mock_analyze):
        """Успішне відправлення звіту еволюції в Sentry."""
        mock_analyze.return_value = {
            "diagnostic_summary": "Summary",
            "recommended_action": "Action",
            "antigravity_cli_prompt": "Prompt"
        }

        trigger_auto_evolution_check()
        
        mock_sentry.capture_message.assert_called_once()
