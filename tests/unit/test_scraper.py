from unittest.mock import patch, MagicMock, mock_open

from src.scraper.hackathon_list_scraper import fetch_ended_hackathons
from src.scraper.hackathon_detail_scraper import scrape_hackathon_detail
from src.scraper.projects_scraper import fetch_hackathon_projects, extract_subdomain
from src.scraper.project_detail_scraper import scrape_project_detail
from src.scraper.github_scraper import get_github_metrics
from src.scraper.trend_scraper import fetch_hacker_news, fetch_arxiv_ai, update_global_trends
from src.scraper.validate_data import validate
from src.scraper.orchestrator import run_full_ingestion

class TestScraperSuite:
    """Тести для модулів скрапінгу (Scraper) та оркерстратора."""

    @patch("src.scraper.hackathon_list_scraper.safe_get")
    def test_fetch_ended_hackathons(self, mock_safe_get):
        """Успішний збір списку закінчених хакатонів."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "hackathons": [
                {"id": 1, "title": "AI Hackathon", "url": "https://ai.devpost.com"},
                {"id": 2, "title": "Web3 Hackathon", "url": "https://web3.devpost.com"}
            ]
        }
        mock_safe_get.return_value = mock_response

        # Зменшимо scrape delay для прискорення тесту
        with patch("src.scraper.hackathon_list_scraper.time.sleep"):
            result = fetch_ended_hackathons(max_pages=1)
            
        assert len(result) == 2
        assert result[0]["title"] == "AI Hackathon"
        mock_safe_get.assert_called_once()

    @patch("src.scraper.hackathon_list_scraper.safe_get")
    def test_fetch_ended_hackathons_fail(self, mock_safe_get):
        """Збій під час збору списку завершених хакатонів."""
        mock_safe_get.return_value = None

        with patch("src.scraper.hackathon_list_scraper.time.sleep"):
            result = fetch_ended_hackathons(max_pages=1)

        assert len(result) == 0

    @patch("src.scraper.hackathon_detail_scraper.safe_get")
    def test_scrape_hackathon_detail(self, mock_safe_get):
        """Успішний парсинг сторінки деталей хакатону."""
        html_content = """
        <div class="prize-amount">$10,000</div>
        <span class="theme-label">AI</span>
        <span class="theme-label">Open Source</span>
        <img class="sponsor_logo_img" alt="Google logo" src="google.png" />
        <img class="sponsor_logo_img" alt="Devpost" src="devpost.png" />
        <div id="judging-criteria">Quality of prototype</div>
        <div class="participants-count">123 participants</div>
        <ul id="eligibility-list">
            <li>Students only</li>
            <li>Team required</li>
        </ul>
        <h1 class="header-image"><img src="banner.png" /></h1>
        """
        mock_response = MagicMock()
        mock_response.text = html_content
        mock_safe_get.return_value = mock_response

        result = scrape_hackathon_detail("https://test.devpost.com")
        
        assert result["prize_total"] == "$10,000"
        assert "AI" in result["themes"]
        assert "Google" in result["sponsors"]
        assert "Devpost" not in result["sponsors"]
        assert result["participant_count"] == 123
        assert result["students_only"] is True
        assert result["team_required"] is True
        assert result["banner_url"] == "banner.png"

    @patch("src.scraper.hackathon_detail_scraper.safe_get")
    def test_scrape_hackathon_detail_error(self, mock_safe_get):
        """Помилка під час збору деталей хакатону."""
        mock_safe_get.return_value = None
        result = scrape_hackathon_detail("https://test.devpost.com")
        assert result == {}

    def test_extract_subdomain(self):
        """Тест вилучення субдомену з URL."""
        assert extract_subdomain("https://ai-hack.devpost.com/") == "ai-hack"
        assert extract_subdomain("http://blockchain.devpost.com") == "blockchain"

    @patch("src.scraper.projects_scraper.safe_get")
    def test_fetch_hackathon_projects(self, mock_safe_get):
        """Успішний парсинг галереї проектів хакатону."""
        html_content = """
        <div class="software-entry">
            <h5>Awesome AI</h5>
            <div class="entry-body"><p>Decentralized AI Assistant</p></div>
            <div class="software-entry-tags">
                <span>Python</span>
                <span>PyTorch</span>
            </div>
            <div class="like-count">15 likes</div>
            <a class="block-wrapper-link" href="/software/awesome-ai-123"></a>
            <div class="winner-badge">Winner</div>
        </div>
        """
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = html_content
        mock_safe_get.return_value = mock_response

        with patch("src.scraper.projects_scraper.time.sleep"):
            # Обмежимо збір 1 сторінкою, повернувши None на наступній
            mock_safe_get.side_effect = [mock_response, None]
            result = fetch_hackathon_projects("test-subdomain")

        assert len(result) == 1
        assert result[0]["title"] == "Awesome AI"
        assert result[0]["likes"] == 15
        assert result[0]["is_winner"] is True
        assert result[0]["project_url"] == "https://devpost.com/software/awesome-ai-123"

    @patch("src.scraper.project_detail_scraper.safe_get")
    def test_scrape_project_detail(self, mock_safe_get):
        """Успішний збір детальної інформації про проект."""
        html_content = """
        <a href="https://github.com/test/repo">GitHub Code</a>
        <div class="app-links"><a href="https://test-demo.com">Live Demo</a></div>
        <div class="members">
            <div class="user-profile">Alice</div>
            <div class="user-profile">Bob</div>
        </div>
        <div>
            <span class="winner">Winner</span>
            Best AI Project
        </div>
        <ul id="built-with">
            <li>Python</li>
            <li>FastAPI</li>
        </ul>
        """
        mock_response = MagicMock()
        mock_response.text = html_content
        mock_safe_get.return_value = mock_response

        result = scrape_project_detail("https://devpost.com/software/awesome-ai")

        assert result["github_url"] == "https://github.com/test/repo"
        assert result["demo_url"] == "https://test-demo.com"
        assert result["team_size"] == 2
        assert "Best AI Project" in result["prize_track"]
        assert "Python" in result["tech_tags"]

    @patch("src.scraper.project_detail_scraper.safe_get")
    def test_scrape_project_detail_invalid_url(self, mock_safe_get):
        """Некоректний URL проекту повертає {}."""
        result = scrape_project_detail("invalid-url")
        assert result == {}
        mock_safe_get.assert_not_called()

    @patch("src.scraper.github_scraper.httpx.get")
    def test_get_github_metrics(self, mock_get):
        """Збір метрик з GitHub API."""
        mock_repo_resp = MagicMock()
        mock_repo_resp.status_code = 200
        mock_repo_resp.json.return_value = {
            "size": 1204,
            "open_issues_count": 5
        }

        mock_readme_resp = MagicMock()
        mock_readme_resp.status_code = 200
        mock_readme_resp.json.return_value = {
            "content": "SGVsbG8gV29ybGQ=" # Base64 Hello World
        }

        from datetime import datetime, timezone
        now_str = datetime.now(timezone.utc).isoformat()
        mock_commits_resp = MagicMock()
        mock_commits_resp.status_code = 200
        mock_commits_resp.json.return_value = [
            {"sha": "12345", "commit": {"committer": {"date": now_str}}}
        ] * 15

        mock_get.side_effect = [mock_repo_resp, mock_readme_resp, mock_commits_resp]

        result = get_github_metrics("https://github.com/user/repo")
        
        assert result["repo_size"] == 1204
        assert result["repo_issues"] == 5
        assert result["readme_length"] == 11
        assert result["commit_count_48h"] == 15

    @patch("src.scraper.trend_scraper.httpx.Client.get")
    def test_fetch_hacker_news(self, mock_get):
        """Збір трендів Hacker News."""
        mock_topstories = MagicMock()
        mock_topstories.json.return_value = [1, 2]
        
        mock_item1 = MagicMock()
        mock_item1.json.return_value = {"title": "Google releases Antigravity AI"}
        
        mock_item2 = MagicMock()
        mock_item2.json.return_value = {"title": "XGBoost 3.3.0 is out"}

        mock_get.side_effect = [mock_topstories, mock_item1, mock_item2]

        trends = fetch_hacker_news()
        assert len(trends) == 2
        assert trends[0] == "Google releases Antigravity AI"

    @patch("src.scraper.trend_scraper.safe_get")
    def test_fetch_arxiv_ai(self, mock_safe_get):
        """Збір публікацій з ArXiv (XML-парсинг)."""
        arxiv_xml = """<?xml version="1.0" encoding="UTF-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
            <entry>
                <title>Deep reinforcement learning in MLOps</title>
            </entry>
        </feed>
        """
        mock_resp = MagicMock()
        mock_resp.text = arxiv_xml
        mock_safe_get.return_value = mock_resp

        papers = fetch_arxiv_ai()
        assert len(papers) == 1
        assert papers[0] == "Deep reinforcement learning in MLOps"

    @patch("src.scraper.trend_scraper.fetch_arxiv_ai")
    @patch("src.scraper.trend_scraper.fetch_hacker_news")
    def test_update_global_trends(self, mock_hn, mock_arxiv):
        """Оновлення та кешування глобальних трендів."""
        mock_hn.return_value = ["Trend 1"]
        mock_arxiv.return_value = ["Paper 1"]

        # Замокуємо відкриття файлу для запису
        m = mock_open()
        with patch("src.scraper.trend_scraper.open", m), \
             patch("src.scraper.trend_scraper.Path.mkdir"):
            update_global_trends()
        
        # Перевіримо, чи відбувся запис
        m.assert_called_once()

    @patch("src.scraper.trend_scraper.httpx.Client.get")
    def test_fetch_hacker_news_error(self, mock_get):
        """Hacker News збір обробляє помилки API."""
        mock_get.side_effect = Exception("API error")
        trends = fetch_hacker_news()
        assert trends == []

    @patch("src.scraper.trend_scraper.safe_get")
    def test_fetch_arxiv_ai_error(self, mock_safe_get):
        """ArXiv збір обробляє помилки API."""
        mock_safe_get.side_effect = Exception("Network error")
        papers = fetch_arxiv_ai()
        assert papers == []

    @patch("src.scraper.validate_data.duckdb.connect")
    def test_validate(self, mock_connect):
        """Перевірка аналітики бази даних DuckDB."""
        mock_con = MagicMock()
        mock_con.execute.return_value.fetchone.side_effect = [
            (5,), # hackathons count
            (100,), # projects count
            (20,), # winners count
            (0.20,) # win rate
        ]
        mock_con.execute.return_value.fetchall.return_value = [
            ("Python", 15),
            ("FastAPI", 10)
        ]
        mock_connect.return_value = mock_con

        # Патчимо шлях, щоб існував
        with patch("src.scraper.validate_data.Path.exists", return_value=True):
            validate()
        
        mock_connect.assert_called_once()
        mock_con.close.assert_called_once()

    def test_validate_no_db(self):
        """validate повертає None, якщо файл БД не існує."""
        with patch("src.scraper.validate_data.Path.exists", return_value=False):
            validate()

    @patch("src.scraper.validate_data.duckdb.connect")
    def test_validate_empty_result(self, mock_connect):
        """validate обробляє порожній список технологій переможців."""
        mock_con = MagicMock()
        mock_con.execute.return_value.fetchone.side_effect = [
            (5,),
            (100,),
            (20,),
            (0.20,)
        ]
        mock_con.execute.return_value.fetchall.return_value = []
        mock_connect.return_value = mock_con

        with patch("src.scraper.validate_data.Path.exists", return_value=True):
            validate()

    @patch("src.scraper.validate_data.duckdb.connect")
    def test_validate_error(self, mock_connect):
        """validate обробляє виключення під час зчитування."""
        mock_connect.side_effect = Exception("duckdb error")
        with patch("src.scraper.validate_data.Path.exists", return_value=True):
            validate()

    @patch("src.scraper.orchestrator.get_connection")
    @patch("src.scraper.orchestrator.fetch_ended_hackathons")
    @patch("src.scraper.orchestrator.scrape_hackathon_detail")
    @patch("src.scraper.orchestrator.fetch_hackathon_projects")
    @patch("src.scraper.orchestrator.scrape_project_detail")
    @patch("src.scraper.orchestrator.get_github_metrics")
    def test_orchestrator_run_full_ingestion(self, mock_github, mock_pdetail, mock_projects, mock_hdetail, mock_list, mock_db_conn):
        """Повний інтеграційний сценарій оркестратора."""
        # 1. Список хакатонів
        mock_list.return_value = [{
            "url": "https://ai-hack.devpost.com",
            "title": "AI Hackathon",
            "organization_name": "Google",
            "submission_period_dates": "2026-07-10 to 2026-07-11"
        }]

        # 2. Деталі хакатону
        mock_hdetail.return_value = {
            "prize_total": "$5,000",
            "participant_count": 50,
            "themes": ["AI"],
            "sponsors": ["Google"],
            "judging_criteria": "Creativity",
            "banner_url": "banner.png"
        }

        # 3. Список проектів хакатону
        mock_projects.return_value = [{
            "title": "Pennywise",
            "description": "Financial Assistant",
            "tech_tags": ["Python"],
            "likes": 10,
            "project_url": "https://devpost.com/software/pennywise",
            "is_winner": True
        }]

        # 4. Деталі проекту
        mock_pdetail.return_value = {
            "github_url": "https://github.com/pennywise",
            "demo_url": "demo.com",
            "team_size": 2,
            "prize_track": "Best AI",
            "tech_tags": ["Python", "FastAPI"]
        }

        # 5. Метрики GitHub
        mock_github.return_value = {
            "readme_length": 500,
            "commit_count_48h": 5
        }

        # 6. База даних (немає хакатону в базі)
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchone.return_value = None
        mock_db_conn.return_value = mock_conn

        with patch("src.scraper.orchestrator.init_db"), \
             patch("src.scraper.orchestrator.time.sleep"):
            run_full_ingestion(max_pages=1)

        # Переконуємося, що були виконані INSERT запити
        assert mock_conn.execute.call_count >= 3
        mock_conn.commit.assert_called_once()
