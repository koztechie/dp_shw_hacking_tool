import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from src.utils import safe_path, validate_file_path, SecretManager, backup_database

class TestUtils:
    """Тести для загальних утиліт (безпека шляхів, секрети)."""

    def test_safe_path_valid(self):
        """safe_path успішно дозволяє безпечний шлях."""
        base = Path("/tmp/base")
        res = safe_path(base, "sub/file.txt")
        assert res.name == "file.txt"

    def test_safe_path_traversal(self):
        """safe_path викидає ValueError при спробі path traversal."""
        base = Path("/tmp/base")
        with pytest.raises(ValueError, match="Path traversal detected"):
            safe_path(base, "../etc/passwd")

    def test_validate_file_path_nonexistent(self):
        """validate_file_path повертає False для неіснуючого шляху."""
        assert not validate_file_path(Path("/nonexistent/file.txt"))

    def test_validate_file_path_existent(self, tmp_path):
        """validate_file_path валідує розширення файлу."""
        f = tmp_path / "test.json"
        f.write_text("{}")
        
        assert validate_file_path(f, [".json"])
        assert not validate_file_path(f, [".csv"])

    @patch("src.utils.Path")
    def test_secret_manager(self, mock_path, tmp_path):
        """SecretManager створює новий ключ шифрування та успішно шифрує/дешифрує."""
        # Мокаємо домашню директорію, щоб не міняти реальні файли користувача
        mock_key_file = tmp_path / ".dp_shw_encryption_key"
        mock_path.home.return_value = tmp_path
        # Оскільки Path() всередині SecretManager створює об'єкти, налаштуємо поведінку:
        # Для спрощення, замінимо Path.home() на повернення нашої тимчасової директорії.
        with patch.object(Path, "home", return_value=tmp_path):
            sm = SecretManager()
            
            secret = "my_super_secret_api_key"
            encrypted = sm.encrypt(secret)
            decrypted = sm.decrypt(encrypted)
            
            assert decrypted == secret
            assert encrypted != secret.encode()

    def test_backup_database_success(self, tmp_path):
        """Успішне створення бекапу бази даних."""
        db_file = tmp_path / "test.duckdb"
        db_file.write_text("dummy db data")
        
        backup_dir = tmp_path / "backups"
        
        # Створимо кілька старих бекапів для тестування ротації (>7)
        for i in range(10):
            old_backup = backup_dir / f"dp_shw_backup_20240101_00000{i}.duckdb"
            old_backup.parent.mkdir(parents=True, exist_ok=True)
            old_backup.write_text("old data")
            
        backup_file = backup_database(db_file, backup_dir)
        
        assert backup_file.exists()
        # Має залишитися рівно 7 останніх бекапів (згідно з ротацією)
        remaining_backups = list(backup_dir.glob("dp_shw_backup_*.duckdb"))
        assert len(remaining_backups) == 7

    def test_backup_database_nonexistent(self, tmp_path):
        """backup_database повертає None для неіснуючої БД."""
        db_file = tmp_path / "nonexistent.duckdb"
        assert backup_database(db_file, tmp_path / "backups") is None

    @patch("src.utils.shutil.copy2")
    def test_backup_database_exception(self, mock_copy, tmp_path):
        """backup_database безпечно ловить виключення та повертає None."""
        db_file = tmp_path / "test.duckdb"
        db_file.write_text("data")
        mock_copy.side_effect = OSError("Disk full")
        
        assert backup_database(db_file, tmp_path / "backups") is None
