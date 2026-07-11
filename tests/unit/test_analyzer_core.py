import pytest
import pandas as pd
from unittest.mock import patch, MagicMock

from src.analyzer.context_manager import ContextWindowManager
from src.analyzer.eda import run_eda

class TestAnalyzerCore:
    """Тести для керування контекстом (ContextWindowManager) та аналітики даних (EDA)."""

    def test_context_window_manager_init(self):
        """Ініціалізація ContextWindowManager з лімітами моделей."""
        cm = ContextWindowManager("mimo-v2.5")
        assert cm.max_tokens == 16000
        assert cm.max_prompt_tokens == 11200

    def test_context_window_manager_count_tokens(self):
        """Підрахунок токенів у тексті."""
        cm = ContextWindowManager("mimo-v2.5-pro")
        tokens = cm.count_tokens("Hello, world!")
        assert tokens > 0

    def test_context_window_manager_truncate_no_need(self):
        """Промпт не потребує обрізання, якщо він менший за ліміт."""
        cm = ContextWindowManager("mimo-v2.5")
        prompt = "Hello {name}"
        variables = {"name": "User"}
        
        final_prompt, truncated_vars = cm.truncate_to_fit(prompt, variables)
        
        assert final_prompt == "Hello User"
        assert truncated_vars["name"] == "User"

    def test_context_window_manager_truncate_needed(self):
        """Обрізання довгих змінних промпту."""
        # Встановимо дуже малий ліміт токенів
        cm = ContextWindowManager("mimo-v2.5")
        cm.max_prompt_tokens = 20 # Дуже маленький ліміт
        
        prompt = "System prompt {description} {constraints}"
        variables = {
            "description": "A very long description that should be truncated to fit the small context window limit.",
            "constraints": "Keep it short"
        }
        
        final_prompt, truncated_vars = cm.truncate_to_fit(prompt, variables)
        
        assert "[TRUNCATED]" in truncated_vars["description"]
        assert truncated_vars["constraints"] == "Keep it short" # Не обрізано через низький пріоритет та малий розмір

    @patch("src.analyzer.eda.duckdb.connect")
    def test_run_eda_empty_db(self, mock_connect):
        """EDA повертає порожній звіт при порожній БД."""
        mock_con = MagicMock()
        mock_df = pd.DataFrame()
        mock_con.execute.return_value.fetchdf.return_value = mock_df
        mock_connect.return_value = mock_con
        
        # Переконуємось, що функція не падає
        run_eda()
        mock_con.close.assert_called_once()

    @patch("src.analyzer.eda.duckdb.connect")
    def test_run_eda_success(self, mock_connect):
        """Успішне проведення EDA на тестових даних."""
        mock_con = MagicMock()
        mock_df = pd.DataFrame({
            "is_winner": [True, False],
            "likes": [10, 2],
            "team_size": [3, 1],
            "tech_count": [4, 1],
            "has_social_angle": [1, 0],
            "uses_sponsor_tech": [1, 0],
            "sponsor_challenge_match": [1, 0],
            "description_length": [100, 20],
            "has_github": [1, 0],
            "readme_length": [1000, 50],
            "commit_count_48h": [5, 0],
            "novelty_score": [0.8, 0.4]
        })
        mock_con.execute.return_value.fetchdf.return_value = mock_df
        mock_connect.return_value = mock_con
        
        run_eda()
        mock_con.close.assert_called_once()

    @patch("src.analyzer.eda.duckdb.connect")
    def test_run_eda_error(self, mock_connect):
        """EDA безпечно виходить при збої бази даних."""
        mock_connect.side_effect = Exception("Connection lost")
        
        # Не має викидати виключення
        run_eda()
