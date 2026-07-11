import pytest
import pandas as pd
import numpy as np
from unittest.mock import patch, MagicMock

from src.analyzer.assets_generator import generate_project_assets
from src.scraper.realtime_news import get_realtime_sponsor_news
from src.analyzer.techspec_pipeline import generate_and_save_techspec
from src.analyzer.batch_features import run_batch_feature_extraction

class TestAnalyzerExtra:
    """Додаткові тести для генератора ассетів, Real-time новин та пайплайнів ТЗ."""

    @patch("src.analyzer.assets_generator.generate_json_with_failover")
    def test_generate_project_assets_success(self, mock_failover):
        """Успішна генерація ассетів коду та промптів."""
        mock_failover.return_value = {
            "bash_setup_script": "mkdir test",
            "ui_prompts": ["dashboard UI"],
            "video_prompts": ["intro animation"]
        }
        techspec = {"project_name": "Test project"}
        
        result = generate_project_assets(techspec)
        
        assert result["bash_setup_script"] == "mkdir test"
        mock_failover.assert_called_once()

    @patch("src.analyzer.assets_generator.generate_json_with_failover")
    def test_generate_project_assets_fallback(self, mock_failover):
        """Фоллбек при збої AI-генератора ассетів."""
        mock_failover.return_value = {"fallback": True}
        techspec = {"project_name": "Test project"}
        
        result = generate_project_assets(techspec)
        
        assert "fallback" not in result
        assert "bash_setup_script" in result
        assert "dashboard" in result["ui_prompts"][0].lower()

    @patch("src.scraper.realtime_news.safe_get")
    def test_get_realtime_sponsor_news(self, mock_safe_get):
        """Успішне отримання JIT-новин про спонсорів."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "hits": [
                {"title": "OpenAI releases GPT-5"},
                {"title": "GPT-5 API details"}
            ]
        }
        mock_safe_get.return_value = mock_response

        news = get_realtime_sponsor_news(["OpenAI"])
        
        assert "GPT-5" in news
        assert mock_safe_get.call_count == 1

    @patch("src.scraper.realtime_news.safe_get")
    def test_get_realtime_sponsor_news_empty(self, mock_safe_get):
        """Обробка порожнього списку новин."""
        mock_safe_get.return_value = None
        news = get_realtime_sponsor_news(["NonExistentSponsor"])
        assert "No recent breaking news" in news

    @patch("src.analyzer.techspec_pipeline.get_connection")
    @patch("src.analyzer.techspec_pipeline.get_realtime_sponsor_news")
    @patch("src.analyzer.techspec_pipeline.generate_techspec")
    @patch("src.analyzer.techspec_pipeline.get_cached")
    @patch("src.analyzer.techspec_pipeline.set_cache")
    def test_generate_and_save_techspec_no_cache(self, mock_set, mock_get_cached, mock_gen_spec, mock_news, mock_db_conn):
        """Генерація ТЗ з нуля (без кешу) та збереження в БД."""
        mock_get_cached.return_value = None
        mock_news.return_value = "OpenAI updates"
        mock_gen_spec.return_value = {"tech_stack": "FastAPI"}
        
        mock_con = MagicMock()
        mock_con.execute.return_value.fetchone.return_value = (
            '{"sponsor_tech_used": ["OpenAI"]}', # idea JSON
            '["OpenAI"]' # sponsors list raw
        )
        mock_db_conn.return_value = mock_con

        spec = generate_and_save_techspec("pred-123", 1, "https://hack.com")
        
        assert spec["tech_stack"] == "FastAPI"
        mock_gen_spec.assert_called_once()
        mock_con.commit.assert_called_once()
        mock_con.close.assert_called_once()

    @patch("src.utils.memory_guard.MemoryGuard.check_memory")
    @patch("src.analyzer.batch_features.get_connection")
    @patch("src.analyzer.batch_features.EmbedderSingleton.get_model")
    @patch("src.analyzer.batch_features.extract_features")
    @patch("src.analyzer.batch_features.EmbedderSingleton.cleanup")
    def test_run_batch_feature_extraction(self, mock_cleanup, mock_extract, mock_get_model, mock_db_conn, mock_check_mem):
        """Успішне пакетне вилучення ознак для бази даних."""
        mock_check_mem.return_value = True
        
        # Мок для хакатонів
        mock_con = MagicMock()
        mock_hackathons_df = pd.DataFrame({
            "id": ["h1"],
            "title": ["Hack Neon"],
            "organizer": ["Google"]
        })
        mock_projects_df = pd.DataFrame({
            "id": ["p1"],
            "description": ["Cool project description"],
            "hackathon_id": ["h1"]
        })
        
        mock_con.execute.return_value.fetchdf.side_effect = [
            mock_hackathons_df,
            mock_projects_df
        ]
        mock_db_conn.return_value = mock_con

        # Мок для embedder та extract_features
        mock_embedder = MagicMock()
        mock_embedder.encode.return_value = np.random.normal(0, 1, (4, 384)) # 4 embeds to pass PCA > 3 condition
        mock_get_model.return_value = mock_embedder
        
        # Додамо ще описи, щоб len(descriptions) > 3 пройшов
        mock_projects_df_large = pd.DataFrame({
            "id": ["p1", "p2", "p3", "p4"],
            "description": ["desc1", "desc2", "desc3", "desc4"],
            "hackathon_id": ["h1"] * 4
        })
        mock_con.execute.return_value.fetchdf.side_effect = [
            mock_hackathons_df,
            mock_projects_df_large
        ]

        mock_extract.return_value = {
            "uses_sponsor_tech": 1, "tech_count": 5, "has_social_angle": 0,
            "description_length": 25, "has_github": 1, "readme_length": 100,
            "commit_count_48h": 2, "sponsor_challenge_match": 1,
            "has_video_demo": 1, "competition_density": 0.5, "prize_numeric": 500,
            "github_stars": 10, "repo_size": 2048, "repo_issues": 1,
            "days_before_deadline": 2, "prize_per_team": 250, "organizer_reputation": 5
        }

        run_batch_feature_extraction()
        
        mock_get_model.assert_called_once()
        mock_extract.assert_called()
        mock_con.commit.assert_called_once()
        mock_cleanup.assert_called_once()
        mock_con.close.assert_called_once()
