import sys
from pathlib import Path

# Гарантуємо правильні шляхи імпорту
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.logger import logger

print("=== ТЕСТУВАННЯ СИСТЕМИ МОНІТОРИНГУ SENTRY ===")

logger.info("Запуск тестового скрипту. Цей запис має з'явитися в Sentry як Breadcrumb (слід).")

# 1. Спроба логування помилки
logger.error("🚨 Тестове повідомлення про помилку від логера!")

# 2. Штучно викликаємо критичний виняток
try:
    print("⏳ Генеруємо штучний виняток ZeroDivisionError...")
    result = 1 / 0
except Exception as e:
    # Передаємо виняток у логер. Завдяки інтеграції Loguru, Sentry миттєво зафіксує цей трейсбек!
    logger.exception(f"Перехоплено виняток: {e}")
    print("✅ Тестовий виняток успішно згенеровано та залоговано.")

print("\nПеревірте ваш особистий кабінет на Sentry.io. Там мають з'явитися два нові інциденти!")
