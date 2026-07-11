import pytest
from src.utils.metrics import track_metrics, REQUEST_COUNT, REQUEST_DURATION

@pytest.mark.anyio
async def test_track_metrics_success():
    """Тест успішного виклику з логуванням метрик."""
    @track_metrics("GET", "/test")
    async def sample_func():
        return "ok"
    
    res = await sample_func()
    assert res == "ok"

@pytest.mark.anyio
async def test_track_metrics_error():
    """Тест виклику з виключенням та логуванням статусу помилки."""
    @track_metrics("POST", "/test-error")
    async def sample_func_error():
        raise ValueError("test error")
        
    with pytest.raises(ValueError, match="test error"):
        await sample_func_error()
