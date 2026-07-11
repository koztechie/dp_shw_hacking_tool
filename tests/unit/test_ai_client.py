import pytest
from unittest.mock import patch, MagicMock
from src.analyzer.ai_client import _call_api, generate_json_with_failover, mimo_circuit_breaker

@pytest.fixture(autouse=True)
def reset_circuit_breaker():
    """Скидаємо стан Circuit Breaker перед кожним тестом."""
    mimo_circuit_breaker.reset()
    yield

@pytest.fixture
def mock_rate_limiter():
    with patch("src.analyzer.ai_client.check_and_increment", return_value=True) as mock:
        yield mock

@pytest.fixture
def mock_openai():
    with patch("src.analyzer.ai_client.OpenAI") as MockOpenAI:
        mock_client = MagicMock()
        MockOpenAI.return_value = mock_client
        
        # Налаштовуємо успішну відповідь за замовчуванням
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '{"test": "success"}'
        mock_client.chat.completions.create.return_value = mock_response
        
        yield mock_client

class TestAIClient:
    """Тести для AI клієнта та його механізмів антикрихкості."""
    
    def test_call_api_success(self, mock_rate_limiter, mock_openai):
        """Успішний виклик API повертає валідний JSON."""
        result = _call_api(
            api_key="test_key",
            base_url="http://test",
            prompt="Test prompt",
            model="test-model"
        )
        assert result == {"test": "success"}
        mock_openai.chat.completions.create.assert_called_once()
        
    def test_call_api_rate_limit_exceeded(self, mock_openai):
        """Якщо локальний rate limit вичерпано, повертається помилка fallback."""
        with patch("src.analyzer.ai_client.check_and_increment", return_value=False):
            result = _call_api(
                api_key="test_key",
                base_url="http://test",
                prompt="Test prompt",
                model="test-model"
            )
            assert result == {"error": "Local rate limit exceeded", "fallback": True}
            mock_openai.chat.completions.create.assert_not_called()
            
    def test_circuit_breaker_blocks_requests(self, mock_rate_limiter, mock_openai):
        """Якщо Circuit Breaker відкритий, запити блокуються миттєво."""
        mimo_circuit_breaker.record_failure()
        mimo_circuit_breaker.record_failure()
        mimo_circuit_breaker.record_failure()
        
        result = _call_api(
            api_key="test_key",
            base_url="http://test",
            prompt="Test prompt",
            model="test-model"
        )
        
        assert result == {"error": "Circuit breaker is OPEN", "fallback": True}
        mock_openai.chat.completions.create.assert_not_called()
        
    def test_call_api_removes_think_tags(self, mock_rate_limiter, mock_openai):
        """API клієнт успішно видаляє теги <think> перед парсингом JSON."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '<think>some reasoning</think>```json\n{"data": "value"}\n```'
        mock_openai.chat.completions.create.return_value = mock_response
        
        result = _call_api(
            api_key="test_key",
            base_url="http://test",
            prompt="Test prompt",
            model="test-model"
        )
        assert result == {"data": "value"}
        
    def test_call_api_invalid_json_retries(self, mock_rate_limiter, mock_openai):
        """Якщо повернутий JSON невалідний за схемою, API має повторити спробу."""
        # Перший виклик повертає невалідний JSON, другий - валідний
        mock_response_invalid = MagicMock()
        mock_response_invalid.choices = [MagicMock()]
        mock_response_invalid.choices[0].message.content = '{"wrong": "format"}'
        
        mock_response_valid = MagicMock()
        mock_response_valid.choices = [MagicMock()]
        mock_response_valid.choices[0].message.content = '{"title": "Idea", "description": "Desc", "score": 9.5}'
        
        mock_openai.chat.completions.create.side_effect = [
            mock_response_invalid,
            mock_response_valid
        ]
        
        with patch("src.analyzer.prompt_validator.PromptSchemaValidator.validate_response") as mock_validator:
            # Налаштовуємо валідатор так, щоб він зафейлив перший раз і пропустив другий
            mock_validator.side_effect = [
                (False, "Missing fields"),
                (True, "")
            ]
            
            result = _call_api(
                api_key="test_key",
                base_url="http://test",
                prompt="Test prompt",
                model="test-model",
                schema_name="idea",
                max_retries=1
            )
            
            assert mock_openai.chat.completions.create.call_count == 2
            assert result == {"title": "Idea", "description": "Desc", "score": 9.5}

    def test_generate_json_with_failover_success_primary(self, mock_rate_limiter, mock_openai):
        """Перевірка failover логіки: Успішний запит до основного API."""
        with patch("src.analyzer.ai_client._call_api") as mock_call:
            mock_call.return_value = {"success": True}
            
            result = generate_json_with_failover("prompt", "schema")
            assert result == {"success": True}
            mock_call.assert_called_once()
            
    @patch("src.analyzer.ai_client._call_api")
    def test_generate_json_with_failover_uses_fallback(self, mock_call, mock_rate_limiter, mock_openai):
        """Перевірка failover логіки: Перехід на OpenRouter при збої MIMO."""
        # Перший виклик повертає fallback, другий - успіх
        mock_call.side_effect = [
            {"error": "MIMO failed", "fallback": True},
            {"success": "openrouter"}
        ]
        
        with patch("config.settings.MIMO_API_KEY", "test_mimo"), \
             patch("config.settings.OPENROUTER_API_KEY", "test_or"):
            result = generate_json_with_failover("prompt", "schema")
            
        assert result == {"success": "openrouter"}
        assert mock_call.call_count == 2
