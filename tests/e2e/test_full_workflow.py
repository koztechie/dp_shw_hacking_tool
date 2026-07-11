import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch

from src.api.main import app

class TestE2EWorkflow:
    """End-to-End (E2E) тести для перевірки повного циклу обробки."""
    
    @pytest.fixture
    def client(self):
        return TestClient(app)

    @patch("src.analyzer.pipeline.analyze_hackathon")
    def test_full_analysis_workflow(self, mock_analyze, client):
        """Перевірка E2E процесу: запит -> аналізатор -> відповідь."""
        # Імітуємо успішний результат від аналізатора (pipeline)
        expected_result = {
            "prediction_id": "test_id_12345",
            "hackathon_info": {"title": "Test Hackathon", "participants": 100},
            "winning_ideas": [{"title": "Idea 1", "tech_stack": ["Python"]}],
            "techspec": {"project_name": "Idea 1"}
        }
        mock_analyze.return_value = expected_result
        
        # 1. Відправляємо POST-запит з клієнта
        # Запит використовує Form(...), тому відправляємо як data
        payload = {
            "url": "https://test.devpost.com"
        }
        headers = {
            "Origin": "http://localhost:8000",
            "x-api-key": "test_key_12345"
        }
        
        import os
        from unittest.mock import patch
        
        with patch.dict(os.environ, {"API_SECRET_KEY": "test_key_12345"}):
            response = client.post("/analyze/url", data=payload, headers=headers)
            
            # 2. Перевіряємо результат
            assert response.status_code == 200
        
        data = response.json()
        assert data["status"] == "success"
        assert data["prediction_id"] == "test_id_12345"
        
        # Перевіряємо, що метод був викликаний з правильними параметрами
        mock_analyze.assert_called_once_with("https://test.devpost.com")
