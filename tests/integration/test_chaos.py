import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
import duckdb

from src.api.main import app
from src.analyzer.ai_client import generate_json_with_failover

class TestChaosEngineering:
    """Хаос-тестування: перевірка стійкості (Antifragility) при відмовах."""

    @pytest.fixture
    def client(self):
        return TestClient(app)

    @pytest.fixture
    def auth_headers(self):
        return {
            "Origin": "http://localhost:8000",
            "x-api-key": "test_key_12345"
        }

    @patch("src.db.duckdb.connect")
    def test_database_locked_chaos(self, mock_db_connect, client, auth_headers):
        """Симуляція: База даних заблокована іншим процесом (IO Exception)."""
        # Імітуємо помилку читання БД
        mock_db_connect.side_effect = duckdb.IOException("IO Error: File is locked")
        
        # Перевіряємо health check (повинен повернути 503 Service Unavailable)
        health_resp = client.get("/health", headers=auth_headers)
        assert health_resp.status_code == 503
        
        data = health_resp.json()
        assert data["status"] == "critical"
        assert data["components"]["database"]["status"] == "error"
        assert "locked" in data["components"]["database"]["details"]["error"]

    @patch("src.analyzer.ai_client._call_api")
    def test_llm_api_timeout_chaos(self, mock_call_api):
        """Симуляція: MiMo та OpenRouter повністю лягли (Timeout/500)."""
        # Імітуємо повернення помилки від _call_api
        mock_call_api.return_value = {"error": "Connection timed out", "fallback": True}
        
        # Функція повинна відловити таймаут, Circuit Breaker має спрацювати,
        # і ми повинні отримати Offline-відповідь (або порожній JSON)
        result = generate_json_with_failover(
            prompt="Test prompt"
        )
        
        # Переконуємось, що Circuit breaker включився і повернув резервний результат, а не впав з помилкою
        assert isinstance(result, dict)
        assert mock_call_api.call_count > 0 # Були спроби

    @patch("src.scraper.http_client.httpx.Client.get")
    def test_scraper_network_failure(self, mock_get):
        """Симуляція: Devpost впав або блокує наші IP (Network Error)."""
        import httpx
        from src.scraper.http_client import safe_get
        
        mock_get.side_effect = httpx.ConnectError("Connection Refused")
        
        # Скрейпер має мати механізм retry і в результаті повернути None або пустий рядок,
        # не зламавши весь пайплайн
        resp = safe_get("https://devpost.com/test")
        assert resp is None

    @patch("src.utils.memory_guard.psutil.virtual_memory")
    def test_memory_leak_chaos(self, mock_vm):
        """Симуляція: У сервера раптово закінчилась пам'ять (AMD A4 issue)."""
        from src.utils.memory_guard import MemoryGuard
        
        # 98% пам'яті зайнято
        mock_vm.return_value = MagicMock(percent=98.0)
        
        # Перевіряємо чи спрацює блокування
        @MemoryGuard.memory_aware("heavy_ml_task")
        def heavy_task():
            return "Should not execute"
            
        with pytest.raises(MemoryError, match="Insufficient memory"):
            heavy_task()
