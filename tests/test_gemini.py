import sys
from pathlib import Path

# Додаємо корінь проекту до шляхів імпорту Python
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from google import genai
    from config.settings import GEMINI_API_KEY, GEMINI_MODEL
except ImportError as e:
    print(f"❌ Помилка імпорту бібліотек: {e}")
    print("Рекомендація: перевірте, чи встановлено новий пакет 'google-genai' та чи активоване venv.")
    sys.exit(1)

# Валідація наявності ключа
if not GEMINI_API_KEY or GEMINI_API_KEY == "your_key_here" or "твій_ключ" in GEMINI_API_KEY:
    print("❌ Помилка конфігурації: API-ключ не налаштований у .env!")
    sys.exit(1)

print(f"🔄 Спроба з'єднання з новим Gemini API (модель: {GEMINI_MODEL})...")

try:
    # Ініціалізація нового уніфікованого клієнта Google GenAI
    client = genai.Client(api_key=GEMINI_API_KEY)
    
    # Виклик моделі згідно з новим синтаксисом SDK
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents="Скажи: OK"
    )
    
    result_text = response.text.strip()
    if "OK" in result_text.upper():
        print(f"\n[УСПІХ] Відповідь моделі: {result_text}")
        print("✅ OK (Тест міграції на новий SDK успішно пройдено!)")
    else:
        print(f"⚠️ Отримано неочікувану відповідь від моделі: {result_text}")
        
except Exception as e:
    error_str = str(e)
    print("\n❌ Не вдалося отримати відповідь від нового Gemini API.")
    print(f"Деталі помилки: {error_str}")
    print("\n--- ДІАГНОСТИКА ---")
    if "API_KEY_INVALID" in error_str:
        print("👉 Скопійований API-ключ недійсний. Перевірте вміст файлу .env.")
    elif "quota" in error_str.lower() or "429" in error_str:
        print("👉 Перевищено ліміти безкоштовного тарифу (Rate Limit).")
    else:
        print("👉 Перевірте з'єднання з мережею або доступність обраної моделі в Google AI Studio.")
    sys.exit(1)
