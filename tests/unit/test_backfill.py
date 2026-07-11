import pytest
import json
from unittest.mock import patch, MagicMock
from bs4 import BeautifulSoup

from src.scraper.backfill_db import run_backfill
from src.scraper.backfill_sponsors import backfill_sponsors, scrape_sponsors_robust

class TestBackfill:
    """Тести для скриптів збагачення даних (backfill_db та backfill_sponsors)."""

    @patch("src.scraper.backfill_db.get_connection")
    @patch("src.scraper.backfill_db.scrape_project_detail")
    def test_run_backfill(self, mock_scrape, mock_db_conn):
        """Успішне збагачення деталей проектів (номінації та статус переможця)."""
        mock_con = MagicMock()
        mock_con.execute.return_value.fetchall.return_value = [
            ("p-001", "https://devpost.com/software/p-001")
        ]
        mock_db_conn.return_value = mock_con

        mock_scrape.return_value = {
            "prize_track": "Best AI Tool"
        }

        with patch("src.scraper.backfill_db.time.sleep"):
            run_backfill()

        mock_con.execute.assert_called()
        mock_con.commit.assert_called()
        mock_con.close.assert_called_once()

    @patch("src.scraper.backfill_db.get_connection")
    def test_run_backfill_error(self, mock_db_conn):
        """Перевірка обробки виключень та rollback у run_backfill."""
        mock_con = MagicMock()
        mock_con.execute.return_value.fetchall.return_value = [
            ("p-001", "https://devpost.com/software/p-001")
        ]
        # Make the UPDATE statement fail by side effect
        mock_con.execute.side_effect = [
            mock_con.execute.return_value, # for SELECT
            Exception("DB error") # for UPDATE
        ]
        mock_db_conn.return_value = mock_con

        run_backfill()
        
        mock_con.rollback.assert_called_once()
        mock_con.close.assert_called_once()

    def test_scrape_sponsors_robust(self):
        """Тест парсингу логотипів спонсорів з HTML."""
        html = """
        <img class="sponsor_logo_img" alt="Google logo" />
        <img class="sponsor_logo_img" alt="Devpost logo" />
        <div id="sponsor-list">
            <img class="sponsor_logo_img" src="aws.png" alt="AWS" />
        </div>
        """
        soup = BeautifulSoup(html, "lxml")
        sponsors = scrape_sponsors_robust(soup)
        
        assert "Google" in sponsors
        assert "AWS" in sponsors
        assert "Devpost" not in sponsors

    @patch("src.scraper.backfill_sponsors.get_connection")
    @patch("src.scraper.backfill_sponsors.safe_get")
    def test_backfill_sponsors_success(self, mock_safe_get, mock_db_conn):
        """Успішне збагачення спонсорів хакатонів."""
        mock_con = MagicMock()
        mock_con.execute.return_value.fetchall.return_value = [
            ("h-001", "https://ai.devpost.com", "AI Hackathon")
        ]
        mock_db_conn.return_value = mock_con

        mock_resp = MagicMock()
        mock_resp.text = '<img class="sponsor_logo_img" alt="Google logo" />'
        mock_safe_get.return_value = mock_resp

        with patch("src.scraper.backfill_sponsors.time.sleep"):
            backfill_sponsors()

        mock_con.execute.assert_called()
        mock_con.close.assert_called_once()
