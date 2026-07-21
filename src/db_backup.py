import sys
from pathlib import Path
import shutil
import gzip
from datetime import datetime

# Гарантуємо правильні шляхи
PROJECT_ROOT = Path(__file__).resolve().parent.parent

from src.logger import logger
from config.settings import DB_PATH

def backup_database():
    backup_dir = PROJECT_ROOT / "data" / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    
    if not DB_PATH.exists():
        logger.warning("⚠️ База даних не існує. Бекап скасовано.")
        return

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = backup_dir / f"dp_shw_{timestamp}.duckdb.gz"
    temp_backup = backup_dir / f"temp_{timestamp}.duckdb"

    try:
        logger.info("📦 Початок створення резервної копії бази даних...")
        # Безпечне копіювання поточного стану
        shutil.copy2(DB_PATH, temp_backup)
        
        # GZIP стиснення для економії дискового простору (10x стиснення для DB)
        with open(temp_backup, 'rb') as f_in:
            with gzip.open(backup_file, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)
        
        # Видаляємо тимчасовий нестиснений файл
        temp_backup.unlink()
        logger.info(f"✅ Успішно збережено стиснений бекап: {backup_file.name}")
        
        # Ротація (Залишаємо лише 7 найновіших копій)
        backups = sorted(backup_dir.glob("dp_shw_*.duckdb.gz"))
        if len(backups) > 7:
            for old_backup in backups[:-7]:
                old_backup.unlink()
                logger.info(f"🗑️ Видалено старий бекап: {old_backup.name}")
                
    except Exception as e:
        logger.error(f"❌ Помилка створення бекапу: {e}")
        if temp_backup.exists():
            temp_backup.unlink()

if __name__ == "__main__":
    backup_database()
