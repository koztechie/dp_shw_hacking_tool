import pytest
from unittest.mock import patch, MagicMock

from src.utils.memory_guard import MemoryGuard

class TestMemoryGuard:
    """Тести для захисту від Out-Of-Memory (OOM) на слабкому залізі (AMD A4)."""
    
    @patch("src.utils.memory_guard.psutil.virtual_memory")
    def test_get_memory_usage(self, mock_vm):
        mock_vm.return_value = MagicMock(percent=45.5)
        assert MemoryGuard.get_memory_usage() == 45.5

    @patch("src.utils.memory_guard.psutil.virtual_memory")
    def test_check_memory_normal(self, mock_vm):
        """Пам'яті достатньо (менше 75%)."""
        mock_vm.return_value = MagicMock(percent=50.0)
        assert MemoryGuard.check_memory("test_task") is True

    @patch("src.utils.memory_guard.psutil.virtual_memory")
    def test_check_memory_warning(self, mock_vm):
        """Система під навантаженням (75%-85%), але задача дозволена."""
        mock_vm.return_value = MagicMock(percent=80.0)
        assert MemoryGuard.check_memory("test_task") is True

    @patch("src.utils.memory_guard.psutil.virtual_memory")
    def test_check_memory_critical(self, mock_vm):
        """Пам'ять переповнена (85%-95%), нові задачі блокуються."""
        mock_vm.return_value = MagicMock(percent=90.0)
        assert MemoryGuard.check_memory("test_task") is False

    @patch("src.utils.memory_guard.psutil.virtual_memory")
    def test_check_memory_emergency(self, mock_vm):
        """Критична межа OOM (>95%), все блокується."""
        mock_vm.return_value = MagicMock(percent=98.0)
        assert MemoryGuard.check_memory("test_task") is False

    @patch("src.utils.memory_guard.psutil.virtual_memory")
    def test_memory_aware_decorator_success(self, mock_vm):
        """Декоратор дозволяє виконання при достатній пам'яті."""
        mock_vm.return_value = MagicMock(percent=50.0)
        
        @MemoryGuard.memory_aware("test_task")
        def dummy_function():
            return "success"
            
        assert dummy_function() == "success"

    @patch("src.utils.memory_guard.psutil.virtual_memory")
    def test_memory_aware_decorator_blocks(self, mock_vm):
        """Декоратор кидає MemoryError при нестачі пам'яті."""
        mock_vm.return_value = MagicMock(percent=90.0)
        
        @MemoryGuard.memory_aware("test_task")
        def dummy_function():
            return "should_not_run"
            
        with pytest.raises(MemoryError, match="Insufficient memory for test_task"):
            dummy_function()
