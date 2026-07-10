from functools import wraps

import psutil

from src.logger import logger


class MemoryGuard:
    """
    АНТИКРИХКІСТЬ: Захист від OOM (Out Of Memory) на слабкому залізі.
    """

    # Пороги використання RAM (у відсотках)
    WARNING_THRESHOLD = 75  # Попередження при 75%
    CRITICAL_THRESHOLD = 85  # Блокування нових задач при 85%
    EMERGENCY_THRESHOLD = 95  # Примусове завершення при 95%

    @classmethod
    def get_memory_usage(cls) -> float:
        """Повертає поточне використання RAM у відсотках."""
        return psutil.virtual_memory().percent

    @classmethod
    def check_memory(cls, task_name: str = "Operation") -> bool:
        """
        Перевіряє, чи достатньо пам'яті для виконання задачі.
        Повертає True, якщо можна продовжувати, False - якщо треба зупинитися.
        """
        usage = cls.get_memory_usage()

        if usage >= cls.EMERGENCY_THRESHOLD:
            logger.critical(f"🚨 КРИТИЧНО: RAM {usage:.1f}% > {cls.EMERGENCY_THRESHOLD}%. "
                          f"Задача '{task_name}' примусово завершена для запобігання OOM Kill.")
            return False

        if usage >= cls.CRITICAL_THRESHOLD:
            logger.error(f"⚠️ Блокування: RAM {usage:.1f}% > {cls.CRITICAL_THRESHOLD}%. "
                        f"Задача '{task_name}' не може бути запущена.")
            return False

        if usage >= cls.WARNING_THRESHOLD:
            logger.warning(f"⚠️ Увага: RAM {usage:.1f}% > {cls.WARNING_THRESHOLD}%. "
                          f"Задача '{task_name}' запущена, але система під навантаженням.")

        return True

    @classmethod
    def memory_aware(cls, task_name: str = "Operation"):
        """
        Декоратор для функцій, які потребують багато пам'яті.
        Автоматично перевіряє RAM перед виконанням.
        """
        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                if not cls.check_memory(task_name):
                    raise MemoryError(f"Insufficient memory for {task_name}. "
                                    f"Current usage: {cls.get_memory_usage():.1f}%")
                return func(*args, **kwargs)
            return wrapper
        return decorator

# Глобальний інстанс
memory_guard = MemoryGuard()
