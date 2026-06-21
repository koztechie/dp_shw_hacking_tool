import sys
from pathlib import Path
from loguru import logger

# Додаємо корінь проекту до шляхів імпорту
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import LOG_PATH

# Гарантуємо існування директорії logs/
Path(LOG_PATH).parent.mkdir(parents=True, exist_ok=True)

# Налаштовуємо запис у файл із примусовим UTF-8 кодуванням
logger.add(
    LOG_PATH,
    rotation="10 MB",
    retention="30 days",
    level="INFO",
    encoding="utf-8",
    backtrace=True,
    diagnose=True
)

if __name__ == "__main__":
    logger.info("Тестовий запис системи логування. Українська кирилиця підтримується успішно.")
    print("Логування налаштовано. Перевірте вміст файлу за шляхом logs/app.log")
