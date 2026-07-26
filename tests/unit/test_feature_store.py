import pandas as pd
from unittest.mock import patch, MagicMock
from src.ml.feature_store import LightweightFeatureStore

class TestFeatureStore:
    """Тести для Feature Store ( snapshot, data quality monitoring, training data retrieval)."""

    @patch("src.ml.feature_store.duckdb.connect")
    @patch("src.ml.feature_store.STORE_DIR")
    def test_snapshot_features_success(self, mock_store_dir, mock_connect):
        mock_con = MagicMock()
        mock_connect.return_value = mock_con
        mock_store_dir.__truediv__.return_value = MagicMock()
        
        fs = LightweightFeatureStore()
        path = fs.snapshot_features()
        
        assert path != ""
        mock_con.execute.assert_called_once()
        mock_con.close.assert_called_once()

    @patch("src.ml.feature_store.duckdb.connect")
    def test_snapshot_features_error(self, mock_connect):
        mock_connect.side_effect = Exception("Copy failed")
        
        fs = LightweightFeatureStore()
        path = fs.snapshot_features()
        
        assert path == ""

    @patch("src.ml.feature_store.duckdb.connect")
    @patch("src.ml.feature_store.sentry_sdk")
    def test_get_training_data_and_monitoring(self, mock_sentry, mock_connect):
        mock_con = MagicMock()
        
        # Створюємо синтетичні дані, які тригерять усі Quality Alerts
        df = pd.DataFrame({
            "uses_sponsor_tech": [0.0] * 10,
            "tech_count": [1] * 10,
            "has_social_angle": [0] * 10,
            "description_length": [100] * 10,
            "has_github": [0.0] * 10, # mean < 0.05
            "readme_length": [0] * 10,
            "commit_count_48h": [0] * 10,
            "novelty_score": [0.5] * 10,
            "sponsor_challenge_match": [0] * 10,
            "has_video_demo": [0] * 10,
            "competition_density": [1.0] * 10,
            "prize_numeric": [100] * 10,
            "semantic_pca_1": [0.1] * 10, # var = 0
            "semantic_pca_2": [0.2] * 10,
            "semantic_pca_3": [0.3] * 10,
            "github_stars": [0] * 10,
            "likes": [5] * 10,
            "team_size": [2] * 10,
            "is_winner": [0] * 10
        })
        mock_con.execute.return_value.fetch_arrow_table.return_value.to_pandas.return_value = df
        mock_connect.return_value = mock_con
        
        fs = LightweightFeatureStore()
        result_df = fs.get_training_data()
        
        assert len(result_df) == 10
        assert mock_sentry.capture_message.call_count == 3
        mock_con.close.assert_called_once()
