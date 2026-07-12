from unittest.mock import patch
from src.scraper.app_store_scraper import search_itunes, search_duckduckgo_play_store, check_existing_apps

class MockResponse:
    def __init__(self, json_data, status_code, text=""):
        self.json_data = json_data
        self.status_code = status_code
        self.text = text

    def json(self):
        return self.json_data

class TestAppStoreScraper:
    @patch("src.scraper.app_store_scraper.httpx.get")
    def test_search_itunes_success(self, mock_get):
        mock_get.return_value = MockResponse({"results": [{"trackName": "App 1", "description": "Desc 1", "trackViewUrl": "url1"}]}, 200)
        res = search_itunes("query")
        assert len(res) == 1
        assert res[0]["title"] == "App 1"

    @patch("src.scraper.app_store_scraper.httpx.get")
    def test_search_itunes_error(self, mock_get):
        mock_get.side_effect = Exception("Network Error")
        res = search_itunes("query")
        assert res == []

    @patch("src.scraper.app_store_scraper.httpx.post")
    def test_search_ddg_success(self, mock_post):
        html = """<div><h2 class='result__title'>Play App</h2><a class='result__snippet'>snippet</a><a class='result__url' href='url2'></a></div>"""
        mock_post.return_value = MockResponse(None, 200, text=html)
        res = search_duckduckgo_play_store("query")
        assert len(res) == 1
        assert res[0]["title"] == "Play App"

    @patch("src.scraper.app_store_scraper.httpx.post")
    def test_search_ddg_error(self, mock_post):
        mock_post.side_effect = Exception("Network Error")
        res = search_duckduckgo_play_store("query")
        assert res == []

    @patch("src.scraper.app_store_scraper.search_itunes")
    @patch("src.scraper.app_store_scraper.search_duckduckgo_play_store")
    def test_check_existing_apps(self, mock_ddg, mock_itunes):
        mock_itunes.return_value = [{"title": "A"}]
        mock_ddg.return_value = [{"title": "B"}]
        res = check_existing_apps("query")
        assert len(res) == 2
