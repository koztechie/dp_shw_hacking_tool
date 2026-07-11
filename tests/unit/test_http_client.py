from unittest.mock import patch, MagicMock
import httpx
from src.scraper.http_client import safe_get

class TestHttpClient:
    """Тести для безпечного HTTP клієнта скрейпера."""
    
    @patch("src.scraper.http_client.httpx.Client")
    def test_safe_get_success(self, mock_client_class):
        """Перевірка успішного запиту (HTTP 200)."""
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client.get.return_value = mock_response
        
        result = safe_get("http://example.com")
        
        assert result == mock_response
        mock_client.get.assert_called_once()
        mock_response.raise_for_status.assert_called_once()

    @patch("src.scraper.http_client.httpx.Client")
    def test_safe_get_404_not_found(self, mock_client_class):
        """Перевірка обробки 404 (повертається відразу, без retry)."""
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_client.get.return_value = mock_response
        
        result = safe_get("http://example.com")
        
        assert result == mock_response
        assert mock_client.get.call_count == 1
        mock_response.raise_for_status.assert_not_called()

    @patch("src.scraper.http_client.time.sleep")
    @patch("src.scraper.http_client.httpx.Client")
    def test_safe_get_429_rate_limit(self, mock_client_class, mock_sleep):
        """Антикрихкість: 429 викликає time.sleep(60) та повторний запит."""
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        
        mock_response_429 = MagicMock()
        mock_response_429.status_code = 429
        
        mock_response_200 = MagicMock()
        mock_response_200.status_code = 200
        
        # Перший виклик повертає 429, другий - 200
        mock_client.get.side_effect = [mock_response_429, mock_response_200]
        
        result = safe_get("http://example.com")
        
        assert result == mock_response_200
        assert mock_client.get.call_count == 2
        mock_sleep.assert_called_once_with(60)

    @patch("src.scraper.http_client.time.sleep")
    @patch("src.scraper.http_client.httpx.Client")
    def test_safe_get_timeout_retries(self, mock_client_class, mock_sleep):
        """Антикрихкість: таймаути мережі викликають експоненційний backoff та вичерпання ліміту."""
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        
        mock_client.get.side_effect = httpx.TimeoutException("Connection timed out")
        
        result = safe_get("http://example.com")
        
        assert result is None
        assert mock_client.get.call_count == 3  # MAX_RETRIES = 3
        assert mock_sleep.call_count == 3

    @patch("src.scraper.http_client.time.sleep")
    @patch("src.scraper.http_client.httpx.Client")
    def test_safe_get_server_error(self, mock_client_class, mock_sleep):
        """Антикрихкість: HTTP 500 викликає retry і повертає None після 3 спроб."""
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        
        mock_response_500 = MagicMock()
        mock_response_500.status_code = 500
        # raise_for_status raises HTTPStatusError
        error = httpx.HTTPStatusError("Server Error", request=MagicMock(), response=mock_response_500)
        mock_response_500.raise_for_status.side_effect = error
        
        mock_client.get.return_value = mock_response_500
        
        result = safe_get("http://example.com")
        
        assert result is None
        assert mock_client.get.call_count == 3
        assert mock_response_500.raise_for_status.call_count == 3
