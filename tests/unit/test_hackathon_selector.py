import pytest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
from src.analyzer.hackathon_selector import (
    clean_prize,
    parse_days_left,
    fetch_page,
    fetch_detail_page,
    get_best_hackathon_async,
    CACHE_KEY
)

class TestHackathonSelector:
    def test_clean_prize(self):
        assert clean_prize("$10,000") == 10000.0
        assert clean_prize("<b>$1,500.50</b>") == 1500.5
        assert clean_prize("non-cash") == 0.0
        assert clean_prize("") == 0.0
        assert clean_prize(None) == 0.0

    def test_parse_days_left(self):
        assert parse_days_left("1 month") == 30.0
        assert parse_days_left("about 2 months left") == 60.0
        assert parse_days_left("10 days left") == 10.0
        assert parse_days_left("about 24 hours left") == 1.0
        assert parse_days_left("12 hours") == 0.5
        assert parse_days_left("30 minutes") == 30 / 1440.0
        assert parse_days_left("unknown") == 30.0
        assert parse_days_left("") == 30.0
        assert parse_days_left(None) == 30.0

    @pytest.mark.anyio
    async def test_fetch_page_success(self):
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {"hackathons": [{"title": "Test"}]}
        mock_client.get.return_value = mock_response

        res = await fetch_page(mock_client, 1)
        assert len(res) == 1
        assert res[0]["title"] == "Test"

    @pytest.mark.anyio
    async def test_fetch_detail_page_success(self):
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.text = "<html><body>Welcome to hackathon. It is great.</body></html>"
        mock_client.get.return_value = mock_response

        candidate = {"url": "http://test.com", "title": "Test"}
        res = await fetch_detail_page(mock_client, candidate)
        assert res is not None
        assert "details_text" in res
        assert "welcome" in res["details_text"]

    @pytest.mark.anyio
    async def test_fetch_detail_page_rejection_student(self):
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.text = "<html><body>Must be a student to apply.</body></html>"
        mock_client.get.return_value = mock_response

        candidate = {"url": "http://test.com"}
        res = await fetch_detail_page(mock_client, candidate)
        assert res is None

    @pytest.mark.anyio
    async def test_fetch_detail_page_rejection_ukraine(self):
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.text = "<html><body>Residents of Ukraine are not eligible.</body></html>"
        mock_client.get.return_value = mock_response

        candidate = {"url": "http://test.com"}
        res = await fetch_detail_page(mock_client, candidate)
        assert res is None

    @pytest.mark.anyio
    @patch("src.analyzer.hackathon_selector.get_cached")
    async def test_get_best_hackathon_async_uses_cache(self, mock_get_cached):
        import time
        mock_get_cached.return_value = {
            "timestamp": time.time(),
            "data": {"best_hackathon_title": "Cached Hackathon"}
        }

        res = await get_best_hackathon_async()
        assert res["best_hackathon_title"] == "Cached Hackathon"

    @pytest.mark.anyio
    @patch("src.analyzer.hackathon_selector._calculate_best_hackathon_impl")
    @patch("src.analyzer.hackathon_selector.get_cached")
    @patch("src.analyzer.hackathon_selector.set_cache")
    async def test_get_best_hackathon_async_calculates_if_no_cache(self, mock_set_cache, mock_get_cached, mock_impl):
        mock_get_cached.return_value = None
        mock_impl.return_value = {"best_hackathon_title": "Freshly Calculated"}

        res = await get_best_hackathon_async()
        assert res["best_hackathon_title"] == "Freshly Calculated"
        mock_set_cache.assert_called_once()
        
    @pytest.mark.anyio
    @patch("src.analyzer.hackathon_selector.fetch_page")
    @patch("src.analyzer.hackathon_selector.fetch_detail_page")
    @patch("src.analyzer.hackathon_selector.generate_json_with_failover")
    async def test_calculate_best_hackathon_impl(self, mock_generate, mock_fetch_detail, mock_fetch_page):
        # We need to test the implementation to boost coverage
        from src.analyzer.hackathon_selector import _calculate_best_hackathon_impl
        
        # Mock pages
        mock_fetch_page.return_value = [
            {
                "title": "Good Hackathon",
                "url": "http://good.com",
                "displayed_location": "Online",
                "invite_only": False,
                "prize_amount": "$100,000",
                "registrations_count": 50,
                "time_left_to_submission": "10 days left"
            },
            {
                "title": "Bad Hackathon",
                "url": "http://bad.com",
                "displayed_location": "In-Person", # Should be ignored
                "prize_amount": "$5,000"
            }
        ]
        
        # Detail mock
        mock_fetch_detail.side_effect = lambda c, cand: cand
        
        # AI mock
        mock_generate.return_value = {
            "best_hackathon_title": "Good Hackathon",
            "best_hackathon_url": "http://good.com",
            "win_probability_score": 99.9,
            "scientific_reasoning": "Highest EV."
        }
        
        res = await _calculate_best_hackathon_impl()
        assert res is not None
        assert res["best_hackathon_title"] == "Good Hackathon"
