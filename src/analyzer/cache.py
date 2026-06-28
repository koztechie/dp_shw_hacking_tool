import sys
from pathlib import Path
import hashlib
import json

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.logger import logger
from config.settings import CACHE_DIR

# Гарантуємо існування директорії для кешу
CACHE_PATH = Path(CACHE_DIR)
CACHE_PATH.mkdir(parents=True, exist_ok=True)

def cache_key(data) -> str:
    """
    Генерує MD5 хеш для будь-яких вхідних даних (рядок, словник, список).
    Використовується sort_keys=True для гарантії однакового хешу для однакових словників.
    """
    if isinstance(data, (dict, list)):
        data_str = json.dumps(data, sort_keys=True)
    else:
        data_str = str(data)
        
    return hashlib.md5(data_str.encode("utf-8")).hexdigest()

def get_cached(key: str):
    """
    Повертає закешовані дані за ключем. 
    Антикрихкість: якщо файл пошкоджено, він автоматично видаляється.
    """
    file_path = CACHE_PATH / f"{key}.json"
    
    if file_path.exists():
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            logger.warning(f"Кеш-файл {file_path.name} пошкоджено. Видаляємо для створення нового. Помилка: {e}")
            file_path.unlink()  # Видаляємо битий файл
            return None
        except Exception as e:
            logger.error(f"Помилка читання кешу {file_path.name}: {e}")
            return None
            
    return None

def set_cache(key: str, value):
    """Зберігає дані в кеш-файл."""
    file_path = CACHE_PATH / f"{key}.json"
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(value, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Не вдалося зберегти кеш у {file_path.name}: {e}")

if __name__ == "__main__":
    print("=== ТЕСТУВАННЯ СИСТЕМИ КЕШУВАННЯ (Етап 37) ===")
    
    # 1. Тест хешування словника
    test_data = {"hackathon": "Cal Hacks", "url": "https://calhacks.com"}
    key = cache_key(test_data)
    print(f"1. Згенерований ключ: {key}")
    
    # 2. Запис у кеш
    set_cache(key, {"analysis": "Great hackathon", "score": 95})
    print("2. Дані успішно записані в кеш.")
    
    # 3. Читання з кешу
    cached = get_cached(key)
    print(f"3. Зчитані дані: {cached}")
    
    # 4. Перевірка антикрихкості (створюємо битий файл)
    bad_key = cache_key("broken_test")
    bad_file = CACHE_PATH / f"{bad_key}.json"
    with open(bad_file, "w") as f:
        f.write("{invalid_json_")
        
    print(f"4. Створено пошкоджений кеш-файл: {bad_key}.json. Спроба зчитати...")
    result = get_cached(bad_key)
    if result is None and not bad_file.exists():
        print("   ✅ Антикрихкість спрацювала: битий файл розпізнано та видалено!")
