import pytest
import time

from src.analyzer.ai_client import CircuitBreaker

class TestCircuitBreaker:
    """Тести для Circuit Breaker pattern."""
    
    def test_initial_state_closed(self):
        """Circuit Breaker починається в закритому стані."""
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=300)
        assert cb.is_open() is False
        assert cb.failure_count == 0
    
    def test_opens_after_threshold_failures(self):
        """Circuit Breaker відкривається після досягнення порогу помилок."""
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=300)
        
        # Симулюємо 3 помилки
        cb.record_failure()
        assert cb.failure_count == 1
        assert cb.is_open() is False
        
        cb.record_failure()
        assert cb.failure_count == 2
        assert cb.is_open() is False
        
        cb.record_failure()
        assert cb.failure_count == 3
        assert cb.is_open() is True
    
    def test_stays_open_during_recovery_timeout(self):
        """Circuit Breaker залишається відкритим протягом recovery timeout."""
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=2)  # 2 секунди
        
        # Відкриваємо
        cb.record_failure()
        cb.record_failure()
        assert cb.is_open() is True
        
        # Перевіряємо через 1 секунду - все ще відкритий
        time.sleep(1)
        assert cb.is_open() is True
        
        # Перевіряємо через 2 секунди - переходить в half-open
        time.sleep(1.5)
        assert cb.is_open() is False  # Half-open стан
    
    def test_resets_on_success(self):
        """Circuit Breaker скидається після успішного виклику."""
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=300)
        
        # Відкриваємо
        cb.record_failure()
        cb.record_failure()
        assert cb.is_open() is True
        
        # Скидаємо
        cb.reset()
        assert cb.is_open() is False
        assert cb.failure_count == 0
    
    def test_call_success_resets_counter(self):
        """Успішний виклик через call() скидає лічильник помилок."""
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=300)
        
        # Додаємо помилки
        cb.record_failure()
        cb.record_failure()
        assert cb.failure_count == 2
        
        # Успішний виклик
        def success_func():
            return "success"
        
        result = cb.call(success_func)
        assert result == "success"
        assert cb.failure_count == 0
    
    def test_call_failure_increments_counter(self):
        """Неуспішний виклик через call() збільшує лічильник помилок."""
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=300)
        
        def failing_func():
            raise Exception("API Error")
        
        with pytest.raises(Exception, match="API Error"):
            cb.call(failing_func)
        
        assert cb.failure_count == 1
    
    def test_call_blocked_when_open(self):
        """Виклик блокується, коли Circuit Breaker відкритий."""
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=300)
        
        # Відкриваємо
        cb.record_failure()
        assert cb.is_open() is True
        
        # Спроба виклику має бути заблокована
        def any_func():
            return "should not execute"
        
        with pytest.raises(Exception, match="Circuit breaker is OPEN"):
            cb.call(any_func)
    
    @pytest.mark.parametrize("threshold,expected_failures", [
        (1, 1),
        (3, 3),
        (5, 5),
        (10, 10),
    ])
    def test_configurable_threshold(self, threshold, expected_failures):
        """Circuit Breaker підтримує налаштовуваний поріг помилок."""
        cb = CircuitBreaker(failure_threshold=threshold, recovery_timeout=300)
        
        for _ in range(expected_failures):
            cb.record_failure()
        
        assert cb.is_open() is True
        assert cb.failure_count == expected_failures
    
    def test_concurrent_access(self):
        """АНТИКРИХКІСТЬ: Circuit Breaker працює коректно при конкурентному доступі."""
        import threading
        
        cb = CircuitBreaker(failure_threshold=100, recovery_timeout=300)
        
        def increment_failures():
            for _ in range(10):
                cb.record_failure()
        
        threads = [threading.Thread(target=increment_failures) for _ in range(10)]
        
        for t in threads:
            t.start()
        
        for t in threads:
            t.join()
        
        # Має бути 100 помилок (10 потоків * 10 помилок)
        assert cb.failure_count == 100
