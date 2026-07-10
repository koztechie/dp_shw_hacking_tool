from pathlib import Path


def safe_path(base_dir: Path, user_path: str) -> Path:
    """
    АНТИКРИХКІСТЬ: Безпечне об'єднання шляхів з захистом від Path Traversal.
    """
    base = base_dir.resolve()
    target = (base / user_path).resolve()

    # Перевірка, що target знаходиться всередині base
    if not str(target).startswith(str(base)):
        raise ValueError(f"Path traversal detected: {user_path}")

    return target


def validate_file_path(file_path: Path, allowed_extensions: list[str] = None) -> bool:
    """
    Валідація шляху до файлу.
    """
    if not file_path.exists():
        return False

    return allowed_extensions is None or file_path.suffix.lower() in allowed_extensions


from cryptography.fernet import Fernet  # noqa: E402


class SecretManager:
    """
    АНТИКРИХКІСТЬ: Шифрування/дешифрування секретів.
    """

    def __init__(self):
        # Ключ шифрування зберігається окремо від .env
        key_file = Path.home() / ".dp_shw_encryption_key"

        if not key_file.exists():
            # Генеруємо новий ключ
            key = Fernet.generate_key()
            key_file.write_bytes(key)
            key_file.chmod(0o600)  # Тільки власник може читати
        else:
            key = key_file.read_bytes()

        self.cipher = Fernet(key)

    def encrypt(self, secret: str) -> bytes:
        return self.cipher.encrypt(secret.encode())

    def decrypt(self, encrypted: bytes) -> str:
        return self.cipher.decrypt(encrypted).decode()


import shutil  # noqa: E402
from datetime import datetime  # noqa: E402

from src.logger import logger  # noqa: E402


def backup_database(db_path: Path, backup_dir: Path = None):
    """
    АНТИКРИХКІСТЬ: Автоматичний backup БД.
    """
    if backup_dir is None:
        backup_dir = db_path.parent / "backups"

    backup_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = backup_dir / f"dp_shw_backup_{timestamp}.duckdb"

    try:
        if db_path.exists():
            shutil.copy2(db_path, backup_file)

            # Зберігаємо тільки останні 7 backup-ів
            backups = sorted(backup_dir.glob("dp_shw_backup_*.duckdb"), reverse=True)
            for old_backup in backups[7:]:
                old_backup.unlink()

            return backup_file
        return None
    except Exception as e:
        logger.error(f"Failed to backup database: {e}")
        return None
