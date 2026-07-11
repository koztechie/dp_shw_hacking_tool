from unittest.mock import patch, MagicMock
from src.db_backup import backup_database
from src.scraper.restore_urls import run_restore

class TestBackupRestore:
    """Тести для операцій резервного копіювання та відновлення даних."""
    
    @patch("src.db_backup.shutil.copyfileobj")
    @patch("src.db_backup.shutil.copy2")
    @patch("src.db_backup.DB_PATH")
    def test_backup_database_success(self, mock_db_path, mock_copy2, mock_copyfileobj, tmp_path):
        """Перевірка успішного бекапу бази даних."""
        mock_db_path.exists.return_value = True
        
        # Використовуємо тимчасову папку для збереження бекапів
        backup_dir = tmp_path / "data" / "backups"
        
        def fake_copy2(src, dst):
            with open(dst, 'wb') as f:
                f.write(b"dummy")
        mock_copy2.side_effect = fake_copy2
        
        with patch("src.db_backup.PROJECT_ROOT", tmp_path):
            backup_database()
            
            # Перевіряємо створення папки
            assert backup_dir.exists()
            
            # Перевіряємо копіювання
            mock_copy2.assert_called_once()
            mock_copyfileobj.assert_called_once()

    @patch("src.db_backup.shutil.copy2")
    @patch("src.db_backup.DB_PATH")
    def test_backup_database_missing_db(self, mock_db_path, mock_copy2, tmp_path):
        """Якщо БД відсутня, бекап не виконується."""
        mock_db_path.exists.return_value = False
        
        with patch("src.db_backup.PROJECT_ROOT", tmp_path):
            backup_database()
            
            mock_copy2.assert_not_called()

    @patch("src.db_backup.DB_PATH")
    def test_backup_database_rotation(self, mock_db_path, tmp_path):
        """Антикрихкість: збереження лише 7 останніх копій, щоб уникнути переповнення диска."""
        mock_db_path.exists.return_value = True
        
        backup_dir = tmp_path / "data" / "backups"
        backup_dir.mkdir(parents=True)
        
        # Створюємо 10 старих файлів бекапів
        for i in range(10):
            f = backup_dir / f"dp_shw_test_{i}.duckdb.gz"
            f.touch()
            
        with patch("src.db_backup.PROJECT_ROOT", tmp_path), \
             patch("src.db_backup.shutil.copy2") as mock_copy2, \
             patch("src.db_backup.shutil.copyfileobj"):
             
            def fake_copy2(src, dst):
                with open(dst, 'wb') as f:
                    f.write(b"dummy")
            mock_copy2.side_effect = fake_copy2
             
            backup_database()
            
            # Всього має залишитися 7 файлів
            remaining_backups = list(backup_dir.glob("dp_shw_*.duckdb.gz"))
            assert len(remaining_backups) == 7

    @patch("src.db_backup.shutil.copy2")
    @patch("src.db_backup.DB_PATH")
    def test_backup_database_cleanup_on_error(self, mock_db_path, mock_copy2, tmp_path):
        """Антикрихкість: видалення тимчасового файлу при помилці архівації."""
        mock_db_path.exists.return_value = True
        
        # Викликаємо помилку при копіюванні
        mock_copy2.side_effect = Exception("Disk full")
        
        backup_dir = tmp_path / "data" / "backups"
        
        with patch("src.db_backup.PROJECT_ROOT", tmp_path):
            backup_database()
            
            # Перевіряємо, що тимчасовий файл (temp_*) був видалений/не існує
            temp_files = list(backup_dir.glob("temp_*.duckdb"))
            assert len(temp_files) == 0

    @patch("src.scraper.restore_urls.time.sleep")
    @patch("src.scraper.restore_urls.fetch_hackathon_projects")
    @patch("src.scraper.restore_urls.get_connection")
    def test_run_restore_success(self, mock_get_connection, mock_fetch, mock_sleep):
        """Успішне відновлення відсутніх URL проектів."""
        mock_con = MagicMock()
        mock_get_connection.return_value = mock_con
        
        # Мокаємо результати з БД
        mock_con.execute.return_value.fetchall.return_value = [
            ("h1", "http://test.devpost.com", "Test Hackathon")
        ]
        
        # Мокаємо проекти з галереї
        mock_fetch.return_value = [
            {"title": "Proj1", "project_url": "http://p1.com"},
            {"title": "Proj2", "project_url": "http://p2.com"}
        ]
        
        run_restore()
        
        # Перевіряємо транзакції
        mock_con.execute.assert_any_call("BEGIN")
        mock_con.commit.assert_called_once()
        mock_con.rollback.assert_not_called()
        
        # Перевіряємо виклик UPDATE
        assert mock_con.execute.call_count > 2  # BEGIN, UPDATEs, etc.

    @patch("src.scraper.restore_urls.time.sleep")
    @patch("src.scraper.restore_urls.fetch_hackathon_projects")
    @patch("src.scraper.restore_urls.get_connection")
    def test_run_restore_rollback_on_error(self, mock_get_connection, mock_fetch, mock_sleep):
        """Антикрихкість: якщо стається помилка, транзакція відкочується."""
        mock_con = MagicMock()
        mock_get_connection.return_value = mock_con
        
        mock_con.execute.return_value.fetchall.return_value = [
            ("h1", "http://test.devpost.com", "Test Hackathon")
        ]
        
        # Викликаємо помилку при fetch
        mock_fetch.side_effect = Exception("Network error")
        
        run_restore()
        
        mock_con.commit.assert_not_called()
        mock_con.rollback.assert_called_once()
