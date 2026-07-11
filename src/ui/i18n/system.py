"""
DP_SHW i18n System — Антикрихка локалізація
Гарантує, що КОЖЕН текст має fallback і ніколи не показує сирий ключ
"""
from typing import Dict, Any
from pathlib import Path
import importlib

class CopySystem:
    def __init__(self, default_locale: str = "uk"):
        self.default_locale = default_locale
        self.current_locale = default_locale
        self._cache: Dict[str, Dict[str, str]] = {}
        self._load_locale(default_locale)
    
    def _load_locale(self, locale: str) -> None:
        if locale in self._cache:
            return
        try:
            module = importlib.import_module(f"src.ui.i18n.{locale}")
            self._cache[locale] = getattr(module, "COPY", {})
        except ImportError:
            # АНТИКРИХКІСТЬ: fallback на українську, якщо мова не знайдена
            if locale != self.default_locale:
                self._load_locale(self.default_locale)
                self._cache[locale] = self._cache.get(self.default_locale, {})
            else:
                self._cache[locale] = {}
    
    def t(self, key: str, **kwargs: Any) -> str:
        """
        Повертає локалізований текст.
        АНТИКРИХКІСТЬ: якщо ключа немає — повертає сам ключ у читабельному форматі,
        а не порожній рядок і не exception.
        """
        self._load_locale(self.current_locale)
        text = self._cache.get(self.current_locale, {}).get(key)
        
        if text is None:
            # Fallback: "error.file_too_large.title" → "Error: File Too Large (Title)"
            text = self._humanize_key(key)
        
        try:
            return text.format(**kwargs)
        except (KeyError, IndexError):
            return text
    
    def _humanize_key(self, key: str) -> str:
        """Перетворює 'error.file_too_large.title' на читабельний fallback."""
        parts = key.split(".")
        return " · ".join(p.replace("_", " ").title() for p in parts)

# Глобальний інстанс
copy = CopySystem()

# Шорткат для шаблонів
def t(key: str, **kwargs: Any) -> str:
    return copy.t(key, **kwargs)
