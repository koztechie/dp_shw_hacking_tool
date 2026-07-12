import pandas as pd
import numpy as np
from unittest.mock import patch, MagicMock

from src.ml.drift_detector import calculate_psi, trigger_retraining, detect_drift

class TestDriftDetector:
    """Тести для системи виявлення дрейфу даних (Data Drift Detection)."""

    def test_calculate_psi_no_drift(self):
        """PSI для однакових розподілів має бути близьким до нуля."""
        expected = pd.DataFrame({"feat1": np.random.normal(0, 1, 1000)})
        actual = pd.DataFrame({"feat1": np.random.normal(0, 1, 1000)})
        
        psi = calculate_psi(expected, actual, buckets=10)
        assert psi < 0.1

    def test_calculate_psi_with_drift(self):
        """PSI для суттєво змінених розподілів має бути високим."""
        expected = pd.DataFrame({"feat1": np.random.normal(0, 1, 1000)})
        actual = pd.DataFrame({"feat1": np.random.normal(2, 1, 1000)}) # зміщене середнє
        
        psi = calculate_psi(expected, actual, buckets=10)
        assert psi > 0.2

    @patch("src.ml.drift_detector.logger")
    @patch("src.ml.train_ensemble.train_ensemble")
    def test_trigger_retraining(self, mock_train, mock_logger):
        """Перевірка виклику перенавчання."""
        trigger_retraining()
        mock_train.assert_called_once()
        mock_logger.info.assert_any_call("✅ Модель успішно перетренована!")

    @patch("src.ml.drift_detector.duckdb.connect")
    def test_detect_drift_database_error(self, mock_connect):
        """При помилці DuckDB метод повертає False."""
        mock_connect.side_effect = Exception("Locked database error")
        result = detect_drift()
        assert result is False

    @patch("src.ml.drift_detector.duckdb.connect")
    def test_detect_drift_too_few_rows(self, mock_connect):
        """При недостатній кількості рядків (<500) дрейф не перевіряється."""
        mock_con = MagicMock()
        mock_df = pd.DataFrame({"description_length": [10] * 100}) # 100 rows
        mock_con.execute.return_value.fetchdf.return_value = mock_df
        mock_connect.return_value = mock_con

        result = detect_drift()
        assert result is False
        mock_con.close.assert_called_once()

    @patch("src.ml.drift_detector.duckdb.connect")
    def test_detect_drift_no_drift_large_dataset(self, mock_connect):
        """Великий датасет без дрейфу не викликає перенавчання."""
        mock_con = MagicMock()
        # Створюємо 600 рядків стабільних даних
        data = {
            "description_length": np.random.randint(100, 500, 600),
            "tech_count": np.random.randint(1, 10, 600),
            "novelty_score": np.random.uniform(0.1, 0.9, 600),
            "prize_numeric": np.random.uniform(100, 10000, 600),
            "uses_sponsor_tech": [1, 0] * 300,
            "has_video_demo": [0, 1] * 300,
            "has_github": [1, 1] * 300,
            "likes": np.random.randint(0, 50, 600),
            "scraped_at": pd.date_range("2026-01-01", periods=600)
        }
        mock_df = pd.DataFrame(data)
        mock_con.execute.return_value.fetchdf.return_value = mock_df
        mock_connect.return_value = mock_con

        result = detect_drift()
        assert result is False

    @patch("src.ml.drift_detector.duckdb.connect")
    def test_detect_drift_with_drift_triggered(self, mock_connect):
        """Значні зміни у розподілі даних викликають автоматичне перенавчання."""
        mock_con = MagicMock()
        # Створюємо 1000 рядків, де останні 200 мають дрейф (наприклад, суттєво більше лайків та довжини опису)
        ref_data = {
            "description_length": np.random.randint(10, 50, 800),
            "tech_count": np.random.randint(1, 3, 800),
            "novelty_score": np.random.uniform(0.1, 0.2, 800),
            "prize_numeric": np.random.uniform(10, 100, 800),
            "uses_sponsor_tech": [0] * 800,
            "has_video_demo": [0] * 800,
            "has_github": [0] * 800,
            "likes": np.random.randint(0, 5, 800),
            "scraped_at": pd.date_range("2026-01-01", periods=800)
        }
        
        curr_data = {
            "description_length": np.random.randint(500, 1000, 200),
            "tech_count": np.random.randint(10, 20, 200),
            "novelty_score": np.random.uniform(0.8, 0.9, 200),
            "prize_numeric": np.random.uniform(1000, 10000, 200),
            "uses_sponsor_tech": [1] * 200,
            "has_video_demo": [1] * 200,
            "has_github": [1] * 200,
            "likes": np.random.randint(100, 500, 200),
            "scraped_at": pd.date_range("2026-03-01", periods=200)
        }
        
        df_ref = pd.DataFrame(ref_data)
        df_curr = pd.DataFrame(curr_data)
        mock_df = pd.concat([df_ref, df_curr], ignore_index=True)
        
        mock_con.execute.return_value.fetchdf.return_value = mock_df
        mock_connect.return_value = mock_con

        result = detect_drift()
        assert result is True
