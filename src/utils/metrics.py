import time
from functools import wraps

from prometheus_client import Counter, Gauge, Histogram

# Метрики
REQUEST_COUNT = Counter(
    'dp_shw_requests_total',
    'Total number of requests',
    ['method', 'endpoint', 'status']
)

REQUEST_DURATION = Histogram(
    'dp_shw_request_duration_seconds',
    'Request duration in seconds',
    ['method', 'endpoint']
)

DATABASE_CONNECTIONS = Gauge(
    'dp_shw_database_connections_active',
    'Number of active database connections'
)

ML_PREDICTIONS = Counter(
    'dp_shw_ml_predictions_total',
    'Total number of ML predictions'
)

AI_API_CALLS = Counter(
    'dp_shw_ai_api_calls_total',
    'Total number of AI API calls',
    ['model', 'status']
)

MEMORY_USAGE = Gauge(
    'dp_shw_memory_usage_percent',
    'Current memory usage percentage'
)

def track_metrics(method: str, endpoint: str):
    """Декоратор для автоматичного трекингу метрик."""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            status = "success"

            try:
                result = await func(*args, **kwargs)
                return result
            except Exception:
                status = "error"
                raise
            finally:
                duration = time.time() - start_time
                REQUEST_COUNT.labels(method=method, endpoint=endpoint, status=status).inc()
                REQUEST_DURATION.labels(method=method, endpoint=endpoint).observe(duration)

        return wrapper
    return decorator
